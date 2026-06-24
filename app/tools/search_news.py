"""도구(Tool): 뉴스 검색 — @tool 데코레이터 (박희순_과제소스의 get_weather 참고).

LLM이 "이 도구가 필요하다"고 판단하면 자동으로 호출합니다.
"""
from __future__ import annotations

from langchain_core.tools import tool


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
