"""도구(Tool): 내부 자료 검색 — Chroma 벡터DB(관련규정/관련자료) 질의.

LLM이 회사 규정·정책·용어집·과거 뉴스레터 등 '내부 자료'가 필요하다고 판단하면 호출합니다.
"""
from __future__ import annotations

from langchain_core.tools import tool

from ..knowledge import search


@tool
def search_internal_docs(query: str) -> str:
    """회사 내부 자료(관련 규정·발송 정책·브랜드 규정·용어집·과거 뉴스레터 등)에서
    질의와 관련된 내용을 검색해 돌려준다. 뉴스레터 톤·규정·표현 기준이 필요할 때 사용한다."""
    print(f"\n[Tool 가동] search_internal_docs -> {query}")
    results = search(query, k=3)
    if not results:
        return "내부 자료에서 관련 내용을 찾지 못했습니다."
    return "\n\n".join(f"[내부자료: {r['source']}] {r['text']}" for r in results)
