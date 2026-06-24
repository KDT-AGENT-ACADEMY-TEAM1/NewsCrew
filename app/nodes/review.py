"""[노드] 검수 — 초안 품질 판정 (자동 1차 검수).

검수 결과(점수/통과 여부)를 DB(newsletter)에 저장합니다.
이 노드까지가 '그래프 한 덩어리'이고, 직후 send 직전에서 멈춰 사람 승인을 받습니다.
"""
from __future__ import annotations

from langgraph.config import get_config

from ..db import execute
from ..state import NewsletterState, ReviewResult


# ==========================================================================
# STEP 4. 검수 노드 — 초안 품질 판정 + 점수 저장
# ==========================================================================
def review_node(state: NewsletterState) -> NewsletterState:
    draft = state.get("draft", "")
    revision = state.get("revision_count", 0)
    print(f"[검수] 품질 검증 중 ({revision}회차)")

    # TODO: ask_ai() 로 LLM 검수를 시키고 싶으면 _simple_review 를 교체하세요.
    review = _simple_review(draft)
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
