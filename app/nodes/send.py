"""[노드] 발송 — 사람 승인 후 실행됨."""
from __future__ import annotations

from ..state import NewsletterState


# ==========================================================================
# STEP 6. 발송 노드 — 사람 승인 후 실행됨
# ==========================================================================
def send_node(state: NewsletterState) -> NewsletterState:
    draft = state.get("draft", "")
    print("[발송] 승인 완료 → 발송 및 이력 저장")

    # TODO: 여기 채우기 —— 실제 이메일 발송(예: AWS SES) + DB 저장.
    return {"final": draft, "status": "sent"}
