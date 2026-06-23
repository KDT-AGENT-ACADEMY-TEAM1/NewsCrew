"""노드들을 연결해 흐름(그래프)을 만드는 곳 — 학습용 심플 버전.

[그래프]란?
  '어떤 노드 다음에 어떤 노드로 갈지'를 그린 지도입니다.
  화살표(edge)를 따라 상태(메모지)가 흘러갑니다.

이 파이프라인의 지도:
  START → research → (도구 필요?) ─┬─ tools → research (도구 결과 반영해 다시 판단)
                                  └─ write → review → (검수 결과로 갈림)
                                                        ├─ 통과/한도초과 → send → END
                                                        └─ 미달          → write (다시 작성)

세 가지 핵심 개념:
  1) 도구 루프(agent ⇄ tools): 리서치 LLM이 필요하면 도구를 부르고 결과를 받아 다시 판단
  2) 조건부 분기(Conditional Edge): 검수 결과/도구 호출 여부에 따라 다음 길을 다르게 정함
  3) 사람 승인(Human-in-the-loop): send 직전에 잠깐 멈춰 사람의 승인을 기다림
"""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .agents import (
    research_node,
    review_node,
    route_after_research,
    send_node,
    tools_node,
    write_node,
)
from .state import NewsletterState


# --------------------------------------------------------------------------
# 검수(review) 다음에 어디로 갈지 정하는 '갈림길 판단' 함수
#   돌려주는 문자열("write" / "send")이 곧 다음 행선지입니다.
# --------------------------------------------------------------------------
def route_after_review(state: NewsletterState) -> str:
    review = state.get("review", {})
    revision = state.get("revision_count", 0)
    max_rev = state.get("max_revisions", 2)

    if review.get("passed"):
        return "send"            # 통과 → 발송 단계로
    if revision < max_rev:
        return "write"           # 미달 + 아직 기회 있음 → 다시 작성
    return "send"                # 미달 + 한도 초과 → 사람이 직접 판단하도록 발송 단계로

    # TODO: 분기 규칙을 바꾸고 싶으면 위 if 들을 수정하세요.
    #   예) 점수가 70점 미만이면 무조건 다시 쓰게 하기 등


# --------------------------------------------------------------------------
# 그래프(지도)를 조립해서 돌려줍니다.
# --------------------------------------------------------------------------
def build_graph():
    # (1) 어떤 상태를 공유할지 알려주며 빌더 생성
    builder = StateGraph(NewsletterState)

    # (2) 노드 등록: ("이름", 실행할 함수)
    builder.add_node("research", research_node)   # 리서치 에이전트(LLM)
    builder.add_node("tools", tools_node)         # 도구 실행
    builder.add_node("write", write_node)
    builder.add_node("review", review_node)
    builder.add_node("send", send_node)

    # (3) 화살표 연결: a 다음 b
    builder.add_edge(START, "research")   # 시작 → 리서치

    # (4-a) 리서치 다음은 '갈림길': 도구가 필요하면 tools, 아니면 write
    builder.add_conditional_edges(
        "research",
        route_after_research,
        {"tools": "tools", "write": "write"},
    )
    builder.add_edge("tools", "research")  # 도구 실행 후 다시 리서치 에이전트로(결과 반영)
    builder.add_edge("write", "review")    # 작성 → 검수

    # (4-b) 검수 다음은 '갈림길': route_after_review 가 정한 곳으로 보냄
    builder.add_conditional_edges(
        "review",
        route_after_review,
        {"write": "write", "send": "send"},   # 판단 결과 → 실제 노드 매핑
    )
    builder.add_edge("send", END)         # 발송 → 끝

    # (5) 컴파일 + 두 가지 장치
    #   - checkpointer: 진행 상태를 저장(기억)해 두는 장치. 멈췄다 재개하려면 필요.
    #   - interrupt_before=["send"]: send 노드 '직전'에 자동으로 멈춤 → 사람 승인 대기
    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer, interrupt_before=["send"])


# 앱 전체에서 함께 쓰는 그래프 한 개를 미리 만들어 둡니다.
graph = build_graph()
