"""FastAPI 백엔드 — DB 처리와 LangGraph(생성/승인/반려)를 모두 담당합니다.

화면(web/streamlit_app.py)은 이 API를 HTTP로 호출만 합니다.
실행:  python run_api.py   (또는 uvicorn app.main:app --reload)
문서:  http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import json
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import categories as cat
from . import db
from . import knowledge
from . import mailer
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
        "title": v.get("title") or "",
        "draft": v.get("draft", ""),
        "review": v.get("review", {}),
        "revision_count": v.get("revision_count", 0),
        "awaiting_approval": "send" in state.next,
    }


def _sends(thread_id: str) -> list[dict]:
    """발송 이력(누구에게·언제)을 조회합니다."""
    rows = db.fetch_all(
        "SELECT email, name, sent_at FROM newsletter_send "
        "WHERE thread_id = %s ORDER BY id",
        (thread_id,),
    )
    for r in rows:
        r["sent_at"] = str(r["sent_at"])
    return rows


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
    checkpoints: list[str] = []


class CheckpointsIn(BaseModel):
    checkpoints: list[str] = []


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
                                 b.description, b.sort_order, b.checkpoints)
    return {"id": new_id}


@app.put("/categories/{cid}/checkpoints")
def api_categories_checkpoints(cid: int, b: CheckpointsIn):
    return {"updated": cat.update_checkpoints(cid, b.checkpoints)}


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
# 이메일 템플릿 (email_template)
# ==========================================================================
class TemplateIn(BaseModel):
    code: str
    name: str
    html: str = ""


@app.get("/templates")
def api_templates_list():
    return db.list_templates()


@app.post("/templates")
def api_templates_create(b: TemplateIn):
    return {"id": db.create_template(b.code, b.name, b.html)}


@app.delete("/templates/{tid}")
def api_templates_delete(tid: int):
    return {"deleted": db.delete_template(tid)}


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


class StatusIn(BaseModel):
    status: str


@app.get("/newsletters")
def api_newsletters_list(category_id: Optional[int] = None):
    sql = (
        "SELECT n.thread_id, n.title, n.draft, n.status, n.review_score, n.created_at, "
        "       n.news_type, c.name AS category, COALESCE(nt.name, n.news_type) AS type_label "
        "FROM newsletter n "
        "LEFT JOIN interest_category c  ON c.id = n.category_id "
        "LEFT JOIN newsletter_type nt   ON nt.code = n.news_type "
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
    """상세: 그래프에 살아 있으면 그 상태, 없으면 DB. 둘 다 발송 전이면 승인/반려 가능."""
    state = graph.get_state(_config(thread_id))
    if state.values:
        snap = _read_state(thread_id)
        snap["_live"] = True
        code = state.values.get("type_code")
        snap["news_type"] = code
        snap["type_label"] = db.get_type_name(code)
        snap["sends"] = _sends(thread_id)
        return snap
    row = db.fetch_one(
        "SELECT thread_id, title, draft, status, review_score, review_feedback, "
        "       revision_count, news_type "
        "FROM newsletter WHERE thread_id = %s",
        (thread_id,),
    )
    if not row:
        raise HTTPException(404, "보고서를 찾을 수 없습니다.")
    return {
        "thread_id": row["thread_id"],
        "status": row["status"],
        "title": row["title"] or "",
        "draft": row["draft"] or "",
        "review": {"score": row["review_score"], "feedback": row["review_feedback"]},
        "revision_count": row["revision_count"] or 0,
        "news_type": row["news_type"],
        "type_label": db.get_type_name(row["news_type"]),
        # 발송 전(sent 아님)이면 세션과 무관하게 승인/반려 가능
        "awaiting_approval": row["status"] != "sent",
        "_live": False,
        "sends": _sends(thread_id),
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
def api_newsletters_approve(thread_id: str, template_code: Optional[str] = None):
    """승인 → 발송. 그래프가 살아 있으면 재개하고, DB 상태를 발송완료로 동기화한 뒤
    그 카테고리에 관심 있는 구독자에게 (선택한 템플릿으로) 메일을 보냅니다(이력 기록)."""
    cfg = _config(thread_id)
    state = graph.get_state(cfg)
    if state.values and "send" in state.next:
        graph.invoke(None, cfg)                  # 그래프 발송 단계 실행

    # DB 상태를 발송완료로 동기화 (live/old 공통)
    n = db.execute("UPDATE newsletter SET status = 'sent', final_body = draft "
                   "WHERE thread_id = %s", (thread_id,))
    if not n:
        raise HTTPException(404, "보고서를 찾을 수 없습니다.")

    # 카테고리 관심 구독자에게 메일 발송 + 발송 이력 기록
    #   메일 제목 = "카테고리명 + 뉴스레터" (카테고리 없으면 그냥 '뉴스레터')
    row = db.fetch_one("SELECT n.category_id, n.title, n.draft, c.name AS category "
                       "FROM newsletter n "
                       "LEFT JOIN interest_category c ON c.id = n.category_id "
                       "WHERE n.thread_id = %s", (thread_id,))
    subject = f"{row['category']} 뉴스레터" if row.get("category") else "뉴스레터"
    mailer.send_newsletter(thread_id, row["category_id"], subject, row["draft"] or "",
                           template_code=template_code)
    return api_newsletters_get(thread_id)


@app.post("/newsletters/{thread_id}/reject")
def api_newsletters_reject(thread_id: str, b: RejectIn):
    """반려 → 재작성. 살아 있으면 그래프 재개, 없으면 저장된 정보로 같은 thread_id 재생성."""
    cfg = _config(thread_id)
    state = graph.get_state(cfg)
    if state.values and "send" in state.next:
        graph.update_state(cfg, {"human_feedback": b.feedback, "status": "writing"},
                           as_node="research")
        graph.invoke(None, cfg)
        return api_newsletters_get(thread_id)

    # 과거 보고서: DB에 저장된 키워드/카테고리/타입으로 다시 생성 (피드백 반영)
    row = db.fetch_one(
        "SELECT keywords, category_id, news_type FROM newsletter WHERE thread_id = %s",
        (thread_id,),
    )
    if not row:
        raise HTTPException(404, "보고서를 찾을 수 없습니다.")
    try:
        keywords = json.loads(row["keywords"]) if row["keywords"] else []
    except (ValueError, TypeError):
        keywords = []
    initial = {"keywords": keywords, "revision_count": 0,
               "max_revisions": db.get_int_setting("max_revisions", 2),
               "status": "researching", "human_feedback": b.feedback}
    if row["category_id"]:
        initial["category_id"] = row["category_id"]
    if row["news_type"]:
        initial["type_code"] = row["news_type"]
    graph.invoke(initial, cfg)
    return api_newsletters_get(thread_id)


@app.put("/newsletters/{thread_id}/status")
def api_newsletters_status(thread_id: str, b: StatusIn):
    """상태 값을 직접 수정합니다. (목록의 상태 선택박스용)"""
    n = db.execute("UPDATE newsletter SET status = %s WHERE thread_id = %s",
                   (b.status, thread_id))
    if not n:
        raise HTTPException(404, "보고서를 찾을 수 없습니다.")
    return {"updated": n}


@app.delete("/newsletters/{thread_id}")
def api_newsletters_delete(thread_id: str):
    return {"deleted": db.execute("DELETE FROM newsletter WHERE thread_id = %s", (thread_id,))}


# ==========================================================================
# 내부 자료 (Chroma 벡터DB)
# ==========================================================================
@app.get("/knowledge/status")
def api_knowledge_status():
    """색인된 내부자료 조각 수 + 내부 자료 검색 미리보기용 상태."""
    return {"count": knowledge.count(), "dirs": ["data/관련규정", "data/관련자료"]}


@app.post("/knowledge/reindex")
def api_knowledge_reindex():
    """내부 자료를 다시 읽어 재색인합니다(force)."""
    return {"count": knowledge.init_chroma(force=True)}


@app.get("/knowledge/search")
def api_knowledge_search(q: str, k: int = 3):
    """내부 자료 검색 (미리보기/확인용)."""
    return knowledge.search(q, k)


@app.get("/")
def root():
    return {"service": "뉴스레터 자동 생성 에이전트 API", "docs": "/docs"}
