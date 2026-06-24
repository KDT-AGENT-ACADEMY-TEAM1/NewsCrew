"""뉴스레터 관심분야(카테고리) 카탈로그 — DB 테이블 interest_category 에 대응.

DB 연동 전 단계라, 학습용으로 카테고리 목록을 코드에 담아 둡니다.
나중에 interest_category 테이블로 교체하더라도 같은 형태
(code / name / keywords / 대분류-소분류 계층)를 유지하면 화면 코드는 그대로 둘 수 있습니다.

  - code     : 분야 코드(영문 슬러그)        ↔ interest_category.code
  - name     : 분야 표시명                   ↔ interest_category.name
  - keywords : 수집·검색용 키워드 배열(JSON) ↔ interest_category.keywords
  - children : 하위 분야(소분류)             ↔ parent_id 로 연결되는 자식들
"""
from __future__ import annotations

# 대분류 → 소분류(children) 2단계 계층.
CATEGORIES = [
    {
        "code": "ai_tech", "name": "AI/기술",
        "children": [
            {"code": "generative_ai", "name": "생성형 AI", "keywords": ["생성형 AI", "LLM", "AI 에이전트"]},
            {"code": "semiconductor", "name": "반도체",    "keywords": ["반도체", "HBM", "파운드리"]},
            {"code": "robotics",      "name": "로봇/자동화", "keywords": ["로봇", "자동화", "휴머노이드"]},
        ],
    },
    {
        "code": "economy", "name": "경제/금융",
        "children": [
            {"code": "stock",      "name": "증시/주식",  "keywords": ["증시", "코스피", "나스닥"]},
            {"code": "crypto",     "name": "가상자산",   "keywords": ["비트코인", "이더리움", "가상자산"]},
            {"code": "realestate", "name": "부동산",     "keywords": ["부동산", "금리", "분양"]},
        ],
    },
    {
        "code": "mobility", "name": "모빌리티",
        "children": [
            {"code": "ev",         "name": "전기차",    "keywords": ["전기차", "배터리", "충전 인프라"]},
            {"code": "autonomous", "name": "자율주행",  "keywords": ["자율주행", "ADAS"]},
        ],
    },
    {
        "code": "industry", "name": "산업/IT",
        "children": [
            {"code": "it_platform", "name": "IT/플랫폼", "keywords": ["플랫폼", "클라우드", "SaaS"]},
            {"code": "game",        "name": "게임",      "keywords": ["게임", "콘솔", "e스포츠"]},
        ],
    },
]


def _flatten(categories: list[dict]) -> list[dict]:
    """'대분류 > 소분류' 형태의 평면 목록으로 펼칩니다. (화면 선택용)"""
    rows: list[dict] = []
    for top in categories:
        for child in top.get("children", []):
            rows.append({
                "code": child["code"],
                "name": child["name"],
                "label": f"{top['name']} > {child['name']}",
                "keywords": child["keywords"],
            })
    return rows


# 코드에 박아 둔 기본 카탈로그(폴백). DB를 못 읽을 때 이걸 씁니다.
FLAT_CATEGORIES = _flatten(CATEGORIES)


def _load_from_db() -> list[dict] | None:
    """interest_category 테이블에서 활성 카테고리를 읽어 평면 목록으로 만듭니다.

    DB 미연결/테이블 없음/데이터 없음이면 None 을 돌려줘 코드 카탈로그로 폴백하게 합니다.
    keywords 컬럼은 JSON 이라 문자열로 오므로 json.loads 로 풀어 줍니다.
    """
    import json

    try:
        from .db import fetch_all
        rows = fetch_all(
            "SELECT c.code, c.name, c.keywords, p.name AS parent_name "
            "FROM interest_category c "
            "LEFT JOIN interest_category p ON c.parent_id = p.id "
            "WHERE c.is_active = 1 AND c.parent_id IS NOT NULL "
            "ORDER BY c.sort_order, c.id"
        )
    except Exception as e:   # 드라이버 미설치/접속 실패 등 → 폴백
        print(f"[categories] DB 로드 실패 → 코드 카탈로그 사용: {e}")
        return None

    if not rows:
        return None

    flat: list[dict] = []
    for r in rows:
        raw = r.get("keywords")
        try:
            keywords = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except (ValueError, TypeError):
            keywords = []
        parent = r.get("parent_name") or "기타"
        flat.append({
            "code": r["code"],
            "name": r["name"],
            "label": f"{parent} > {r['name']}",
            "keywords": keywords,
        })
    return flat


def get_flat_categories() -> list[dict]:
    """화면이 쓸 카테고리 목록. DB를 먼저 시도하고, 안 되면 코드 카탈로그로 폴백."""
    return _load_from_db() or FLAT_CATEGORIES


def keywords_for_labels(labels: list[str], catalog: list[dict] | None = None) -> list[str]:
    """선택한 카테고리 라벨들에서 키워드를 모아 중복 없이 돌려줍니다."""
    by_label = {row["label"]: row for row in (catalog or FLAT_CATEGORIES)}
    collected: list[str] = []
    for label in labels:
        row = by_label.get(label)
        if not row:
            continue
        for kw in row["keywords"]:
            if kw not in collected:
                collected.append(kw)
    return collected
