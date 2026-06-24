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
    print(f"[검수] AI 품질 검증 시작 ({revision}회차)")

    # 1. ask_ai() 로 LLM 검수를 수행합니다.
    review = _llm_review(draft)
    
    # 2. 통과 기준 점수를 환경설정에서 읽어와 다시 판정합니다. (Passed 여부 재조정)
    pass_score = get_int_setting("pass_score", 60)
    review["passed"] = review["score"] >= pass_score
    
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


def _llm_review(draft: str) -> ReviewResult:
    """LLM을 사용하여 뉴스레터의 가독성, 흥미성, 형식을 종합 평가합니다."""
    if not draft or len(draft.strip()) < 100:
        return {"passed": False, "score": 30, "feedback": "초안의 분량이 너무 적거나 내용이 비어 있습니다."}

    system_prompt = (
        "당신은 뉴스레터 편집장입니다. 제공된 초안의 품질을 엄격히 심사해야 합니다.\n"
        "다음 3가지 기준을 바탕으로 평가해주세요:\n"
        "1. 가독성 및 구성: 소제목(##) 활용 및 문단 나누기가 잘 되어 있는가?\n"
        "2. 톤앤매너: 독자에게 친근하고 전문적인 어조를 유지하는가?\n"
        "3. 정보의 가치: 핵심 내용이 명확하고 흥미로운가?\n\n"
        "반드시 아래 JSON 포맷으로만 답변하세요. 다른 말은 하지 마세요.\n"
        "{\n"
        '  "passed": true 또는 false,\n'
        '  "score": 0~100 사이의 정수 점수,\n'
        '  "feedback": "탈락했다면 구체적으로 어떤 점을 수정해야 하는지 피드백을, 통과했다면 칭찬 및 보완점 작성"\n'
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
                "feedback": "가짜 AI 검수 모드입니다. 테스트를 위해 임시 통과시킵니다."
            }

        # JSON 파싱 (안전장치 포함)
        clean_response = response.strip().replace("```json", "").replace("```", "")
        result = json.loads(clean_response)
        
        # 타입 검증 및 기본값 보장
        return {
            "passed": bool(result.get("passed", False)),
            "score": int(result.get("score", 0)),
            "feedback": str(result.get("feedback", "평가 결과가 올바르지 않습니다."))
        }
    except Exception as e:
        print(f"[검수 에러] LLM 검수 중 오류 발생: {e}")
        # LLM 장애 시 시스템이 멈추지 않도록 Fail-Safe 처리 (재작성 유도)
        return {
            "passed": False,
            "score": 50,
            "feedback": f"AI 검수 프로세스 오류로 인해 재작성을 요청합니다. (에러: {e})"
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
