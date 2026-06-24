"""노드(Node) 모음 — 각 노드는 같은 폴더의 개별 파일에 있습니다.

  - research.py : research_node + route_after_research (리서치 에이전트/갈림길)
  - tools.py    : tools_node                          (도구 실행)
  - write.py    : write_node                          (초안 작성)
  - review.py   : review_node                         (품질 검수)
  - send.py     : send_node                           (발송)

graph.py 가 이 파일을 통해 모든 노드를 한 번에 가져갑니다.
새 노드를 추가하려면 이 폴더에 파일을 만들고 아래 import 에 등록하세요.
"""
from __future__ import annotations

from .research_old import research_node, route_after_research
from .review import review_node
from .send import send_node
from .tools import tools_node
from .write import write_node

__all__ = [
    "research_node",
    "route_after_research",
    "tools_node",
    "write_node",
    "review_node",
    "send_node",
]
