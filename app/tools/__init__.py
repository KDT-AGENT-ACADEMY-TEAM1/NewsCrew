"""도구(Tool) 모음 — 각 도구는 같은 폴더의 개별 파일에 있습니다.

  - search_news.py  : 뉴스 검색
  - search_stock.py : 주가 조회

[새 도구를 추가하려면]
  1) 이 폴더에 새 파일을 만들고 @tool 함수를 작성하세요. (search_news.py 참고)
  2) 아래 import 줄과 TOOLS_LIST / TOOLS_MAP 에 한 줄씩 등록하세요.

TOOLS_LIST  : LLM에게 알려 줄 도구 목록 (llm.bind_tools 에 사용)
TOOLS_MAP   : 이름 → 함수 매핑 (tools_node 가 실제 실행할 때 사용)
"""
from __future__ import annotations

from .search_news import search_news
from .search_stock import search_stock
from .search_rag import search_rag
# 도구 목록 + 이름→함수 매핑 (소스의 tools_list / tools_map 패턴)
TOOLS_LIST = [search_news, search_stock,search_rag]
TOOLS_MAP = {"search_news": search_news, "search_stock": search_stock,"search_rag":search_rag}

__all__ = ["search_news", "search_stock","search_rag", "TOOLS_LIST", "TOOLS_MAP"]
