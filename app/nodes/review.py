"""[노드] 검수 — 초안 품질 판정 (자동 1차 검수).

검수 결과(점수/통과 여부)를 DB(newsletter)에 저장합니다.
이 노드까지가 '그래프 한 덩어리'이고, 직후 send 직전에서 멈춰 사람 승인을 받습니다.
"""
from __future__ import annotations

import json
from langgraph.config import get_config

from ..db import execute, get_int_setting
from ..llm import ask_ai
from ..state import NewsletterState, ReviewResult


# ==========================================================================
# STEP 4. 검수 노드 — 초안 품질 판정 + 점수 저장
#   '통과' 여부는 환경설정(app_setting)의 '승인 기준 점수(pass_score)'로 정합니다.
# ==========================================================================
def review_node(state: NewsletterState) -> NewsletterState:
    draft = state.get("draft", "")
    revision = state.get("revision_count", 0)

    # 1. 상태에서 타입명과 타입 설명 꺼내기
    type_name = state.get("type_name", "")
    type_desc = state.get("type_desc", "")
    
    print(f"[검수] AI 품질 검증 시작 ({revision}회차)")

    # 2. ask_ai() 로 LLM 검수를 수행합니다.
    review = _llm_review(draft, type_name, type_desc)
    
    # 3. 통과 기준 점수를 환경설정에서 읽어와 다시 판정합니다.
    # 단, AI가 과락 등의 사유로 이미 passed=False로 판정했다면 false를 유지합니다.
    pass_score = get_int_setting("pass_score", 60)
    review["passed"] = review.get("passed", False) and (review["score"] >= pass_score)
    
    if review["passed"]:
        review["feedback"] = f"승인 기준({pass_score}점) 이상으로 통과했습니다. 점수: {review['score']}. 코멘트: {review['feedback']}"
    else:
        review["feedback"] = f"품질 미달: {review['feedback']} (점수 {review['score']} / 기준 {pass_score})"

    revision_count = revision + 1
    status = "awaiting_approval" if review["passed"] else "writing"

    print(f"[검수] 결과: {'통과' if review['passed'] else '미달'} (점수 {review['score']} / 기준 {pass_score})")
    _save_review(review, status, revision_count)   # 검수 점수/상태를 DB에 반영
    
    return {
        "review": review,
        "revision_count": revision_count,
        "status": status,
        "human_feedback": "",   # 피드백은 한 번 쓰고 비웁니다
    }


def _llm_review(draft: str, type_name: str = "", type_desc: str = "") -> ReviewResult:
    """LLM을 사용하여 뉴스레터의 가독성, 흥미성, 형식을 종합 평가합니다."""
    if not draft or len(draft.strip()) < 100:
        return {
            "passed": False,
            "score": 30,
            "feedback": "초안의 분량이 너무 적거나 내용이 비어 있습니다.",
            "deduction_reasons": {
                "structure": "분량 부족",
                "expression": "분량 부족",
                "readability": "분량 부족",
                "tone": "분량 부족",
                "value": "분량 부족"
            },
            "suggested_fix": "초안 내용을 더 채워주세요."
        }

    system_prompt = (
        "당신은 구독자 10만 명을 보유한 프리미엄 IT/테크 뉴스레터의 대단히 까다롭고 날카로운 편집장입니다.\n"
        "당신의 임무는 제공된 초안에서 'AI 특유의 진부한 패턴, 영혼 없는 문장, 논리적 허점'을 찾아내어 엄격하게 채점하는 것입니다.\n"
        "단, 문맥상 정당한 이유가 있거나 구체적인 근거가 포함된 표현은 억울하게 감점해서는 안 됩니다.\n\n"
        "[🚨 채점 및 감점 필독 규칙]\n"
        "1. 모든 항목은 10점 만점으로 시작합니다. (기본 총점 100점)\n"
        "2. 각 항목별 감점 사유가 발견될 때마다 '맥락'을 확인한 뒤 감점 기준에 맞춰 정확하게 점수를 차감하세요.\n"
        "3. 기준 7(어미 혼용) 또는 기준 10(환각 정보) 항목에서 감점이 발생하여 5점 이하가 될 경우, 총점과 상관없이 \"passed\"는 무조건 false(과락 탈락)로 처리합니다.\n\n"
        "--- [10가지 엄격한 심사 기준 및 감점/가점 규정] ---\n\n"
        "1. [구조] 도입부(Hooking)의 자연스러움 (10점 시작)\n"
        "   - 감점(-3점): 첫 문장이 백과사전식 정의(\"~란 ...를 뜻합니다\")로 시작하거나, 너무 뻔한 질문(\"~에 대해 알고 계시나요?\")으로 지루하게 시작하는 경우.\n"
        "   - 유지(0점): 독자가 흥미를 느낄 만한 최신 트렌드, 가벼운 인사이트, 혹은 스토리텔링으로 자연스럽게 본론을 열었을 때.\n"
        "   - 가점(+2점): 오프닝의 흡입력이 매우 뛰어나고 본문 핵심 주제로 넘어가는 연결고리가 완벽한 경우. (최대 10점)\n\n"
        "2. [구조] 문단 간의 유기적 연결성 (10점 시작)\n"
        "   - 감점(-2점): 문단과 문단을 이을 때 논리적 흐름 없이 \"또한\", \"게다가\", \"마지막으로\", \"다음으로\" 같은 접속사만 기계적으로 남발하여 개조식 글을 억지로 이어 붙인 경우.\n"
        "   - 예외: 나열형 정보(예: '이번 주 주요 뉴스 3가지')를 전달하는 섹션에서 순서를 나타내기 위해 쓴 접속사는 감점하지 않습니다.\n\n"
        "3. [표현] 상투적 표현 및 미사여구 남발 (10점 시작)\n"
        "   - 감점(-3점): \"혁신적인\", \"놀라운\", \"획기적인\", \"주목할 만한\" 등의 수식어를 썼으나, 본문 어디에도 '왜 혁신적인지'에 대한 구체적인 근거(기술적 차별성, 기존 방식과의 수치적 비교 등)가 없이 단어만 공허하게 남발된 경우.\n"
        "   - 예외: 실제로 업계의 거대한 변화나 신기술을 다루고 있고, 그에 걸맞은 명확한 이유나 데이터가 본문에서 함께 증명된 경우는 정상적인 표현으로 인정하여 감점하지 않습니다.\n\n"
        "4. [표현] 동의어 반복 및 순환 논리 (10점 시작)\n"
        "   - 감점(-4점): 했던 말을 단어나 주어만 살짝 바꿔서 다음 문장에서 똑같이 또 반복하는 '영혼 없는 분량 늘리기 패턴'이 명백히 드러나는 경우.\n"
        "   - 예외: 글의 주제나 핵심 메시지를 강조하기 위해 의도적으로 미문(수사학적 반복)을 사용한 경우는 맥락을 고려하여 감점하지 않습니다.\n\n"
        "5. [가독성] 정보의 완급 조절 및 호흡 (10점 시작)\n"
        "   - 감점(-2점): 한 단락에 마침표가 4개 이상 들어갈 정도로 줄바꿈 없이 빽빽하여 스마트폰 화면에서 가독성이 해쳐지는 경우. 또는 반대로 깊이 없이 모든 문장을 한 줄씩만 쪼개놓아 가벼워 보이는 경우.\n\n"
        "6. [가독성] 구체적인 예시 및 비유의 적절성 (10점 시작)\n"
        "   - 감점(-3점): 독자가 이해하기 어려운 추상적이고 개념적인 설명만 장황하게 나열되어 있고, 실생활 예시, 비즈니스 케이스, 혹은 직관적인 비유가 단 하나도 없는 경우.\n"
        "   - 예외: 뉴스레터 전체의 분량이 아주 짧은 브리핑 형태이거나, 이미 대중적으로 널리 알려진 쉬운 개념을 다룰 때는 예시가 없어도 감점하지 않습니다.\n\n"
        "7. [톤앤매너] 어미의 일관성과 친근함 (🚨 과락 주의 / 10점 시작)\n"
        "   - 감점(-5점): 친근한 해요체(~요, ~습니다)로 전개하다가, 중간이나 맺음말에서 딱딱한 평서문(~다, ~임)으로 끝나는 문장이 섞여 브랜드 인격체의 일관성이 깨지는 경우.\n"
        "   - 예외: 인용구(\"~라고 전문가들은 말합니다.\")나 객관적인 통계 지표를 딱딱하게 인용하는 문장은 어미 예외로 인정합니다.\n\n"
        "8. [톤앤매너] 지나친 기계적 중립성 탈피 (10점 시작)\n"
        "   - 감점(-3점): \"이 기술은 장단점이 있습니다\", \"선택은 독자의 몫입니다\"처럼 결론을 흐리며 책임 회피성 양비론/양난론으로 마무리 짓는 경우. 뉴스레터는 필자의 명확한 인사이트나 주관을 제시해야 합니다.\n\n"
        "9. [정보가치] 핵심 요약의 명확성 (10점 시작)\n"
        "   - 감점(-4점): 글을 다 읽었을 때 독자가 기억해야 할 핵심 메시지(Key Takeaway)나 구체적인 행동 지침(Action Item)이 명확하게 한눈에 정리되어 있지 않은 경우.\n\n"
        "10. [정보가치] 할루시네이션 의심 정보 필터링 (🚨 과락 주의 / 10점 시작)\n"
        "    - 감점(-5점): 구체적인 출처(기관명, 전문가 이름, 보고서 제목 등) 없이 \"한 연구 결과에 따르면\", \"최근 통계에 의하면\" 등 날조된 정보로 의심되는 모호한 서술을 남발하는 경우.\n"
        "    - 예외: '최근 IT 업계의 전반적인 분위기'처럼 널리 알려진 거시적 현상을 서술할 때는 출처가 없어도 감점하지 않습니다.\n\n"
    )

    # 3. 타입 정보가 있다면 검수 프롬프트에 추가 조건 부여
    if type_name:
        system_prompt += (
            f"[추가 기준 - 타입 적합성]\n"
            f"이 뉴스레터는 '{type_name}' 타입으로 작성되어야 합니다.\n"
            f"   스타일 가이드: {type_desc}\n"
            f"   초안이 이 스타일 가이드 지침을 철저히 준수하여 쓰였는지 확인하고 평가 및 감점에 반영해 주세요.\n\n"
        )

    system_prompt += (
        "반드시 아래 JSON 포맷으로만 답변하세요. Markdown 코드 블록(```json 등)을 포함하지 말고 오직 순수 JSON 텍스트만 반환하세요. 다른 서론이나 설명은 절대 금지합니다.\n"
        "{\n"
        '  "passed": true 또는 false,\n'
        '  "score": 계산된 최종 정수 총점 (0~100),\n'
        '  "feedback": "전체 초안에 대한 핵심 총평 (편집장 관점에서 날카롭게 기술)",\n'
        '  "deduction_reasons": {\n'
        '    "structure": "기준 1, 2번 관련 감점 내역 및 이유 (감점 없으면 \'없음\')",\n'
        '    "expression": "기준 3, 4번 관련 감점 내역 및 이유 (감점 없으면 \'없음\')",\n'
        '    "readability": "기준 5, 6번 관련 감점 내역 및 이유 (감점 없으면 \'없음\')",\n'
        '    "tone": "기준 7, 8번 관련 감점 내역 및 이유 (감점 없으면 \'없음\')",\n'
        '    "value": "기준 9, 10번 관련 감점 내역 및 이유 (감점 없으면 \'없음\')"\n'
        '  },\n'
        '  "suggested_fix": "수정을 진행할 AI 작성자를 위해, \'어떤 단어를 빼고, 문단을 어떻게 연결하고, 어떤 예시를 추가해야 하는지\' 맥락에 맞게 지시하는 🛠️행동 지침 수정 가이드라인"\n'
        "}"
    )

    try:
        # 공통 모듈인 ask_ai를 통해 호출 (Mock 모드 자동 대응)
        response = ask_ai(system_prompt, f"--- 뉴스레터 초안 ---\n{draft}")
        
        # 가짜 AI 답변인 경우의 예외 처리 (Fail-safe)
        if response.startswith("[가짜 AI 답변]"):
            return {
                "passed": True,
                "score": 85,
                "feedback": "가짜 AI 검수 모드입니다. 테스트를 위해 임시 통과시킵니다.",
                "deduction_reasons": {
                    "structure": "없음",
                    "expression": "없음",
                    "readability": "없음",
                    "tone": "없음",
                    "value": "없음"
                },
                "suggested_fix": "가짜 AI 모드이므로 수정 제안이 없습니다."
            }

        # JSON 파싱 (안전장치 포함)
        clean_response = response.strip().replace("```json", "").replace("```", "")
        result = json.loads(clean_response)
        
        # 타입 검증 및 기본값 보장
        return {
            "passed": bool(result.get("passed", False)),
            "score": int(result.get("score", 0)),
            "feedback": str(result.get("feedback", "평가 결과가 올바르지 않습니다.")),
            "deduction_reasons": result.get("deduction_reasons", {}),
            "suggested_fix": str(result.get("suggested_fix", "수정 가이드라인이 제공되지 않았습니다."))
        }
    except Exception as e:
        print(f"[검수 에러] LLM 검수 중 오류 발생: {e}")
        # LLM 장애 시 시스템이 멈추지 않도록 Fail-Safe 처리 (재작성 유도)
        return {
            "passed": False,
            "score": 50,
            "feedback": f"AI 검수 프로세스 오류로 인해 재작성을 요청합니다. (에러: {e})",
            "deduction_reasons": {
                "structure": "시스템 오류",
                "expression": "시스템 오류",
                "readability": "시스템 오류",
                "tone": "시스템 오류",
                "value": "시스템 오류"
            },
            "suggested_fix": "시스템 에러로 감점이 발생했으므로 재작성을 권장합니다."
        }


def _save_review(review: ReviewResult, status: str, revision_count: int) -> None:
    """검수 점수/코멘트/상태를 newsletter 테이블에 갱신합니다.

    write 노드가 먼저 만들어 둔 같은 thread_id 행을 UPDATE 합니다.
    thread_id 는 그래프 실행 설정(get_config)에서 가져옵니다. (best-effort)
    """
    try:
        thread_id = (get_config().get("configurable") or {}).get("thread_id")
    except Exception:
        thread_id = None      # 그래프 밖 단독 호출(예: 테스트)이면 저장 생략
    if not thread_id:
        return
    try:
        execute(
            "UPDATE newsletter "
            "SET review_score = %s, review_feedback = %s, status = %s, revision_count = %s "
            "WHERE thread_id = %s",
            (review.get("score"), review.get("feedback"), status, revision_count, thread_id),
        )
    except Exception as e:
        print(f"[검수] 점수 DB 저장 실패(무시하고 진행): {e}")
