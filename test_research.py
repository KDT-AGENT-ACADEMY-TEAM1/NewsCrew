from app.nodes import research_node
from app.tools import search_news

def main():
    print("--- [테스트 시작] ---")
    
    # 1. 뉴스 검색 도구 단독 테스트
    topic = "인공지능"
    print(f"[{topic}] 키워드로 뉴스 검색 중...")
    
    # ==========================================
    # 수정된 부분: .invoke() 메서드를 사용합니다.
    # (도구가 정의된 파라미터 이름이 "query"라고 가정)
    # ==========================================
    web_search_result = search_news.invoke( topic)
    

    print(">> 뉴스 검색 결과:\n", web_search_result)
    print("--------------------")
    # 2. 리서치 노드 테스트
    initial_state = {
        "keywords": [topic],
        "messages": [],
        "status": "init",
        "research": web_search_result
    }
    
    print("[리서치 노드] 초기 상태로 실행 중...")
    node_result = research_node(initial_state)
    print(">> 리서치 노드 실행 결과:\n", node_result)

if __name__ == "__main__":
    main()