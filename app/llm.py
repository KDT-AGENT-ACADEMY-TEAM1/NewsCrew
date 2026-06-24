"""LLM 공통 도우미 — 모든 노드가 함께 쓰는 'AI 호출' 부분만 모았습니다.

[이 파일이 하는 일]
  ① LLM 준비   : ChatOpenAI(...) 객체를 한 번 만들어 재사용 (_get_llm)
  ② 글 요청    : system(역할 지시) + user(요청) → '글' 받기 (ask_ai)

OPENAI_API_KEY 가 없으면(또는 호출 실패 시) 자동으로 '가짜(Mock) 모드'로 떨어져
키 없이도 앱 흐름은 그대로 동작합니다.

도구를 붙인 LLM(bind_tools)이 필요하면 with_tools=True 로 부르세요.
도구 목록은 app/tools 패키지에서 가져옵니다.
"""
from __future__ import annotations

import os
from functools import lru_cache

from langchain_core.messages import HumanMessage, SystemMessage

from .tools import TOOLS_LIST


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
