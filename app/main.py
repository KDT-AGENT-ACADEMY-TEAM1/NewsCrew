"""FastAPI 서버.

역할
- 구독 키워드 관리 (등록/조회)
- 뉴스레터 생성 트리거 (그래프 실행 -> 승인 대기 지점까지)
- 생성된 초안 조회
- 승인(approve) / 반려(reject) API
"""
from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .graph import graph

app = FastAPI(title="맞춤형 뉴스레터 자동 검수 에이전트", version="0.1.0")

# 데모용 인메모리 저장소 (실제로는 DB 사용)
_subscriptions: dict[str, list[str]] = {}


# --------------------------- 요청/응답 모델 ---------------------------
class SubscriptionIn(BaseModel):
    user_id: str
    keywords: list[str]


class GenerateIn(BaseModel):
    user_id: str


class RejectIn(BaseModel):
    feedback: str


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _snapshot(thread_id: str) -> dict:
    """현재 그래프 상태를 직렬화해서 반환."""
    state = graph.get_state(_config(thread_id))
    if not state.values:
        raise HTTPException(404, "해당 thread_id 를 찾을 수 없습니다.")
    v = state.values
    return {
        "thread_id": thread_id,
        "status": v.get("status"),
        "keywords": v.get("keywords"),
        "draft": v.get("draft"),
        "review": v.get("review"),
        "revision_count": v.get("revision_count"),
        "final": v.get("final"),
        # interrupt 로 멈춰 다음 실행 노드가 남아있으면 승인 대기 상태
        "awaiting_approval": bool(state.next) and v.get("status") == "awaiting_approval",
        "next": list(state.next),
    }


# ------------------------------- 구독 키워드 -------------------------------
@app.post("/subscriptions")
def set_subscription(body: SubscriptionIn):
    """구독 키워드 등록/갱신."""
    _subscriptions[body.user_id] = body.keywords
    return {"user_id": body.user_id, "keywords": body.keywords}


@app.get("/subscriptions/{user_id}")
def get_subscription(user_id: str):
    if user_id not in _subscriptions:
        raise HTTPException(404, "구독 정보가 없습니다.")
    return {"user_id": user_id, "keywords": _subscriptions[user_id]}


# ----------------------------- 뉴스레터 생성 -----------------------------
@app.post("/newsletters/generate")
def generate(body: GenerateIn):
    """그래프를 실행하여 승인 대기(interrupt) 지점까지 진행."""
    keywords = _subscriptions.get(body.user_id)
    if not keywords:
        raise HTTPException(400, "먼저 /subscriptions 로 키워드를 등록하세요.")

    thread_id = uuid.uuid4().hex[:12]
    initial: dict = {
        "keywords": keywords,
        "revision_count": 0,
        "max_revisions": 2,
        "status": "researching",
    }
    # interrupt_before=["send"] 때문에 send 직전에서 자동으로 멈춤
    graph.invoke(initial, _config(thread_id))
    return _snapshot(thread_id)


@app.get("/newsletters/{thread_id}")
def get_newsletter(thread_id: str):
    """현재 초안 및 상태 조회."""
    return _snapshot(thread_id)


# ------------------------------ 승인 / 반려 ------------------------------
@app.post("/newsletters/{thread_id}/approve")
def approve(thread_id: str):
    """사람이 승인 -> 중단된 그래프를 재개하여 발송(send) 실행."""
    snap = _snapshot(thread_id)
    if not snap["awaiting_approval"]:
        raise HTTPException(409, "승인 대기 상태가 아닙니다.")
    # None 입력 = 멈춘 지점부터 그대로 재개
    graph.invoke(None, _config(thread_id))
    return _snapshot(thread_id)


@app.post("/newsletters/{thread_id}/reject")
def reject(thread_id: str, body: RejectIn):
    """사람이 반려 -> 피드백을 반영해 작성 단계부터 다시 실행."""
    snap = _snapshot(thread_id)
    if not snap["awaiting_approval"]:
        raise HTTPException(409, "승인 대기 상태가 아닙니다.")

    cfg = _config(thread_id)
    # 사람 피드백 주입 + 다음 실행 노드를 write 로 강제 지정하여 복귀
    graph.update_state(
        cfg,
        {"human_feedback": body.feedback, "status": "writing"},
        as_node="research",  # research -> write 엣지를 타고 작성 단계로 재진입
    )
    graph.invoke(None, cfg)  # 다시 write -> review -> (승인 대기) 까지 진행
    return _snapshot(thread_id)


@app.get("/")
def root():
    return {
        "service": "맞춤형 뉴스레터 자동 검수 에이전트",
        "flow": "키워드 등록 -> 생성 -> (검수 복귀 루프) -> 승인 대기 -> 승인/반려",
        "docs": "/docs",
    }
