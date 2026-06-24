"""[노드] 작성 — 리서치를 바탕으로 뉴스레터 초안 작성 (LLM 사용).

작성한 초안은 이 노드 안에서 바로 DB(newsletter 테이블)에 저장합니다.
(어느 화면/관문에서 그래프를 돌리든 자동으로 저장되도록 백엔드에 둡니다)
"""
from __future__ import annotations

import json

from langgraph.config import get_config

from ..db import execute
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
    # 생성 타입(요약형/트렌드분석형/실무요약형 …)이 지정되면 그 스타일을 반영합니다.
    type_name = state.get("type_name")
    if type_name:
        type_desc = state.get("type_desc") or ""
        system += (f" 이 뉴스레터는 '{type_name}' 스타일로 작성한다. {type_desc} "
                   f"제목 끝에 '({type_name})'을 붙여라.")
    user = f"[리서치]\n{research}\n"
    if feedback:
        user += f"\n[수정 요청]\n{feedback}\n위 요청을 반드시 반영해서 다시 써 줘."

    draft = ask_ai(system, user)

    _save_draft(state, draft)   # 작성한 초안을 DB에 저장
    return {"draft": draft, "status": "reviewing"}


def _save_draft(state: NewsletterState, draft: str) -> None:
    """작성한 초안을 newsletter 테이블에 저장합니다. (thread_id 기준 upsert)

    - thread_id 는 그래프 실행 설정에서 가져옵니다(get_config).
    - DB 저장이 실패해도 그래프 흐름은 막지 않도록 예외를 삼킵니다(best-effort).
    """
    try:
        thread_id = (get_config().get("configurable") or {}).get("thread_id")
    except Exception:
        thread_id = None      # 그래프 밖에서 단독 호출(예: 테스트)되면 저장 생략
    if not thread_id:
        return

    title = next((ln[2:].strip()[:255] for ln in draft.split("\n")
                  if ln.startswith("# ")), "뉴스레터")
    review = state.get("review") or {}
    try:
        execute(
            "INSERT INTO newsletter "
            "(thread_id, category_id, news_type, title, keywords, draft, "
            " review_score, review_feedback, revision_count, status) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE "
            "  category_id = VALUES(category_id), news_type = VALUES(news_type), "
            "  title = VALUES(title), keywords = VALUES(keywords), draft = VALUES(draft), "
            "  review_score = VALUES(review_score), review_feedback = VALUES(review_feedback), "
            "  revision_count = VALUES(revision_count), status = VALUES(status)",
            (
                thread_id,
                state.get("category_id"),
                state.get("type_name"),
                title,
                json.dumps(state.get("keywords") or [], ensure_ascii=False),
                draft,
                review.get("score"),
                review.get("feedback"),
                state.get("revision_count", 0),
                "reviewing",
            ),
        )
    except Exception as e:
        print(f"[작성] 보고서 DB 저장 실패(무시하고 진행): {e}")


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
