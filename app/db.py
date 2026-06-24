"""공통 데이터베이스 접속 모듈 — 프로젝트 전체가 함께 쓰는 DB 연결 도구.

[이 파일이 하는 일]
  ① 접속 정보 한 곳 관리 (mydatabase / root / 1234)
  ② 연결 만들기            : get_connection()  /  with connection() as conn
  ③ 자주 쓰는 조회·실행    : fetch_all(), fetch_one(), execute()

접속 정보는 환경변수로 덮어쓸 수 있습니다. (없으면 아래 기본값 사용)
  DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME

사용 예)
  from app.db import fetch_all, execute
  rows = fetch_all("SELECT * FROM interest_category WHERE is_active=1")
  execute("INSERT INTO interest_category (code, name) VALUES (%s, %s)", ("ai", "AI"))
"""
from __future__ import annotations

import os
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor


# --------------------------------------------------------------------------
# 접속 정보 (환경변수 우선, 없으면 기본값)
# --------------------------------------------------------------------------
def _db_config() -> dict:
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", "1234"),
        "database": os.getenv("DB_NAME", "mydatabase"),
        "charset": "utf8mb4",
        "cursorclass": DictCursor,   # 결과를 dict(컬럼명: 값) 로 받습니다
    }


# --------------------------------------------------------------------------
# 연결 만들기
# --------------------------------------------------------------------------
def get_connection() -> pymysql.connections.Connection:
    """새 DB 연결을 만들어 돌려줍니다. (직접 닫아야 함 — 보통은 connection() 사용 권장)"""
    return pymysql.connect(**_db_config())


@contextmanager
def connection():
    """with 블록이 끝나면 자동으로 commit/rollback 후 연결을 닫는 안전한 연결.

    예)
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    """
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --------------------------------------------------------------------------
# 자주 쓰는 조회/실행 도우미
# --------------------------------------------------------------------------
def fetch_all(sql: str, params: tuple | dict | None = None) -> list[dict]:
    """여러 행을 조회해 [{컬럼: 값}, ...] 형태로 돌려줍니다."""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def fetch_one(sql: str, params: tuple | dict | None = None) -> dict | None:
    """한 행만 조회해 {컬럼: 값} 으로 돌려줍니다. (없으면 None)"""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()


def execute(sql: str, params: tuple | dict | None = None) -> int:
    """INSERT/UPDATE/DELETE 실행. INSERT면 새 행 id, 그 외엔 영향받은 행 수를 돌려줍니다."""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.lastrowid or cur.rowcount


def ping() -> bool:
    """DB 접속이 되는지 빠르게 확인합니다. (실패 시 False)"""
    try:
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception as e:
        print(f"[DB] 접속 확인 실패: {e}")
        return False


# --------------------------------------------------------------------------
# 초기화 — 기본 테이블 생성 + 기본 카테고리 시드
#   app/__init__.py 에서 한 번 호출합니다. (DB가 없거나 막혀 있어도 앱은 계속 동작)
# --------------------------------------------------------------------------

# 카테고리가 하나도 없을 때 넣어 줄 기본 분야들 (interest_category)
DEFAULT_CATEGORIES = [
    {
        "code": "ai",
        "name": "AI/생성형AI",
        "keywords": [
            "ChatGPT", "Claude", "Gemini", "OpenAI", "Anthropic",
            "생성형 AI", "LLM", "AI 에이전트", "LangChain",
            "LangGraph", "RAG", "MCP"
        ]
    },
    {
        "code": "tech",
        "name": "IT/기술",
        "keywords": [
            "클라우드", "개발자 기술", "오픈소스", "사이버보안",
            "데이터사이언스", "머신러닝", "딥러닝", "반도체",
            "로봇", "디지털전환"
        ]
    },
    {
        "code": "economy",
        "name": "경제/금융",
        "keywords": [
            "증시", "금리", "환율", "부동산",
            "금융", "재테크", "경제정책", "가상자산"
        ]
    },
    {
        "code": "startup",
        "name": "스타트업/비즈니스",
        "keywords": [
            "스타트업", "벤처투자", "기업전략",
            "마케팅", "브랜딩", "경영", "창업"
        ]
    },
    {
        "code": "education",
        "name": "교육/에듀테크",
        "keywords": [
            "교육정책", "에듀테크", "온라인교육",
            "AI교육", "고등교육", "대학", "학습분석"
        ]
    },
    {
        "code": "research",
        "name": "연구/학술",
        "keywords": [
            "논문", "학술연구", "연구성과",
            "연구비", "SCI", "학회", "연구윤리"
        ]
    },
    {
        "code": "mobility",
        "name": "모빌리티",
        "keywords": [
            "전기차", "배터리", "자율주행",
            "항공", "드론", "UAM", "스마트모빌리티"
        ]
    },
    {
        "code": "healthcare",
        "name": "헬스케어/바이오",
        "keywords": [
            "헬스케어", "바이오", "의료AI",
            "제약", "유전체", "디지털헬스"
        ]
    },
    {
        "code": "government",
        "name": "정부/공공",
        "keywords": [
            "정부정책", "공공데이터",
            "디지털플랫폼정부", "행정혁신",
            "법률", "규제"
        ]
    },
    {
        "code": "global",
        "name": "글로벌 동향",
        "keywords": [
            "미국", "중국", "일본", "유럽",
            "글로벌 경제", "해외 기술동향",
            "국제정세"
        ]
    }
]


def init_db() -> None:
    """기본 테이블이 없으면 만들고, 카테고리가 비어 있으면 기본값을 넣습니다.

    DB가 꺼져 있거나 권한이 없어도 앱이 죽지 않도록 예외를 삼킵니다(best-effort).
    """
    try:
        _create_tables_if_missing()
        _seed_default_categories()
    except Exception as e:
        print(f"[DB] 초기화 건너뜀(연결/권한 확인): {e}")


def _create_tables_if_missing() -> None:
    """schema.sql 의 CREATE TABLE 문(IF NOT EXISTS)을 실행해 기본 테이블을 만듭니다."""
    schema_path = os.path.join(os.path.dirname(__file__), os.pardir, "schema.sql")
    with open(schema_path, encoding="utf-8") as f:
        sql = f.read()
    # ';' 로 나눠 'CREATE TABLE' 이 든 문장만 실행 (schema.sql 은 IF NOT EXISTS 라 안전)
    statements = [s.strip() for s in sql.split(";") if "CREATE TABLE" in s.upper()]
    with connection() as conn:
        with conn.cursor() as cur:
            for stmt in statements:
                cur.execute(stmt)


def _seed_default_categories() -> None:
    """기본 카테고리 중 '코드가 아직 없는 것'만 골라 넣습니다. (이미 있으면 건드리지 않음)"""
    import json

    existing = {r["code"] for r in fetch_all("SELECT code FROM interest_category")}
    added = []
    for order, cat in enumerate(DEFAULT_CATEGORIES):
        if cat["code"] in existing:
            continue   # 같은 코드가 이미 있으면 중복 추가 안 함
        execute(
            "INSERT INTO interest_category (code, name, keywords, sort_order) "
            "VALUES (%s, %s, %s, %s)",
            (cat["code"], cat["name"],
             json.dumps(cat["keywords"], ensure_ascii=False), order),
        )
        added.append(cat["name"])
    if added:
        print(f"[DB] 기본 카테고리 추가: {', '.join(added)}")
