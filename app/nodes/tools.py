"""[노드] 도구 실행 — LLM이 요청한 도구를 실제로 호출.

  (소스의 tool_node 패턴: tool_calls 순회 → ToolMessage 로 결과 반환)

어떤 도구가 있는지는 app/tools 패키지의 TOOLS_MAP 에서 가져옵니다.
도구 자체를 추가/수정하려면 app/tools 폴더의 파일을 고치세요.
"""
from __future__ import annotations

from langchain_core.messages import ToolMessage

from ..state import NewsletterState
from ..tools import TOOLS_MAP


# ==========================================================================
# STEP 2-b. 도구 실행 노드
# ==========================================================================
def tools_node(state: NewsletterState) -> NewsletterState:
    print("\n--- [Node: tools] 에이전트의 지시로 도구를 실행합니다 ---")
    last_message = (state.get("messages") or [])[-1]

    tool_outputs: list = []
    results: list[str] = []
    for tool_call in getattr(last_message, "tool_calls", []) or []:
        name = tool_call["name"]
        print(f"LLM이 요청한 도구 이름: {name}")
        result = TOOLS_MAP[name].invoke(tool_call["args"])
        results.append(f"[{name}] {result}")
        # 도구 결과는 반드시 ToolMessage(같은 tool_call_id)로 돌려줘야 LLM이 이어 갑니다.
        tool_outputs.append(
            ToolMessage(content=str(result), tool_call_id=tool_call["id"], name=name)
        )

    prev = state.get("tool_results", "")
    new_results = "\n".join(results)
    combined = f"{prev}\n{new_results}".strip() if prev else new_results
    return {"messages": tool_outputs, "tool_results": combined}
