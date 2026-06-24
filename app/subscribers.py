"""메일링리스트(구독자) — subscriber / subscriber_interest 테이블 관리.

구독자(이메일)와 관심분야(interest_category)는 다대다(N:M) 관계라,
연결 테이블 subscriber_interest 에 (구독자, 분야) 쌍을 행으로 저장합니다.

  - list_subscribers()  : 구독자 목록 + 관심분야명 모아 보기
  - create_subscriber() : 구독자 추가 + 관심분야 연결 (한 트랜잭션)
  - delete_subscriber() : 구독자 삭제 (연결내역은 FK CASCADE 로 자동 정리)
"""
from __future__ import annotations


def list_subscribers() -> list[dict]:
    """구독자 목록을 조회합니다. 관심분야명은 쉼표로 이어 한 칸에 담아 줍니다.

    각 항목: {id, email, name, is_active, categories: "AI/기술, 과학"}
    """
    from .db import fetch_all
    return fetch_all(
        "SELECT s.id, s.email, s.name, s.is_active, "
        "       GROUP_CONCAT(c.name ORDER BY c.sort_order, c.id SEPARATOR ', ') AS categories "
        "FROM subscriber s "
        "LEFT JOIN subscriber_interest si ON si.subscriber_id = s.id "
        "LEFT JOIN interest_category c     ON c.id = si.category_id "
        "GROUP BY s.id, s.email, s.name, s.is_active "
        "ORDER BY s.id"
    )


def create_subscriber(
    email: str,
    name: str | None = None,
    category_ids: list[int] | None = None,
) -> int:
    """구독자를 추가하고 선택한 관심분야들을 연결합니다. (새 구독자 id 반환)

    구독자 INSERT 와 관심분야 INSERT 를 하나의 연결(트랜잭션)에서 처리해,
    중간에 실패하면 통째로 롤백되도록 합니다. (이메일 중복이면 예외 발생)
    """
    from .db import connection
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO subscriber (email, name) VALUES (%s, %s)",
                (email, name),
            )
            subscriber_id = cur.lastrowid
            for category_id in category_ids or []:
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
