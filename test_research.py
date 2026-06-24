from app.nodes import research_node
from app.tools import search_news

def main():
    print("--- [테스트 시작] ---")
    
    # 1. 뉴스 검색 도구 단독 테스트
    topic = "AI"
    print(f"[{topic}] 키워드로 뉴스 검색 중...")
    
    # ==========================================
    # 수정된 부분: .invoke() 메서드를 사용합니다.
    # (도구가 정의된 파라미터 이름이 "query"라고 가정)
    # ==========================================
    try:
        web_search_result = search_news.invoke({"query": topic})
    except Exception as e:
        # 혹시 도구의 인자 이름이 "query"가 아니라 단일 문자열을 받는 구조라면 
        # 아래처럼 실행해야 할 수도 있습니다.
        print(f"딕셔너리 전달 실패, 문자열로 재시도: {e}")
        web_search_result = search_news.invoke(topic)

    print(">> 뉴스 검색 결과:\n", web_search_result)
    print("--------------------")

    # 2. 리서치 노드 테스트
    initial_state = {
        "keywords": ["오픈소스 LLM", "LangGraph"],
        "messages": [],
        "status": "init",
        "research": ""
    }
    
    print("[리서치 노드] 초기 상태로 실행 중...")
    node_result = research_node(initial_state)
    print(">> 리서치 노드 실행 결과:\n", node_result)

if __name__ == "__main__":
    main()