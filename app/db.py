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
