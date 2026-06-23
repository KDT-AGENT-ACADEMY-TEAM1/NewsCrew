"""각 단계를 담당하는 에이전트(노드) — 학습용 심플 버전.

[에이전트(노드)]란?
  '상태(메모지)'를 입력으로 받아 → 자기 일을 하고 → 바뀐 부분만 돌려주는 함수입니다.
  돌려준 값은 자동으로 메모지에 합쳐집니다.

  예)  def write_node(state):  ...  return {"draft": "...", "status": "reviewing"}
       → state["draft"], state["status"] 가 갱신됩니다.

[이 파일에서 보여 주는 3가지 패턴] (박희순_과제소스 참고)
  ① LLM 사용     : ChatOpenAI(...).invoke(messages)
  ② Tool(도구)   : @tool 로 함수를 도구로 등록 → LLM 이 필요할 때 호출
  ③ Tool 실행 루프: 'agent ⇄ tools' 를 should_continue 조건부 분기로 반복

OPENAI_API_KEY 가 없으면(또는 호출 실패 시) 자동으로 '가짜(Mock) 모드'로 떨어져
키 없이도 앱 흐름은 그대로 동작합니다.
"""
from __future__ import annotations

import os
from functools import lru_cache

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from .state import NewsletterState, ReviewResult


# ==========================================================================
# 공통 도우미 — LLM 준비 (박희순_과제소스의 ChatOpenAI 사용법 참고)
# ==========================================================================
def _model_name() -> str:
    """사용할 모델 이름. (환경변수 OPENAI_MODEL 로 바꿀 수 있음)"""
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


@lru_cache(maxsize=2)
def _get_llm(with_tools: bool):
    """LLM 객체를 한 번만 만들어 재사용합니다. (키/패키지 없으면 None)

    with_tools=True 면 도구를 붙인(bind_tools) LLM을 돌려줍니다.
    """
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model=_model_name(),
            temperature=0.4,
            api_key=os.getenv("OPENAI_API_KEY"),
        )
        # ② 도구 사용: bind_tools 로 'LLM이 부를 수 있는 도구 목록'을 알려 줍니다.
        return llm.bind_tools(TOOLS_LIST) if with_tools else llm
    except Exception as e:   # 패키지 미설치 등 → 가짜 모드로 폴백
        print(f"[AI] LLM 준비 실패 → 가짜 모드로 동작합니다: {e}")
        return None


def ask_ai(system: str, user: str) -> str:
    """AI에게 system(역할 지시) + user(요청)를 보내고 '글'을 받습니다. (도구 없음)

    OPENAI_API_KEY 가 있으면 진짜 LLM을, 없으면(또는 실패 시) 가짜 답변을 돌려줍니다.
    """
    llm = _get_llm(with_tools=False)
    if llm is None:
        return f"[가짜 AI 답변] {user[:200]}"
    try:
        return llm.invoke(
            [SystemMessage(content=system), HumanMessage(content=user)]
        ).content
    except Exception as e:   # 네트워크/쿼터 오류 등 → 가짜 모드로 폴백
        print(f"[AI] 호출 실패 → 가짜 답변으로 대체: {e}")
        return f"[가짜 AI 답변] {user[:200]}"


# ==========================================================================
# 도구(Tool) 정의 — @tool 데코레이터 (박희순_과제소스의 get_weather/exchange_info 참고)
#   LLM이 "이 도구가 필요하다"고 판단하면 자동으로 호출합니다.
# ==========================================================================
@tool
def search_news(query: str) -> str:
    """키워드로 최신 뉴스/동향을 검색해 핵심 내용을 돌려줍니다."""
    print(f"\n[Tool 가동] search_news -> {query}")
    # TODO: 여기 채우기 —— 실제 뉴스 검색 API(네이버/구글/Tavily 등)로 교체.
    #   지금은 학습용으로 키워드를 엮은 '가짜 검색 결과'를 돌려줍니다.
    return (
        f"'{query}' 관련 최신 동향(검색 결과 예시):\n"
        f"- 시장이 빠르게 성장하며 투자가 늘고 있습니다.\n"
        f"- 신규 기술·서비스 출시가 이어지고 있습니다.\n"
        f"- 정책/규제 논의도 활발해지는 추세입니다."
    )


@tool
def search_stock(symbol: str) -> str:
    """주식 종목코드(티커)로 현재 주가·등락 정보를 조회합니다.

    예) 애플=AAPL, 테슬라=TSLA, 삼성전자=005930.KS, SK하이닉스=000660.KS
    """
    print(f"\n[Tool 가동] search_stock -> {symbol}")
    import requests   # 도구가 쓰일 때만 불러옵니다

    symbol = symbol.strip().upper()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    try:
        resp = requests.get(
            url,
            params={"range": "1d", "interval": "1d"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=8,
        )
        resp.raise_for_status()
        meta = resp.json()["chart"]["result"][0]["meta"]
    except Exception as e:   # 네트워크/잘못된 티커 등 → 안내 메시지로 폴백
        print(f"[search_stock] 조회 실패: {e}")
        return f"'{symbol}' 주가를 가져오지 못했습니다. (종목코드를 확인하거나 잠시 후 다시 시도)"

    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    currency = meta.get("currency", "")
    name = meta.get("longName") or meta.get("shortName") or symbol

    if price is None:
        return f"'{symbol}' 종목을 찾을 수 없습니다. 종목코드를 확인해 주세요."

    line = f"[{name} ({symbol})] 현재가 {price:,} {currency}"
    if prev:
        diff = price - prev
        rate = diff / prev * 100 if prev else 0
        sign = "▲" if diff > 0 else ("▼" if diff < 0 else "-")
        line += f" / 전일대비 {sign} {abs(diff):,.2f} ({rate:+.2f}%)"
    return line


# 도구 목록 + 이름→함수 매핑 (소스의 tools_list / tools_map 패턴)
TOOLS_LIST = [search_news, search_stock]
TOOLS_MAP = {"search_news": search_news, "search_stock": search_stock}


# ==========================================================================
# STEP 2-a. 리서치 '에이전트' 노드 — LLM이 도구를 쓸지 스스로 판단
#   (소스의 agent_node 패턴: SystemMessage + 누적 messages 를 LLM에 전달)
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
# STEP 2-b. 도구 실행 노드 — LLM이 요청한 도구를 실제로 호출
#   (소스의 tool_node 패턴: tool_calls 순회 → ToolMessage 로 결과 반환)
# ==========================================================================
def tools_node(state: NewsletterState) -> NewsletterState:
    print("\n--- [Node: tools] 에이전트의 지시로 도구를 실행합니다 ---")
    last_message = (state.get("messages") or [])[-1]

    tool_outputs: list = []
    results: list[str] = []
    for tool_call in getattr(last_message, "tool_calls", []) or []:
        name = tool_call["name"]
        print(f"LLM이 요청한 도구 이름: {name}")
        result = TOOLS_MAP[name].invoke(tool_call["args"])
        results.append(f"[{name}] {result}")
        # 도구 결과는 반드시 ToolMessage(같은 tool_call_id)로 돌려줘야 LLM이 이어 갑니다.
        tool_outputs.append(
            ToolMessage(content=str(result), tool_call_id=tool_call["id"], name=name)
        )

    prev = state.get("tool_results", "")
    new_results = "\n".join(results)
    combined = f"{prev}\n{new_results}".strip() if prev else new_results
    return {"messages": tool_outputs, "tool_results": combined}


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


# ==========================================================================
# STEP 4. 검수 노드 — 초안 품질 판정 (여기 결과로 다음 길이 갈립니다)
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


# ==========================================================================
# STEP 6. 발송 노드 — 사람 승인 후 실행됨
# ==========================================================================
def send_node(state: NewsletterState) -> NewsletterState:
    draft = state.get("draft", "")
    print("[발송] 승인 완료 → 발송 및 이력 저장")

    # TODO: 여기 채우기 —— 실제 이메일 발송(예: AWS SES) + DB 저장.
    return {"final": draft, "status": "sent"}
