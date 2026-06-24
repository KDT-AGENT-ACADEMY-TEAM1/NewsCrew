"""FastAPI 백엔드 — DB 처리와 LangGraph(생성/승인/반려)를 모두 담당합니다.

화면(web/streamlit_app.py)은 이 API를 HTTP로 호출만 합니다.
실행:  python run_api.py   (또는 uvicorn app.main:app --reload)
문서:  http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import categories as cat
from . import db
from . import subscribers as sub
from .graph import graph
from .keywords import extract_keywords

app = FastAPI(title="뉴스레터 자동 생성 에이전트 API", version="1.0.0")


# ==========================================================================
# 그래프(LangGraph) 헬퍼
# ==========================================================================
def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _read_state(thread_id: str) -> dict:
    """그래프 상태를 화면이 쓰기 좋은 형태로 정리합니다."""
    state = graph.get_state(_config(thread_id))
    v = state.values
    return {
        "thread_id": thread_id,
        "status": v.get("status"),
        "keywords": v.get("keywords", []),
        "draft": v.get("draft", ""),
        "review": v.get("review", {}),
        "revision_count": v.get("revision_count", 0),
        "awaiting_approval": "send" in state.next,
    }


# ==========================================================================
# 키워드 추출 (LLM)
# ==========================================================================
class TextIn(BaseModel):
    text: str


@app.post("/keywords/extract")
def api_extract_keywords(body: TextIn):
    return {"keywords": extract_keywords(body.text)}


# ==========================================================================
# 관심 카테고리 (interest_category)
# ==========================================================================
class CategoryIn(BaseModel):
    code: str
    name: str
    keywords: list[str] = []
    parent_id: Optional[int] = None
    description: Optional[str] = None
    sort_order: int = 0


@app.get("/categories/flat")
def api_categories_flat():
    """화면 선택용 평면 목록(키워드 포함)."""
    return cat.get_flat_categories()


@app.get("/categories")
def api_categories_list():
    """관리용 전체 목록."""
    return cat.list_categories()


@app.post("/categories")
def api_categories_create(b: CategoryIn):
    new_id = cat.create_category(b.code, b.name, b.keywords, b.parent_id,
                                 b.description, b.sort_order)
    return {"id": new_id}


@app.delete("/categories/{cid}")
def api_categories_delete(cid: int):
    return {"deleted": cat.delete_category(cid)}


# ==========================================================================
# 뉴스레터 생성 타입 (newsletter_type)
# ==========================================================================
class TypeIn(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    sort_order: int = 0


@app.get("/types")
def api_types_list(active_only: int = 0):
    return db.list_newsletter_types(active_only=bool(active_only))


@app.post("/types")
def api_types_create(b: TypeIn):
    return {"id": db.create_newsletter_type(b.code, b.name, b.description, b.sort_order)}


@app.delete("/types/{tid}")
def api_types_delete(tid: int):
    return {"deleted": db.delete_newsletter_type(tid)}


# ==========================================================================
# 메일링리스트 (subscriber)
# ==========================================================================
class SubscriberIn(BaseModel):
    email: str
    name: Optional[str] = None
    category_ids: list[int] = []


@app.get("/subscribers")
def api_subscribers_list():
    return sub.list_subscribers()


@app.post("/subscribers")
def api_subscribers_create(b: SubscriberIn):
    return {"id": sub.create_subscriber(b.email, b.name, b.category_ids)}


@app.delete("/subscribers/{sid}")
def api_subscribers_delete(sid: int):
    return {"deleted": sub.delete_subscriber(sid)}


# ==========================================================================
# 환경설정 (app_setting)
# ==========================================================================
class SettingsIn(BaseModel):
    values: dict


@app.get("/settings")
def api_settings_get():
    return db.get_settings()


@app.put("/settings")
def api_settings_update(b: SettingsIn):
    for k, v in b.values.items():
        db.update_setting(k, v)
    return {"updated": len(b.values)}


# ==========================================================================
# 뉴스레터(보고서) — 목록/상세/생성/승인/반려/삭제
# ==========================================================================
class GenerateIn(BaseModel):
    keywords: list[str]
    category_id: Optional[int] = None
    type_code: Optional[str] = None
    max_revisions: Optional[int] = None


class RejectIn(BaseModel):
    feedback: str = ""


@app.get("/newsletters")
def api_newsletters_list(category_id: Optional[int] = None):
    sql = (
        "SELECT n.thread_id, n.title, n.draft, n.status, n.review_score, n.created_at, "
        "       n.news_type, c.name AS category "
        "FROM newsletter n "
        "LEFT JOIN interest_category c ON c.id = n.category_id "
    )
    if category_id is not None:
        rows = db.fetch_all(sql + "WHERE n.category_id = %s ORDER BY n.created_at DESC, n.id DESC",
                            (category_id,))
    else:
        rows = db.fetch_all(sql + "ORDER BY n.created_at DESC, n.id DESC")
    for r in rows:                       # JSON 직렬화를 위해 날짜를 문자열로
        r["created_at"] = str(r["created_at"])
    return rows


@app.get("/newsletters/{thread_id}")
def api_newsletters_get(thread_id: str):
    """상세: 이번 세션 그래프에 살아 있으면 그 상태(승인/반려 가능), 없으면 DB(읽기전용)."""
    state = graph.get_state(_config(thread_id))
    if state.values:
        snap = _read_state(thread_id)
        snap["_live"] = True
        return snap
    row = db.fetch_one(
        "SELECT thread_id, title, draft, status, review_score, review_feedback, revision_count "
        "FROM newsletter WHERE thread_id = %s",
        (thread_id,),
    )
    if not row:
        raise HTTPException(404, "보고서를 찾을 수 없습니다.")
    return {
        "thread_id": row["thread_id"],
        "status": row["status"],
        "draft": row["draft"] or "",
        "review": {"score": row["review_score"], "feedback": row["review_feedback"]},
        "revision_count": row["revision_count"] or 0,
        "awaiting_approval": False,
        "_live": False,
    }


@app.post("/newsletters/generate")
def api_newsletters_generate(b: GenerateIn):
    """그래프를 처음부터 실행 → 리서치·작성·검수 후 '승인 대기'에서 멈춤."""
    thread_id = uuid.uuid4().hex[:12]
    max_rev = b.max_revisions if b.max_revisions is not None else db.get_int_setting("max_revisions", 2)
    initial = {"keywords": b.keywords, "revision_count": 0,
               "max_revisions": max_rev, "status": "researching"}
    if b.category_id is not None:
        initial["category_id"] = b.category_id
    if b.type_code:
        initial["type_code"] = b.type_code
    graph.invoke(initial, _config(thread_id))
    return _read_state(thread_id)


@app.post("/newsletters/{thread_id}/approve")
def api_newsletters_approve(thread_id: str):
    graph.invoke(None, _config(thread_id))       # 멈춘 지점부터 재개 → 발송
    return _read_state(thread_id)


@app.post("/newsletters/{thread_id}/reject")
def api_newsletters_reject(thread_id: str, b: RejectIn):
    cfg = _config(thread_id)
    graph.update_state(cfg, {"human_feedback": b.feedback, "status": "writing"},
                       as_node="research")
    graph.invoke(None, cfg)
    return _read_state(thread_id)


@app.delete("/newsletters/{thread_id}")
def api_newsletters_delete(thread_id: str):
    return {"deleted": db.execute("DELETE FROM newsletter WHERE thread_id = %s", (thread_id,))}


@app.get("/")
def root():
    return {"service": "뉴스레터 자동 생성 에이전트 API", "docs": "/docs"}
