"""[노드] 리서치 에이전트 — LLM이 도구를 쓸지 스스로 판단.

  (소스의 agent_node 패턴: SystemMessage + 누적 messages 를 LLM에 전달)

  - research_node        : 리서치 에이전트(LLM 호출 / 도구 사용 판단)
  - route_after_research : 도구를 더 쓸지(tools) / 작성으로 갈지(write) 갈림길 판단

실제 도구 '실행'은 옆 파일 tools.py(tools_node)가 담당합니다.
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from ..llm import _get_llm
from ..state import NewsletterState


# ==========================================================================
# STEP 2-a. 리서치 '에이전트' 노드 — LLM이 도구를 쓸지 스스로 판단
# ==========================================================================
def research_node(state: NewsletterState) -> NewsletterState:
    keywords = state.get("keywords", [])
    kw = ", ".join(keywords)
    print(f"\n--- [Node: research] 리서치 에이전트 판단 중: {kw} ---")

    llm = _get_llm(with_tools=True)

    # (폴백) LLM이 없으면 도구 루프 없이 가짜 리서치만 채우고 작성 단계로.
    if llm is None:
        research = (
            f"'{kw}' 관련 핵심 동향(예시):\n"
            f"1. 시장이 빠르게 성장하고 있습니다.\n"
            f"2. 신규 기술/서비스가 계속 나오고 있습니다.\n"
            f"3. 사람들의 관심도가 크게 늘었습니다."
        )
        return {"research": research, "status": "writing"}

    # 첫 진입이면 system + 사용자 요청 메시지를 만들어 대화를 시작합니다.
    existing = state.get("messages") or []
    seed: list = []
    if not existing:
        system = (
            "너는 뉴스레터용 리서치 담당이다. "
            "키워드와 관련된 최신 동향을 조사해야 한다. "
            "최신 뉴스가 필요하면 search_news 도구를, "
            "주가·증시 같은 종목 정보가 필요하면 search_stock 도구(종목코드 사용)를 호출하라. "
            "충분히 모았다면 핵심 내용을 한국어로 깔끔히 정리해 답하라."
        )
        seed = [
            SystemMessage(content=system),
            HumanMessage(content=f"키워드: {kw}\n위 주제로 뉴스레터에 쓸 리서치를 해 줘."),
        ]

    # ① LLM 호출: 지금까지의 대화(seed + 누적 messages)를 모두 넘깁니다.
    response = llm.invoke(seed + existing)

    update: NewsletterState = {"messages": seed + [response], "status": "researching"}
    # 도구 호출 없이 '글'로 답했다면 그게 곧 리서치 결과입니다.
    if getattr(response, "content", ""):
        update["research"] = response.content
    return update


# ==========================================================================
# STEP 2-c. 조건부 분기 — 도구를 더 쓸지 / 작성 단계로 갈지
#   (소스의 should_continue 패턴: 마지막 메시지에 tool_calls 있으면 도구로)
# ==========================================================================
def route_after_research(state: NewsletterState) -> str:
    messages = state.get("messages") or []
    if messages and getattr(messages[-1], "tool_calls", None):
        print("[의사결정] 도구 호출 요청 -> 'tools' 노드로 이동")
        return "tools"
    print("[의사결정] 리서치 완료 -> 'write' 노드로 이동")
    return "write"


