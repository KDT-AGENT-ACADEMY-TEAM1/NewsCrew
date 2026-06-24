"""FastAPI 백엔드 호출용 HTTP 클라이언트 — 화면(Streamlit)은 이 함수들만 씁니다.

DB/LangGraph 처리는 전부 FastAPI(app/main.py)에서 합니다.
백엔드 주소는 환경변수 API_BASE 로 바꿀 수 있습니다. (기본 http://127.0.0.1:8000)
"""
from __future__ import annotations

import os

import requests

BASE = os.getenv("API_BASE", "http://127.0.0.1:80")
_TIMEOUT = 600   # 생성(그래프 실행)은 오래 걸릴 수 있어 넉넉히


def _get(path: str, **params):
    r = requests.get(BASE + path, params={k: v for k, v in params.items() if v is not None},
                     timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _post(path: str, payload: dict | None = None):
    r = requests.post(BASE + path, json=payload or {}, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _put(path: str, payload: dict | None = None):
    r = requests.put(BASE + path, json=payload or {}, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _delete(path: str):
    r = requests.delete(BASE + path, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


# --------------------------- 키워드 ---------------------------
def extract_keywords(text: str) -> list[str]:
    return _post("/keywords/extract", {"text": text}).get("keywords", [])


# --------------------------- 카테고리 ---------------------------
def get_flat_categories() -> list[dict]:
    return _get("/categories/flat")


def list_categories() -> list[dict]:
    return _get("/categories")


def create_category(code, name, keywords=None, parent_id=None, description=None,
                    sort_order=0, checkpoints=None):
    return _post("/categories", {"code": code, "name": name, "keywords": keywords or [],
                                 "parent_id": parent_id, "description": description,
                                 "sort_order": sort_order, "checkpoints": checkpoints or []})


def update_checkpoints(cid: int, checkpoints: list):
    return _put(f"/categories/{cid}/checkpoints", {"checkpoints": checkpoints})


def delete_category(cid: int):
    return _delete(f"/categories/{cid}")


def keywords_for_labels(labels: list[str], catalog: list[dict]) -> list[str]:
    """선택한 카테고리 라벨들에서 키워드를 모아 중복 없이 돌려줍니다. (순수 계산 — 호출 없음)"""
    by_label = {row["label"]: row for row in catalog}
    out: list[str] = []
    for label in labels:
        row = by_label.get(label)
        if not row:
            continue
        for kw in row["keywords"]:
            if kw not in out:
                out.append(kw)
    return out


# --------------------------- 생성 타입 ---------------------------
def list_newsletter_types(active_only: bool = False) -> list[dict]:
    return _get("/types", active_only=1 if active_only else 0)


def create_newsletter_type(code, name, description=None, sort_order=0):
    return _post("/types", {"code": code, "name": name,
                            "description": description, "sort_order": sort_order})


def delete_newsletter_type(tid: int):
    return _delete(f"/types/{tid}")


# --------------------------- 메일링리스트 ---------------------------
def list_subscribers() -> list[dict]:
    return _get("/subscribers")


def create_subscriber(email, name=None, category_ids=None):
    return _post("/subscribers", {"email": email, "name": name,
                                  "category_ids": category_ids or []})


def delete_subscriber(sid: int):
    return _delete(f"/subscribers/{sid}")


# --------------------------- 환경설정 ---------------------------
def get_settings() -> list[dict]:
    return _get("/settings")


def update_settings(values: dict):
    return _put("/settings", {"values": values})


# --------------------------- 뉴스레터(보고서) ---------------------------
def list_newsletters(category_id: int | None = None) -> list[dict]:
    return _get("/newsletters", category_id=category_id)


def get_newsletter(thread_id: str) -> dict | None:
    r = requests.get(BASE + f"/newsletters/{thread_id}", timeout=_TIMEOUT)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def generate(keywords, category_id=None, type_code=None) -> dict:
    return _post("/newsletters/generate", {"keywords": keywords, "category_id": category_id,
                                           "type_code": type_code})


def approve(thread_id: str) -> dict:
    return _post(f"/newsletters/{thread_id}/approve")


def reject(thread_id: str, feedback: str) -> dict:
    return _post(f"/newsletters/{thread_id}/reject", {"feedback": feedback})


def update_status(thread_id: str, status: str):
    return _put(f"/newsletters/{thread_id}/status", {"status": status})


def delete_newsletter(thread_id: str):
    return _delete(f"/newsletters/{thread_id}")
