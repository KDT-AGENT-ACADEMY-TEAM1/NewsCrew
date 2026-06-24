"""[노드] 작성 — 리서치를 바탕으로 뉴스레터 초안 작성 (LLM 사용)."""
from __future__ import annotations

from ..llm import ask_ai
from ..state import NewsletterState


# ==========================================================================
# STEP 3. 작성 노드 — 리서치를 바탕으로 초안 작성 (LLM 사용)
# ==========================================================================
def write_node(state: NewsletterState) -> NewsletterState:
    research = state.get("research", "") or state.get("tool_results", "")
    revision = state.get("revision_count", 0)

    feedback = _pick_feedback(state)
    print(f"[작성] 초안 작성 중 ({revision}회차)"
          + (f" / 피드백 반영: {feedback}" if feedback else ""))

    system = (
        "너는 뉴스레터 작성자다. 아래 리서치를 바탕으로 친근한 한국어 뉴스레터 초안을 써라. "
        "맨 위에 '# 제목' 한 줄, 본문에는 '## 소제목'을 2개 이상 넣어 마크다운으로 작성하라."
    )
    user = f"[리서치]\n{research}\n"
    if feedback:
        user += f"\n[수정 요청]\n{feedback}\n위 요청을 반드시 반영해서 다시 써 줘."

    draft = ask_ai(system, user)
    return {"draft": draft, "status": "reviewing"}


def _pick_feedback(state: NewsletterState) -> str:
    """반영해야 할 피드백을 고릅니다. (사람 피드백이 있으면 그것을 우선)"""
    review = state.get("review")
    if review and not review.get("passed", True):
        feedback = review.get("feedback", "")
    else:
        feedback = ""
    if state.get("human_feedback"):
        feedback = state["human_feedback"]
    return feedback
