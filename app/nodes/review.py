"""[노드] 검수 — 초안 품질 판정 (여기 결과로 다음 길이 갈립니다)."""
from __future__ import annotations

from ..state import NewsletterState, ReviewResult


# ==========================================================================
# STEP 4. 검수 노드 — 초안 품질 판정
# ==========================================================================
def review_node(state: NewsletterState) -> NewsletterState:
    draft = state.get("draft", "")
    revision = state.get("revision_count", 0)
    print(f"[검수] 품질 검증 중 ({revision}회차)")

    # TODO: ask_ai() 로 LLM 검수를 시키고 싶으면 _simple_review 를 교체하세요.
    review = _simple_review(draft)

    print(f"[검수] 결과: {'통과' if review['passed'] else '미달'} (점수 {review['score']})")
    return {
        "review": review,
        "revision_count": revision + 1,
        "status": "awaiting_approval" if review["passed"] else "writing",
        "human_feedback": "",   # 피드백은 한 번 쓰고 비웁니다
    }


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
