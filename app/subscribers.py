"""메일링리스트(구독자) — subscriber / subscriber_interest 테이블 관리.

구독자(이메일)와 관심분야(interest_category)는 다대다(N:M) 관계라,
연결 테이블 subscriber_interest 에 (구독자, 분야) 쌍을 행으로 저장합니다.

  - list_subscribers()  : 구독자 목록 + 관심분야명 모아 보기
  - create_subscriber() : 구독자 추가 + 관심분야 연결 (한 트랜잭션)
  - delete_subscriber() : 구독자 삭제 (연결내역은 FK CASCADE 로 자동 정리)
"""
from __future__ import annotations


def list_subscribers() -> list[dict]:
    """구독자 목록을 조회합니다. 관심분야는 id 목록과 표시명을 함께 돌려줍니다.

    각 항목: {id, email, name, is_active, category_ids: [1,2], categories: "AI/기술, 과학"}
    """
    from .db import fetch_all
    rows = fetch_all(
        "SELECT s.id, s.email, s.name, s.is_active, "
        "       GROUP_CONCAT(c.id ORDER BY c.sort_order, c.id) AS category_ids, "
        "       GROUP_CONCAT(c.name ORDER BY c.sort_order, c.id SEPARATOR ', ') AS categories "
        "FROM subscriber s "
        "LEFT JOIN subscriber_interest si ON si.subscriber_id = s.id "
        "LEFT JOIN interest_category c     ON c.id = si.category_id "
        "GROUP BY s.id, s.email, s.name, s.is_active "
        "ORDER BY s.id"
    )
    for r in rows:
        r["category_ids"] = _parse_category_ids(r.get("category_ids"))
    return rows


def _parse_category_ids(raw) -> list[int]:
    if not raw:
        return []
    return [int(x) for x in str(raw).split(",") if str(x).strip().isdigit()]


def _normalize_category_ids(category_ids: list[int] | None) -> list[int]:
    """중복 제거된 관심분야 id 목록."""
    out: list[int] = []
    for cid in category_ids or []:
        if cid and cid not in out:
            out.append(int(cid))
    return out


def _validate_category_ids(category_ids: list[int]) -> None:
    """존재하는 관심분야 id 인지 확인합니다. (없으면 ValueError)"""
    if not category_ids:
        return
    from .db import fetch_all
    placeholders = ", ".join(["%s"] * len(category_ids))
    rows = fetch_all(
        f"SELECT id FROM interest_category WHERE id IN ({placeholders}) AND is_active = 1",
        tuple(category_ids),
    )
    found = {r["id"] for r in rows}
    missing = [cid for cid in category_ids if cid not in found]
    if missing:
        raise ValueError(f"존재하지 않는 관심분야 ID입니다: {missing}")


def create_subscriber(
    email: str,
    name: str | None = None,
    category_ids: list[int] | None = None,
) -> tuple[int, bool]:
    """구독자를 추가하고 선택한 관심분야들을 연결합니다.

    Returns:
        (subscriber_id, created) — created=False 이면 기존 이메일의 관심분야를 갱신했습니다.
    """
    from .db import connection, execute, fetch_one

    email = (email or "").strip().lower()
    if not email:
        raise ValueError("이메일은 필수입니다.")

    cat_ids = _normalize_category_ids(category_ids)
    _validate_category_ids(cat_ids)

    existing = fetch_one("SELECT id FROM subscriber WHERE email = %s", (email,))
    if existing:
        sid = existing["id"]
        if name:
            execute("UPDATE subscriber SET name = %s WHERE id = %s", (name.strip(), sid))
        update_subscriber_categories(sid, cat_ids)
        return sid, False

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO subscriber (email, name) VALUES (%s, %s)",
                (email, name),
            )
            subscriber_id = cur.lastrowid
            for category_id in cat_ids:
                cur.execute(
                    "INSERT INTO subscriber_interest (subscriber_id, category_id) "
                    "VALUES (%s, %s)",
                    (subscriber_id, category_id),
                )
    return subscriber_id, True


def update_subscriber_categories(subscriber_id: int, category_ids: list[int] | None) -> int:
    """구독자의 관심분야(여러 개)를 갱신합니다."""
    from .db import connection, fetch_one

    if not fetch_one("SELECT id FROM subscriber WHERE id = %s", (subscriber_id,)):
        raise ValueError("구독자를 찾을 수 없습니다.")

    cat_ids = _normalize_category_ids(category_ids)
    _validate_category_ids(cat_ids)

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM subscriber_interest WHERE subscriber_id = %s",
                (subscriber_id,),
            )
            for category_id in cat_ids:
                cur.execute(
                    "INSERT INTO subscriber_interest (subscriber_id, category_id) "
                    "VALUES (%s, %s)",
                    (subscriber_id, category_id),
                )
    return subscriber_id


def delete_subscriber(subscriber_id: int) -> int:
    """구독자 한 명을 삭제합니다. (subscriber_interest 의 연결내역도 CASCADE 로 함께 삭제)"""
    from .db import execute
    return execute("DELETE FROM subscriber WHERE id = %s", (subscriber_id,))
