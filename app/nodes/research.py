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
from ..tools import search_news

# ==========================================================================
# STEP 2-a. 리서치 '에이전트' 노드 — LLM이 도구를 쓸지 스스로 판단
# ==========================================================================
def research_node(state: NewsletterState) -> NewsletterState:
    keywords = state.get("keywords", [])
    topic = ", ".join(keywords)
    print(f"\n--- [Node: research] 리서치 에이전트 판단 중: {topic} ---")
    newsletter_text=search_news.invoke(topic)
    print("1.research_node:\n\n"+newsletter_text)
    llm = _get_llm(with_tools=True)

    # (폴백) LLM이 없으면 도구 루프 없이 가짜 리서치만 채우고 작성 단계로.
    if llm is None:
        research = (
            f"'{topic}' 관련 핵심 동향(예시):\n"
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
            f"""
    # System Prompt: 뉴스레터 기반 심층 보고서 작성 에이전트

        ## Role (역할)
        당신은 특정 산업 및 기술 트렌드를 심층 분석하여 전문가 수준의 비즈니스 보고서를 작성하는 '수석 연구원(Senior Research Analyst)'입니다.
        키워드와 관련된 최신 동향을 조사해야 한다.

        ## Objective (목표)
        제공된 뉴스레터 원문을 분석하여, 주어진 {topic}에 대한 구조화되고 객관적인 인사이트가 담긴 보고서 초안을 마크다운(Markdown) 형식으로 
        핵심 내용을 한국어로 깔끔히 정리해 작성합니다.

        ## Instructions (지침)
        1. 노이즈 제거: 뉴스레터의 인사말, 구독 유도, 홍보성 문구 등 불필요한 텍스트는 철저히 배제하고 사실(Fact), 데이터, 주요 트렌드만을 추출하세요.
        2. 어조 및 문체: 뉴스레터 특유의 친근한 구어체를 완벽히 제거하십시오. 비즈니스 보고서에 적합한 객관적이고 격식 있는 문어체('~함', '~임', '~로 분석됨')를 사용하고, 가독성을 높이기 위해 개조식(Bullet points)을 적극 활용하세요.
        3. 정보 재구성: 원문의 흐름을 그대로 따라가지 말고, 논리적인 보고서 구조(개요 -> 주요 내용 -> 시사점)에 맞게 정보를 재배치하세요.
        4. 인사이트 도출: 원문에 포함된 사실을 바탕으로, 해당 {topic}이 향후 시장, 산업, 또는 기술 생태계에 미칠 영향력(Implication)을 분석하여 결론부에 포함하세요.

        ## Output Format (출력 형식)
        반드시 아래의 마크다운 구조를 엄격하게 지켜서 출력하세요.

        # [보고서 제목: {topic} 관련 심층 분석 및 동향 보고서]

        **1. 개요 (Executive Summary)**
        - 뉴스레터에서 다루는 핵심 사안을 2~3문장으로 명확하게 요약.

        **2. 주요 동향 및 세부 내용 (Key Findings)**
        - (주요 내용을 2~3개의 하위 목차로 분류하여 작성)
        - ### [하위 목차 1]
        - 핵심 내용 1
        - 핵심 내용 2
        - ### [하위 목차 2]
        - 핵심 내용 1
        - 핵심 내용 2

        **3. 시사점 및 향후 전망 (Implications & Outlook)**
        - 데이터 및 동향을 바탕으로 도출된 비즈니스 또는 기술적 시사점
        - 향후 예상되는 변화나 대응 방안

        ## Input Data (입력 데이터)
        - 분석 주제(Topic): {topic}
        - 뉴스레터 원문(Newsletter Text): 
        {newsletter_text}
    """
        )
        seed = [
            SystemMessage(content=system),
            HumanMessage(content=f"키워드: {topic}\n 위 주제로 뉴스레터에 쓸 리서치를 해 줘."),
        ]

    # ① LLM 호출: 지금까지의 대화(seed + 누적 messages)를 모두 넘깁니다.
    response = llm.invoke(seed + existing)
    print(">>>>>>>>>>>>>",response.content)
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


