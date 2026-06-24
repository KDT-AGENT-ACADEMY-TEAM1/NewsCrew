"""뉴스레터 관심분야(카테고리) — interest_category 테이블에서 직접 읽어옵니다.

화면은 DB(interest_category)에 등록된 카테고리만 사용합니다.
(코드에 박아 두는 기본 목록은 두지 않습니다 — DB 가 유일한 출처)

각 카테고리 항목 형태:
  {
    "code":     분야 코드,            ↔ interest_category.code
    "name":     분야 표시명,          ↔ interest_category.name
    "label":    "대분류 > 소분류",     (상위가 없으면 표시명만)
    "keywords": ["LLM", ...],         ↔ interest_category.keywords (JSON)
  }
"""
from __future__ import annotations

import json


def _parse_keywords(raw) -> list[str]:
    """keywords 컬럼(JSON 문자열/리스트/None)을 파이썬 리스트로 풀어 줍니다."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return []
    return []


def get_flat_categories() -> list[dict]:
    """interest_category 에서 활성 카테고리를 읽어 평면 목록으로 돌려줍니다.

    - is_active = 1 인 항목만
    - 상위 분야가 있으면 라벨을 '대분류 > 소분류' 로, 없으면 표시명 그대로
    - keywords 는 JSON 컬럼이라 문자열로 오므로 json.loads 로 풀어 줍니다
    - DB 접속 실패/데이터 없음이면 빈 목록([]) 을 돌려줍니다
    """
    try:
        from .db import fetch_all
        rows = fetch_all(
            "SELECT c.id, c.code, c.name, c.keywords, c.checkpoints, p.name AS parent_name "
            "FROM interest_category c "
            "LEFT JOIN interest_category p ON c.parent_id = p.id "
            "WHERE c.is_active = 1 "
            "ORDER BY c.sort_order, c.id"
        )
    except Exception as e:   # 드라이버 미설치/접속 실패/테이블 없음 등
        print(f"[categories] DB 로드 실패: {e}")
        return []

    flat: list[dict] = []
    for r in rows:
        parent = r.get("parent_name")
        flat.append({
            "id": r["id"],
            "code": r["code"],
            "name": r["name"],
            "label": f"{parent} > {r['name']}" if parent else r["name"],
            "keywords": _parse_keywords(r.get("keywords")),
            "checkpoints": _parse_keywords(r.get("checkpoints")),
        })
    return flat


def keywords_for_labels(labels: list[str], catalog: list[dict]) -> list[str]:
    """선택한 카테고리 라벨들에서 키워드를 모아 중복 없이 돌려줍니다."""
    by_label = {row["label"]: row for row in catalog}
    collected: list[str] = []
    for label in labels:
        row = by_label.get(label)
        if not row:
            continue
        for kw in row["keywords"]:
            if kw not in collected:
                collected.append(kw)
    return collected


# ==========================================================================
# 카테고리 등록/조회/삭제 (interest_category 관리용)
# ==========================================================================
def list_categories() -> list[dict]:
    """모든 카테고리를 관리용으로 조회합니다. (비활성 포함, 상위 분야명 동봉)

    각 항목: {id, code, name, keywords, sort_order, is_active, parent_id, parent_name}
    """
    from .db import fetch_all
    rows = fetch_all(
        "SELECT c.id, c.code, c.name, c.keywords, c.checkpoints, c.sort_order, c.is_active, "
        "       c.parent_id, p.name AS parent_name "
        "FROM interest_category c "
        "LEFT JOIN interest_category p ON c.parent_id = p.id "
        "ORDER BY c.sort_order, c.id"
    )
    for r in rows:
        r["keywords"] = _parse_keywords(r.get("keywords"))
        r["checkpoints"] = _parse_keywords(r.get("checkpoints"))
    return rows


def create_category(
    code: str,
    name: str,
    keywords: list[str] | None = None,
    parent_id: int | None = None,
    description: str | None = None,
    sort_order: int = 0,
    checkpoints: list[str] | None = None,
) -> int:
    """카테고리 한 건을 추가하고, 새로 만들어진 id 를 돌려줍니다.

    keywords/checkpoints 는 JSON 컬럼이라 json.dumps 로 문자열로 만들어 넣습니다.
    code 가 이미 있으면 UNIQUE 제약으로 예외가 납니다(중복 방지).
    """
    from .db import execute
    return execute(
        "INSERT INTO interest_category "
        "(parent_id, code, name, description, keywords, checkpoints, sort_order) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (
            parent_id,
            code,
            name,
            description,
            json.dumps(keywords or [], ensure_ascii=False),
            json.dumps(checkpoints or [], ensure_ascii=False),
            sort_order,
        ),
    )


def update_checkpoints(cat_id: int, checkpoints: list[str]) -> int:
    """카테고리의 '주요 체크포인트'를 갱신합니다."""
    from .db import execute
    return execute(
        "UPDATE interest_category SET checkpoints = %s WHERE id = %s",
        (json.dumps(checkpoints or [], ensure_ascii=False), cat_id),
    )


def get_checkpoints(cat_id: int | None) -> list[str]:
    """카테고리 id 로 주요 체크포인트 목록을 가져옵니다. (없으면 [])"""
    if not cat_id:
        return []
    from .db import fetch_one
    row = fetch_one("SELECT checkpoints FROM interest_category WHERE id = %s", (cat_id,))
    return _parse_keywords(row.get("checkpoints")) if row else []


def delete_category(cat_id: int) -> int:
    """카테고리 한 건을 삭제합니다. (하위 분야의 parent_id 는 FK 규칙에 따라 NULL 로 바뀜)"""
    from .db import execute
    return execute("DELETE FROM interest_category WHERE id = %s", (cat_id,))
