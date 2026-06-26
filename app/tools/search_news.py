"""도구(Tool): 뉴스 검색 — @tool 데코레이터 (박희순_과제소스의 get_weather 참고).

LLM이 "이 도구가 필요하다"고 판단하면 자동으로 호출합니다.
"""
from __future__ import annotations

from langchain_core.tools import tool
from langchain_tavily import TavilySearch
from dotenv import load_dotenv


search_web = TavilySearch(
        tavily_api_key="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",
        max_results=10,
        topic="news",
        include_answer=True,
        include_raw_content=False,
        include_images=False,
        search_depth="advanced"
    )

  


@tool   
def search_news(topic: str) -> str:
    """키워드로 최신 뉴스/동향을 검색해 핵심 내용을 돌려줍니다."""
    print(f"\n[Tool 가동] search_news -> {topic}")
   
    result_news = search_web.invoke(topic)
    #dict_keys(['query', 'follow_up_questions', 'answer', 'images', 'results', 'response_time', 'request_id'])
     
    if not result_news['answer'] or len(result_news['results']) < 1:
        return f"'{topic}'의 뉴스 정보를 찾을 수 없습니다."
    # 결과 요약

    summary = f"'{topic}' 관련 최신 뉴스 요약:\n\n"
    for i, result in enumerate(result_news['results'][:7], 1):
        title = result.get('title', '제목 없음')
        content = result.get('content', '내용 없음')
        url = result.get('url', '')
        
        summary += f"{i}. {title}\n"
        summary += f"   {content}...\n"
        summary += f"   {url}\n\n"
   
    return summary
  