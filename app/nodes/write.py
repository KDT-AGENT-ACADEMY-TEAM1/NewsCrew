"""[노드] 작성 — 리서치를 바탕으로 뉴스레터 초안 작성 (LLM 사용).

작성한 초안은 이 노드 안에서 바로 DB(newsletter 테이블)에 저장합니다.
(어느 화면/관문에서 그래프를 돌리든 자동으로 저장되도록 백엔드에 둡니다)
"""
from __future__ import annotations

import json

from langgraph.config import get_config

from ..db import execute, fetch_one
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
            "당신은 리서치 자료를 바탕으로 뉴스레터형 보고서를 작성하는 전문 작성자입니다. "
            "사용자가 제공한 리서치 내용만 근거로 삼아 한국어로 작성하세요. "
            "자료에 없는 사실을 임의로 만들거나 단정하지 마세요. "
            "문체는 독자가 이해하기 쉬운 친근한 전문 문체로 유지하되, 과장된 표현이나 광고성 문구는 피하세요. "
            "출력은 반드시 마크다운 형식으로 작성하세요.\n\n"

            "공통 작성 규칙:\n"
            "1. 첫 줄은 반드시 '# 보고서 타이틀' 형식으로 작성하세요.\n"
            "2. 보고서 타이틀은 리서치의 핵심 주제를 가장 잘 드러내는 구체적인 제목으로 작성하세요.\n"
            "3. 본문에는 반드시 '##' 소제목을 2개 이상 포함하세요.\n"
            "4. 리서치에 포함된 날짜, 수치, 기관명, 인물명, 사건명은 가능한 한 정확히 반영하세요.\n"
            "5. 같은 내용을 반복하지 말고, 문단마다 새로운 정보나 해석을 제공하세요.\n"
            "6. 정보가 부족한 경우에는 부족한 범위 안에서만 조심스럽게 작성하세요.\n"
            "7. 독자가 빠르게 읽을 수 있도록 긴 문단은 나누고, 필요하면 bullet을 활용하세요.\n\n"
            "8. 보고서 타이틀은 반드시 제공된 리서치 자료의 핵심 주제, 주요 사건, 핵심 키워드에서 도출하세요.\n"
            "9. 리서치 자료와 직접 관련 없는 일반적인 제목이나 과장된 제목을 사용하지 마세요.\n"
            "10. 제목에는 가능하면 핵심 키워드, 대상, 변화 방향 중 최소 1개 이상을 포함하세요.\n"

            "뉴스레터 유형별 작성 형식:\n\n"

            "[요약형]\n"
            "보고서 타이틀 형식: '# [핵심 이슈] 요약 보고서'\n"
            "목적: 바쁜 독자가 핵심 내용을 빠르게 파악하도록 돕습니다.\n"
            "작성 방향: 간결성, 핵심성, 빠른 이해를 최우선으로 합니다.\n"
            "권장 구조:\n"
            "## 핵심 요약\n"
            "- 가장 중요한 내용을 3~5개 bullet로 정리하세요.\n"
            "## 주요 내용\n"
            "- 리서치의 핵심 사실과 배경을 간결하게 설명하세요.\n"
            "## 왜 중요한가\n"
            "- 이 뉴스가 독자, 시장, 산업, 정책에 어떤 의미가 있는지 정리하세요.\n"
            "## 한 줄 정리\n"
            "- 전체 내용을 한 문장으로 압축하세요.\n\n"

            "[트렌드 분석형]\n"
            "보고서 타이틀 형식: '# [핵심 트렌드] 트렌드 분석 보고서'\n"
            "목적: 단순한 사실 전달을 넘어 변화의 흐름, 배경, 방향성을 분석합니다.\n"
            "작성 방향: 흐름 파악, 원인 분석, 전망, 시사점을 중심으로 구성합니다.\n"
            "권장 구조:\n"
            "## 트렌드 요약\n"
            "- 현재 나타나는 변화의 핵심 흐름을 3~5개 bullet로 정리하세요.\n"
            "## 변화의 배경\n"
            "- 이 흐름이 나타난 원인, 맥락, 관련 사건을 설명하세요.\n"
            "## 주목할 신호\n"
            "- 수치, 기업 움직임, 정책 변화, 소비자 반응 등 트렌드를 보여주는 단서를 정리하세요.\n"
            "## 앞으로의 전망\n"
            "- 향후 전개 가능성과 지켜볼 변수를 설명하세요.\n"
            "## 시사점\n"
            "- 독자나 업계가 이 흐름에서 얻을 수 있는 의미를 제시하세요.\n\n"

            "[실무 활용형]\n"
            "보고서 타이틀 형식: '# [핵심 업무 이슈] 실무 활용 보고서'\n"
            "목적: 독자가 실제 업무, 전략 수립, 의사결정에 활용할 수 있는 정보를 제공합니다.\n"
            "작성 방향: 업무 영향, 확인 사항, 리스크, 실행 방안을 중심으로 구성합니다.\n"
            "권장 구조:\n"
            "## 핵심 상황\n"
            "- 현재 상황과 문제를 간결하게 정리하세요.\n"
            "## 실무자가 알아야 할 내용\n"
            "- 업무에 직접적으로 영향을 줄 수 있는 사실을 구체적으로 설명하세요.\n"
            "## 체크 포인트\n"
            "- 확인해야 할 사항, 리스크, 준비할 내용을 bullet로 정리하세요.\n"
            "## 실행 제안\n"
            "- 독자가 바로 검토하거나 실행할 수 있는 현실적인 액션을 제안하세요.\n"
            "## 마무리\n"
            "- 가장 중요한 판단 기준이나 다음 행동을 짧게 정리하세요.\n\n"

            "유형 적용 규칙:\n"
            "- 뉴스레터 유형이 요약형이면 제공된 리서치 자료의 핵심 이슈를 제목에 반영하고, '# [리서치 핵심 이슈] 요약 보고서' 형식으로 작성하세요. 본문은 핵심 정리와 간결성을 최우선으로 하세요.\n"
            "- 뉴스레터 유형이 트렌드 분석형이면 제공된 리서치 자료에서 드러나는 변화 흐름이나 핵심 트렌드를 제목에 반영하고, '# [리서치 핵심 트렌드] 트렌드 분석 보고서' 형식으로 작성하세요. 본문은 변화의 흐름, 배경, 전망, 시사점을 중심으로 작성하세요.\n"
            "- 뉴스레터 유형이 실무 활용형이면 제공된 리서치 자료에서 확인되는 업무상 영향이나 대응 이슈를 제목에 반영하고, '# [리서치 핵심 업무 이슈] 실무 활용 보고서' 형식으로 작성하세요. 본문은 업무 활용성, 체크리스트, 실행 제안을 중심으로 작성하세요.\n"
            "- 제목의 대괄호 안 문구는 반드시 실제 리서치 내용에 맞게 구체적으로 바꾸세요.\n"
            "- 제목은 리서치 자료와 직접 관련된 핵심 키워드, 주요 사건, 대상, 변화 방향 중 최소 1개 이상을 포함해야 합니다.\n"
            "- 제목을 작성하기 전에 리서치 자료에서 가장 중요한 키워드 1~3개를 내부적으로 선택한 뒤, 그 키워드를 반영해 제목을 작성하세요. 내부 선택 과정은 출력하지 마세요.\n"
            "- 유형 설명이 별도로 제공되면 해당 설명을 우선 반영하되, 위의 공통 작성 규칙은 반드시 지키세요."


    )
    # 생성 타입(type_code: summary/trend/practical …)이 지정되면 그 스타일을 반영합니다.
    #   스타일 설명(description)은 newsletter_type 테이블에서 type_code 로 조회합니다.
    type_code = state.get("type_code")

    
    if type_code:
        row = fetch_one("SELECT description FROM newsletter_type WHERE code = %s", (type_code,))
        type_desc = (row or {}).get("description") or ""
        if type_desc:
            system += f" 이 뉴스레터는 다음 스타일로 작성한다: {type_desc}"
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
                state.get("type_code"),
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