"""각 단계를 담당하는 에이전트(노드) — 학습용 심플 버전.

[에이전트(노드)]란?
  '상태(메모지)'를 입력으로 받아 → 자기 일을 하고 → 바뀐 부분만 돌려주는 함수입니다.
  돌려준 값은 자동으로 메모지에 합쳐집니다.

  예)  def write_node(state):  ...  return {"draft": "...", "status": "reviewing"}
       → state["draft"], state["status"] 가 갱신됩니다.

여기서는 진짜 AI(LLM) 호출을 비워 두고, 'Mock(가짜)' 결과로 동작합니다.
실제 AI를 붙이려면 각 노드의  # TODO: 여기 채우기  부분을 채우세요.
"""
from __future__ import annotations

from .state import NewsletterState, ReviewResult


# ==========================================================================
# 공통 도우미 — AI(LLM) 호출
#   OPENAI_API_KEY 가 있으면 진짜 LLM을, 없으면 가짜 텍스트를 돌려줍니다.
# ==========================================================================
import os
from functools import lru_cache


@lru_cache(maxsize=1)
def _get_llm():
    """LLM 객체를 한 번만 만들어 재사용합니다. (키/패키지 없으면 None)"""
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    except Exception as e:   # 패키지 미설치 등 → 가짜 모드로 폴백
        print(f"[AI] LLM 준비 실패 → 가짜 모드로 동작합니다: {e}")
        return None


def ask_ai(system: str, user: str) -> str:
    """AI에게 system(역할 지시) + user(요청)를 보내고 답변 글을 받습니다.

    OPENAI_API_KEY 가 설정돼 있으면 진짜 LLM을 호출하고,
    없으면(또는 호출 실패 시) 기존처럼 가짜 답변을 돌려줍니다.
    """
    llm = _get_llm()
    if llm is None:
        return f"[가짜 AI 답변] {user[:200]}"
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        return llm.invoke(
            [SystemMessage(content=system), HumanMessage(content=user)]
        ).content
    except Exception as e:   # 네트워크/쿼터 오류 등 → 가짜 모드로 폴백
        print(f"[AI] 호출 실패 → 가짜 답변으로 대체: {e}")
        return f"[가짜 AI 답변] {user[:200]}"


# ==========================================================================
# STEP 2. 리서치 노드 — 키워드 관련 자료 수집·정리
# ==========================================================================
def research_node(state: NewsletterState) -> NewsletterState:
    keywords = state.get("keywords", [])
    kw = ", ".join(keywords)
    print(f"[리서치] 자료 조사 중: {kw}")

    # TODO: 여기 채우기 —— ask_ai() 로 진짜 리서치를 시키려면 아래 가짜 부분을 교체.
    research = (
        f"'{kw}' 관련 핵심 동향(예시):\n"
        f"1. 시장이 빠르게 성장하고 있습니다.\n"
        f"2. 신규 기술/서비스가 계속 나오고 있습니다.\n"
        f"3. 사람들의 관심도가 크게 늘었습니다."
    )

    # 바뀐 부분만 돌려줍니다 → 다음 단계는 '작성(writing)'
    return {"research": research, "status": "writing"}


# ==========================================================================
# STEP 3. 작성 노드 — 리서치를 바탕으로 초안 작성
# ==========================================================================
def write_node(state: NewsletterState) -> NewsletterState:
    research = state.get("research", "")
    revision = state.get("revision_count", 0)

    # 검수에서 미달이었거나, 사람이 반려했으면 그 피드백을 반영
    feedback = _pick_feedback(state)
    print(f"[작성] 초안 작성 중 ({revision}회차)"
          + (f" / 피드백 반영: {feedback}" if feedback else ""))

    # TODO: 여기 채우기 —— ask_ai() 로 진짜 작성을 시키려면 아래 가짜 부분을 교체.
    draft = (
        "# 이번 주 뉴스레터\n\n"
        "안녕하세요! 맞춤 뉴스레터입니다.\n\n"
        f"## 주요 소식\n{research}\n\n"
        "## 마무리\n다음 호에서 또 찾아뵐게요."
    )
    if feedback:
        draft += f"\n\n> (수정 반영: {feedback})"

    # [학습용 장치] 첫 초안은 일부러 짧게 만들어 '검수 미달 → 재작성' 루프를 보여줍니다.
    if revision == 0 and not feedback:
        draft = "# 뉴스레터\n\n소식입니다.\n"   # 너무 짧음 → 검수 탈락 예정

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


# ==========================================================================
# STEP 4. 검수 노드 — 초안 품질 판정 (여기 결과로 다음 길이 갈립니다)
# ==========================================================================
def review_node(state: NewsletterState) -> NewsletterState:
    draft = state.get("draft", "")
    revision = state.get("revision_count", 0)
    print(f"[검수] 품질 검증 중 ({revision}회차)")

    # TODO: 여기 채우기 —— ask_ai() 로 진짜 검수를 시키려면 아래 '간단 규칙'을 교체.
    #   (진짜로 할 땐 AI가 점수/통과여부를 글로 답하므로, 그 글에서 숫자를 뽑아내야 합니다)
    review = _simple_review(draft)

    print(f"[검수] 결과: {'통과' if review['passed'] else '미달'} (점수 {review['score']})")
    return {
        "review": review,
        "revision_count": revision + 1,
        # 통과면 승인 대기로, 미달이면 다시 작성으로
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


# ==========================================================================
# STEP 6. 발송 노드 — 사람 승인 후 실행됨
# ==========================================================================
def send_node(state: NewsletterState) -> NewsletterState:
    draft = state.get("draft", "")
    print("[발송] 승인 완료 → 발송 및 이력 저장")

    # TODO: 여기 채우기 —— 실제 이메일 발송(예: AWS SES) + DB 저장.
    #   지금은 그냥 '발송됨' 상태로만 바꿉니다.
    return {"final": draft, "status": "sent"}
