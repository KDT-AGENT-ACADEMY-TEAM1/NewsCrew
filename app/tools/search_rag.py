"""도구(Tool): 주가 조회 — @tool 데코레이터 (박희순_과제소스의 exchange_info 참고).

LLM이 종목 정보가 필요하다고 판단하면 종목코드(티커)로 호출합니다.
"""
from __future__ import annotations

from langchain_core.tools import tool

#테스트2

@tool
def search_rag(topic: str) -> str:
    """
    지식 베이스에서 정보를 검색하는 도구입니다. (시뮬레이션)
    topic: 검색할 주제
    """
    print(f"\n[Tool 가동] search_rag -> {topic}")
    # 간단한 지식 베이스 시뮬레이션
    knowledge_base = {
        "파이썬": "파이썬은 1991년 귀도 반 로섬이 개발한 고급 프로그래밍 언어입니다. 문법이 간단하고 읽기 쉬워 초보자에게 인기가 높습니다.",
        "머신러닝": "머신러닝은 컴퓨터가 명시적으로 프로그래밍되지 않고도 데이터에서 패턴을 학습하는 AI의 한 분야입니다.",
        "langchain": "LangChain은 LLM 애플리케이션 개발을 위한 프레임워크로, 다양한 컴포넌트를 체인으로 연결할 수 있습니다."
    }
    
    topic_lower = topic.lower()
    for key, value in knowledge_base.items():
        if key in topic_lower:
            return f"'{topic}'에 대한 정보: {value}"