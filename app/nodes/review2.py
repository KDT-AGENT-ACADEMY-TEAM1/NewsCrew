"""[노드] 검수 — 초안 품질 판정 (자동 1차 검수 - LLM 고도화 버전).

검수 결과(점수/통과 여부)를 DB(newsletter)에 저장합니다.
이 노드까지가 '그래프 한 덩어리'이고, 직후 send 직전에서 멈춰 사람 승인을 받습니다.
"""
from __future__ import annotations

import json
import re
from langgraph.config import get_config

from ..db import execute
from ..llm import ask_ai
from ..state import NewsletterState, ReviewResult


# ==========================================================================
# STEP 4. 검수 노드 — 초안 품질 판정 + 점수 저장
# ==========================================================================
def review_node(state: NewsletterState) -> NewsletterState:
    draft = state.get("draft", "")
    revision = state.get("revision_count", 0)
    keywords = state.get("keywords", [])
    print(f"[검수] 품질 검증 중 ({revision}회차) - review2 버전")

    # AI를 활용한 품질 검수 수행 (실패 시 규칙 기반 검수로 폴백)
    review = _llm_review(draft, keywords)
    revision_count = revision + 1
    status = "awaiting_approval" if review["passed"] else "writing"

    print(f"[검수] 결과: {'통과' if review['passed'] else '미달'} (점수 {review['score']})")
    _save_review(review, status, revision_count)   # 검수 점수/상태를 DB에 반영
    return {
        "review": review,
        "revision_count": revision_count,
        "status": status,
        "human_feedback": "",   # 피드백은 한 번 쓰고 비웁니다
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


def _llm_review(draft: str, keywords: list[str]) -> ReviewResult:
    """LLM 에디터에게 초안을 검수받아 구조화된 JSON 결과를 반환합니다."""
    keyword_str = ", ".join(keywords) if keywords else "없음"

    system_prompt = (
        "너는 IT/테크 전문 뉴스레터의 수석 편집장이다.\n"
        "작성된 뉴스레터 초안(draft)이 독자에게 제공하기에 높은 품질을 가졌는지 검수해야 한다.\n"
        "반드시 다음 조건들을 평가하고, 최종 평가 결과를 지정된 JSON 형식으로만 답변하라.\n\n"
        
        "※ 평가 기준:\n"
        f"1. 키워드 적합성: 초안이 핵심 키워드 [{keyword_str}]를 충분히 다루고 있는가?\n"
        "2. 구조화 및 가독성: 소제목(##, ###)과 리스트 등을 활용하여 모바일/메일 화면에서 가독성이 좋은가?\n"
        "3. 문체 및 완성도: 뉴스레터다운 친근하면서도 신뢰감 있는 어조(~해요체, 다나까체 등 조화)를 갖췄는가?\n"
        "4. 분량: 독자가 유용하게 읽을 만큼 충분한 내용을 담고 있는가?\n\n"
        
        "※ 통과 기준:\n"
        "- 4가지 기준 중 치명적인 결함이 없고, 평점 80점 이상일 때 passed: true로 판정한다.\n"
        "- 미달인 경우 passed: false로 지정하고, 작성 에디터가 다음 재작성 때 고칠 수 있게 피드백을 아주 구체적으로 작성하라.\n\n"
        
        "※ 출력 JSON 포맷 (반드시 다른 설명 없이 아래 형식의 JSON 텍스트 하나만 출력하라):\n"
        "{\n"
        '  "passed": true/false,\n'
        '  "score": 0~100 사이의 정수 점수,\n'
        '  "feedback": "구체적인 수정 제안 또는 칭찬 코멘트"\n'
        "}"
    )

    user_prompt = f"뉴스레터 초안:\n---\n{draft}\n---"

    try:
        response = ask_ai(system_prompt, user_prompt)
        
        # LLM 응답에서 JSON 형식만 추출 (```json 등으로 감싸져 있을 때를 대비)
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group(0))
            return {
                "passed": bool(result.get("passed", False)),
                "score": int(result.get("score", 50)),
                "feedback": str(result.get("feedback", "검수 완료")),
            }
    except Exception as e:
        print(f"[검수] LLM 검수 중 파싱 오류 발생(규칙 기반 폴백 사용): {e}")

    # 파싱에 실패하거나 API 에러가 나면 규칙 기반 폴백 수행
    return _simple_review(draft)


def _simple_review(draft: str) -> ReviewResult:
    """아주 단순한 규칙 검수: 길이가 충분하고 소제목(##)이 있으면 통과."""
    length_ok = len(draft) > 80
    has_section = "##" in draft
    passed = length_ok and has_section

    if passed:
        return {"passed": True, "score": 90, "feedback": "구성과 분량이 적절합니다. 통과."}

    reasons = []
    if not length_ok:
        reasons.append("내용이 너무 짧음")
    if not has_section:
        reasons.append("섹션 구성 부족")
    return {"passed": False, "score": 40,
            "feedback": "품질 미달: " + ", ".join(reasons)}
