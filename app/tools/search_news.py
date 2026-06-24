"""도구(Tool): 뉴스 검색 — @tool 데코레이터 (박희순_과제소스의 get_weather 참고).

LLM이 "이 도구가 필요하다"고 판단하면 자동으로 호출합니다.
"""
from __future__ import annotations

from langchain_core.tools import tool
from langchain_tavily import TavilySearch
from dotenv import load_dotenv


search_web = TavilySearch(
        tavily_api_key="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",
        max_results=1,
        topic="news",
        include_answer=True,
        include_raw_content=False,
        include_images=False,
        search_depth="advanced"
    )
#def _get_reseach(topic:str):
  


@tool   
def search_news(topic: str) -> str:
    """키워드로 최신 뉴스/동향을 검색해 핵심 내용을 돌려줍니다."""
    print(f"\n[Tool 가동] search_news -> {topic}")
    load_dotenv()
    result_news = search_web.invoke(topic)
    #dict_keys(['query', 'follow_up_questions', 'answer', 'images', 'results', 'response_time', 'request_id'])
     
    if not result_news['answer'] or len(result_news['results']) < 1:
        return f"'{topic}'의 뉴스 정보를 찾을 수 없습니다."
    
    print(result_news['results'])
    return (
        f"'{topic}' 관련 최신 동향(검색 결과 예시):\n"
        f"- 시장이 빠르게 성장하며 투자가 늘고 있습니다.\n"
        f"- 신규 기술·서비스 출시가 이어지고 있습니다.\n"
        f"- 정책/규제 논의도 활발해지는 추세입니다."
    )
