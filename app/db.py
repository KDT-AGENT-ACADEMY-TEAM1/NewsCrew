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
        "code": "tech", "name": "IT/AI 분야",
        "keywords": ["인공지능(AI)", "생성형 AI", "머신러닝/딥러닝", "데이터사이언스",
                     "클라우드", "개발자 기술", "오픈소스", "사이버보안", "로봇", "반도체"],
        "checkpoints": ["기술의 핵심 개념과 변화 지점을 쉽게 설명했는가",
                        "실제 적용 사례나 제품을 제시했는가",
                        "전문 용어를 풀어 설명했는가",
                        "산업·일상에 미칠 영향을 짚었는가"],
    },
    {
        "code": "ai", "name": "AI/생성형AI",
        "keywords": ["ChatGPT", "Claude", "Gemini", "OpenAI", "Anthropic", "생성형 AI",
                     "LLM", "AI 에이전트", "LangChain", "LangGraph", "RAG", "MCP"],
        "checkpoints": ["어떤 모델·도구인지 명확히 했는가",
                        "구체적 활용 사례나 데모를 담았는가",
                        "한계·주의점도 균형 있게 다뤘는가",
                        "독자가 바로 시도할 포인트가 있는가"],
    },
    {
        "code": "economy", "name": "경제/금융",
        "keywords": ["증시", "금리", "부동산"],
        "checkpoints": ["수치·지표로 근거를 제시했는가",
                        "원인과 전망을 함께 설명했는가",
                        "투자·생활 관점의 시사점이 있는가"],
    },
    {
        "code": "mobility", "name": "모빌리티",
        "keywords": ["전기차", "배터리", "자율주행"],
        "checkpoints": ["기술·제품의 차별점을 설명했는가",
                        "시장·정책 동향을 짚었는가",
                        "상용화 시점이나 한계를 언급했는가"],
    },
    {
        "code": "science", "name": "과학",
        "keywords": ["우주", "에너지", "바이오"],
        "checkpoints": ["연구의 의미를 쉽게 풀었는가",
                        "실생활·산업 응용 가능성을 제시했는가",
                        "과장 없이 사실에 근거했는가"],
    },
    {
        "code": "startup", "name": "스타트업/비즈니스",
        "keywords": ["스타트업", "벤처투자", "기업전략", "마케팅", "브랜딩", "경영", "창업"],
        "checkpoints": ["비즈니스 모델·시장 기회를 설명했는가",
                        "투자·성장 지표를 제시했는가",
                        "실행 가능한 인사이트가 있는가"],
    },
    {
        "code": "education", "name": "교육/에듀테크",
        "keywords": ["교육정책", "에듀테크", "온라인교육", "AI교육", "고등교육", "대학", "학습분석"],
        "checkpoints": ["정책·기술이 교육 현장에 주는 변화를 설명했는가",
                        "교수·학생 등 대상별 시사점이 있는가",
                        "사례나 데이터를 제시했는가"],
    },
    {
        "code": "research", "name": "연구/학술",
        "keywords": ["논문", "학술연구", "연구성과", "연구비", "SCI", "학회", "연구윤리"],
        "checkpoints": ["연구 성과의 핵심을 정확히 전달했는가",
                        "방법·한계를 균형 있게 다뤘는가",
                        "후속 연구·활용 방향을 제시했는가"],
    },
    {
        "code": "healthcare", "name": "헬스케어/바이오",
        "keywords": ["헬스케어", "바이오", "의료AI", "제약", "유전체", "디지털헬스"],
        "checkpoints": ["의학적 근거를 정확히 전달했는가",
                        "환자·일반인 관점의 유의점을 담았는가",
                        "과장·오해 소지를 피했는가"],
    },
    {
        "code": "government", "name": "정부/공공",
        "keywords": ["정부정책", "공공데이터", "디지털플랫폼정부", "행정혁신", "법률", "규제"],
        "checkpoints": ["정책의 핵심과 적용 대상을 명확히 했는가",
                        "시행 시기·영향을 설명했는가",
                        "쟁점을 균형 있게 다뤘는가"],
    },
    {
        "code": "global", "name": "글로벌 동향",
        "keywords": ["미국", "중국", "일본", "유럽", "글로벌 경제", "해외 기술동향", "국제정세"],
        "checkpoints": ["국가별 동향을 비교·정리했는가",
                        "국내에 미칠 영향을 짚었는가",
                        "출처·맥락을 제시했는가"],
    },
]


def init_db() -> None:
    """기본 테이블이 없으면 만들고, 카테고리가 비어 있으면 기본값을 넣습니다.

    DB가 꺼져 있거나 권한이 없어도 앱이 죽지 않도록 예외를 삼킵니다(best-effort).
    """
    cfg = _db_config()
    print("=" * 60)
    print("[DB] 데이터베이스 초기화 시작")
    print(f"[DB] 접속 대상: {cfg['host']}:{cfg['port']}/{cfg['database']} (user={cfg['user']})")
    try:
        _create_tables_if_missing()    # schema.sql 의 모든 CREATE TABLE 실행
        print("[DB] (1/8) 테이블 확인/생성 완료")
        _ensure_newsletter_columns()   # 기존 DB 호환: 빠진 컬럼 보강
        print("[DB] (2/8) 컬럼 보강 확인 완료")
        _seed_default_categories()     # 기본 카테고리
        print("[DB] (3/8) 카테고리 시드 완료")
        _seed_settings()               # 환경설정 기본값
        print("[DB] (4/8) 환경설정 시드 완료")
        _seed_newsletter_types()       # 생성 타입 기본값
        print("[DB] (5/8) 생성 타입 시드 완료")
        _seed_review_checklist()       # 기본 검수 체크리스트
        print("[DB] (6/8) 검수 체크리스트 시드 완료")
        _seed_subscribers()            # 기본 구독자(메일링리스트)
        print("[DB] (7/8) 구독자 시드 완료")
        _seed_templates()              # 기본 이메일 템플릿
        print("[DB] (8/8) 이메일 템플릿 시드 완료")
        print("[DB] ✅ 데이터베이스 초기화 완료")
    except Exception as e:
        print(f"[DB] ❌ 초기화 건너뜀(연결/권한 확인): {e}")
    print("=" * 60)


def _create_tables_if_missing() -> None:
    """schema.sql 의 CREATE TABLE 문(IF NOT EXISTS)을 실행해 기본 테이블을 만듭니다."""
    schema_path = os.path.join(os.path.dirname(__file__), os.pardir, "schema.sql")
    with open(schema_path, encoding="utf-8") as f:
        sql = f.read()
    # ';' 로 나눠 'CREATE TABLE' 이 든 문장만 실행 (schema.sql 은 IF NOT EXISTS 라 안전)
    statements = [s.strip() for s in sql.split(";") if "CREATE TABLE" in s.upper()]
    created, checked = 0, 0
    with connection() as conn:
        with conn.cursor() as cur:
            for stmt in statements:
                name = _table_name_of(stmt)
                cur.execute(
                    "SELECT COUNT(*) AS n FROM information_schema.tables "
                    "WHERE table_schema = DATABASE() AND table_name = %s", (name,))
                existed = (cur.fetchone() or {}).get("n", 0) > 0
                cur.execute(stmt)
                if existed:
                    checked += 1
                    print(f"[DB]   - {name}: 확인(이미 있음)")
                else:
                    created += 1
                    print(f"[DB]   - {name}: 🆕 새로 생성")
    print(f"[DB]   테이블 총 {len(statements)}개 (생성 {created} / 기존 {checked})")


def _table_name_of(stmt: str) -> str:
    """CREATE TABLE 문에서 테이블 이름만 뽑아냅니다. (주석의 'IF NOT EXISTS' 에 속지 않도록 CREATE TABLE 기준)"""
    idx = stmt.upper().find("CREATE TABLE")
    rest = stmt[idx + len("CREATE TABLE"):].strip() if idx >= 0 else stmt.strip()
    if rest.upper().startswith("IF NOT EXISTS"):
        rest = rest[len("IF NOT EXISTS"):].strip()
    return rest.split("(")[0].split()[0].strip("`\" ")


def _column_missing(table: str, column: str) -> bool:
    """해당 테이블에 컬럼이 없으면 True."""
    row = fetch_one(
        "SELECT COUNT(*) AS n FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
        (table, column),
    )
    return bool(row) and row.get("n", 0) == 0


def _ensure_newsletter_columns() -> None:
    """기존 DB 호환: 빠진 컬럼을 보강합니다."""
    if _column_missing("newsletter", "news_type"):
        execute("ALTER TABLE newsletter "
                "ADD COLUMN news_type VARCHAR(100) NULL COMMENT '생성 타입명' AFTER category_id")
        print("[DB] newsletter.news_type 컬럼을 추가했습니다.")
    if _column_missing("interest_category", "checkpoints"):
        execute("ALTER TABLE interest_category "
                "ADD COLUMN checkpoints JSON NULL COMMENT '검수용 주요 체크포인트' AFTER keywords")
        print("[DB] interest_category.checkpoints 컬럼을 추가했습니다.")


def _seed_default_categories() -> None:
    """기본 카테고리를 DEFAULT_CATEGORIES 기준으로 다시 맞춥니다.

    코드(code)를 기준으로 '있으면 이름/키워드/체크포인트를 갱신, 없으면 추가'(upsert)합니다.
    → 모든 카테고리가 최신 키워드 + 체크포인트를 갖게 됩니다.
    (행을 통째로 지우지 않고 갱신하므로 id 가 유지되어 구독자·보고서 연결이 끊기지 않습니다)
    """
    import json

    for order, cat in enumerate(DEFAULT_CATEGORIES):
        execute(
            "INSERT INTO interest_category (code, name, keywords, checkpoints, sort_order) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE "
            "  name = VALUES(name), keywords = VALUES(keywords), "
            "  checkpoints = VALUES(checkpoints), sort_order = VALUES(sort_order)",
            (
                cat["code"],
                cat["name"],
                json.dumps(cat["keywords"], ensure_ascii=False),
                json.dumps(cat.get("checkpoints", []), ensure_ascii=False),
                order,
            ),
        )
    print(f"[DB]   카테고리: {len(DEFAULT_CATEGORIES)}개 동기화(키워드·체크포인트 갱신)")


# --------------------------------------------------------------------------
# 환경설정 (app_setting) — 뉴스레터 자동작성 관련 환경 관리
#   key/value 방식이라 설정을 늘리기 쉽습니다. (DEFAULT_SETTINGS 에 한 줄 추가)
# --------------------------------------------------------------------------
DEFAULT_SETTINGS = [
    {"key": "max_revisions", "value": "2",  "type": "int",
     "label": "최대 재작성 횟수",
     "desc": "검수 미달 시 작성 단계로 되돌아가는 최대 횟수 (무한 루프 방지)"},
    {"key": "pass_score",    "value": "60", "type": "int",
     "label": "승인 기준 점수",
     "desc": "검수에서 '통과'로 인정할 최소 점수 (0~100)"},
    {"key": "auto_send",     "value": "0",  "type": "bool",
     "label": "자동 발송",
     "desc": "검수 통과 시 사람 승인 없이 바로 발송 (1=켜기, 0=끄기)"},
    {"key": "default_template_code", "value": "default", "type": "template",
     "label": "기본 이메일 템플릿",
     "desc": "발송 시 기본으로 선택될 이메일 템플릿"},
]


def _seed_settings() -> None:
    """기본 환경설정 중 '키가 아직 없는 것'만 넣습니다. (이미 있으면 건드리지 않음)"""
    existing = {r["setting_key"] for r in fetch_all("SELECT setting_key FROM app_setting")}
    added = []
    for order, s in enumerate(DEFAULT_SETTINGS):
        if s["key"] in existing:
            continue
        execute(
            "INSERT INTO app_setting "
            "(setting_key, setting_value, value_type, label, description, sort_order) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (s["key"], s["value"], s["type"], s["label"], s["desc"], order),
        )
        added.append(s["label"])
    print(f"[DB]   환경설정: 추가 {len(added)}개 / 기존 {len(existing)}개"
          + (f" (추가: {', '.join(added)})" if added else ""))


def get_settings() -> list[dict]:
    """모든 환경설정을 정렬 순서대로 조회합니다. (관리 화면용)"""
    return fetch_all("SELECT * FROM app_setting ORDER BY sort_order, setting_key")


def get_setting(key: str, default: str | None = None) -> str | None:
    """설정 값(문자열)을 가져옵니다. 없으면 default 를 돌려줍니다."""
    row = fetch_one("SELECT setting_value FROM app_setting WHERE setting_key = %s", (key,))
    return row["setting_value"] if row else default


def get_int_setting(key: str, default: int = 0) -> int:
    """정수형 설정 값을 가져옵니다. (없거나 변환 실패 시 default)"""
    try:
        return int(get_setting(key))
    except (TypeError, ValueError):
        return default


def get_bool_setting(key: str, default: bool = False) -> bool:
    """불리언 설정 값을 가져옵니다. ('1/true/on/yes' 면 True)"""
    val = get_setting(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "on", "yes")


def update_setting(key: str, value) -> int:
    """설정 값을 갱신합니다. (값은 문자열로 저장)"""
    return execute(
        "UPDATE app_setting SET setting_value = %s WHERE setting_key = %s",
        (str(value), key),
    )


# --------------------------------------------------------------------------
# 뉴스레터 생성 타입 (newsletter_type) — 요약형 / 트렌드분석형 / 실무요약형 …
#   작성 스타일을 골라 쓰기 위한 목록입니다. description 에 스타일 설명을 둡니다.
# --------------------------------------------------------------------------
DEFAULT_NEWSLETTER_TYPES = [
    {"code": "summary",   "name": "요약형",
     "desc": "핵심 내용만 간결하게 요약하는 스타일"},
    {"code": "trend",     "name": "트렌드분석형",
     "desc": "최신 동향과 흐름을 분석하고 전망까지 담는 스타일"},
    {"code": "practical", "name": "실무요약형",
     "desc": "실무에 바로 활용할 수 있게 정리하는 스타일"},
]


def _seed_newsletter_types() -> None:
    """기본 생성 타입 중 '코드가 아직 없는 것'만 넣습니다."""
    existing = {r["code"] for r in fetch_all("SELECT code FROM newsletter_type")}
    added = []
    for order, t in enumerate(DEFAULT_NEWSLETTER_TYPES):
        if t["code"] in existing:
            continue
        execute(
            "INSERT INTO newsletter_type (code, name, description, sort_order) "
            "VALUES (%s, %s, %s, %s)",
            (t["code"], t["name"], t["desc"], order),
        )
        added.append(t["name"])
    print(f"[DB]   생성 타입: 추가 {len(added)}개 / 기존 {len(existing)}개"
          + (f" (추가: {', '.join(added)})" if added else ""))


def list_newsletter_types(active_only: bool = False) -> list[dict]:
    """뉴스레터 생성 타입 목록을 조회합니다."""
    sql = "SELECT * FROM newsletter_type "
    sql += "WHERE is_active = 1 " if active_only else ""
    return fetch_all(sql + "ORDER BY sort_order, id")


def create_newsletter_type(code: str, name: str,
                           description: str | None = None, sort_order: int = 0) -> int:
    """생성 타입을 추가하고 새 id 를 돌려줍니다. (code 중복 시 예외)"""
    return execute(
        "INSERT INTO newsletter_type (code, name, description, sort_order) "
        "VALUES (%s, %s, %s, %s)",
        (code, name, description, sort_order),
    )


def delete_newsletter_type(type_id: int) -> int:
    """생성 타입 한 건을 삭제합니다."""
    return execute("DELETE FROM newsletter_type WHERE id = %s", (type_id,))


def update_newsletter_type(
    type_id: int,
    name: str | None = None,
    description: str | None = None,
    sort_order: int | None = None,
    is_active: bool | None = None,
) -> int:
    """생성 타입을 수정합니다."""
    fields: list[str] = []
    params: list = []
    if name is not None:
        fields.append("name = %s")
        params.append(name.strip())
    if description is not None:
        fields.append("description = %s")
        params.append(description.strip() or None)
    if sort_order is not None:
        fields.append("sort_order = %s")
        params.append(sort_order)
    if is_active is not None:
        fields.append("is_active = %s")
        params.append(1 if is_active else 0)
    if not fields:
        return 0
    params.append(type_id)
    return execute(
        f"UPDATE newsletter_type SET {', '.join(fields)} WHERE id = %s",
        tuple(params),
    )


def get_type_name(code: str | None) -> str | None:
    """타입 코드(summary/trend …)로 표시명을 가져옵니다. (없으면 코드 그대로, None이면 None)"""
    if not code:
        return None
    row = fetch_one("SELECT name FROM newsletter_type WHERE code = %s", (code,))
    return (row or {}).get("name") or code


# --------------------------------------------------------------------------
# 기본 검수 체크리스트 (review_checklist)
#   카테고리 체크포인트가 없을 때 검수 노드가 사용합니다.
# --------------------------------------------------------------------------
DEFAULT_REVIEW_CHECKLIST = [
    "첫 문단이 독자의 흥미를 끌고 글의 핵심을 예고하는가",
    "친근하면서도 전문적인 어조가 일관되는가",
    "핵심 정보가 구체적이고 독자에게 유익한가(일반론만 아님)",
    "문장이 명확하고 군더더기 없이 이해하기 쉬운가",
    "맺음말 또는 다음 행동(관심·구독 등) 유도가 있는가",
]


def _seed_review_checklist() -> None:
    """기본 검수 체크리스트가 비어 있으면 시드 데이터를 넣습니다."""
    row = fetch_one("SELECT COUNT(*) AS n FROM review_checklist")
    if row and row.get("n", 0) > 0:
        print(f"[DB]   검수 체크리스트: 기존 {row['n']}개 유지")
        return
    for order, label in enumerate(DEFAULT_REVIEW_CHECKLIST):
        execute(
            "INSERT INTO review_checklist (label, sort_order) VALUES (%s, %s)",
            (label, order),
        )
    print(f"[DB]   검수 체크리스트: {len(DEFAULT_REVIEW_CHECKLIST)}개 추가")


def list_review_checklist(active_only: bool = False) -> list[dict]:
    """기본 검수 체크리스트 항목 목록."""
    sql = "SELECT * FROM review_checklist "
    sql += "WHERE is_active = 1 " if active_only else ""
    return fetch_all(sql + "ORDER BY sort_order, id")


def create_review_checklist_item(label: str, sort_order: int = 0) -> int:
    """체크리스트 항목 추가."""
    return execute(
        "INSERT INTO review_checklist (label, sort_order) VALUES (%s, %s)",
        (label.strip(), sort_order),
    )


def update_review_checklist_item(
    item_id: int,
    label: str | None = None,
    sort_order: int | None = None,
    is_active: bool | None = None,
) -> int:
    """체크리스트 항목 수정."""
    fields: list[str] = []
    params: list = []
    if label is not None:
        fields.append("label = %s")
        params.append(label.strip())
    if sort_order is not None:
        fields.append("sort_order = %s")
        params.append(sort_order)
    if is_active is not None:
        fields.append("is_active = %s")
        params.append(1 if is_active else 0)
    if not fields:
        return 0
    params.append(item_id)
    return execute(
        f"UPDATE review_checklist SET {', '.join(fields)} WHERE id = %s",
        tuple(params),
    )


def delete_review_checklist_item(item_id: int) -> int:
    """체크리스트 항목 삭제."""
    return execute("DELETE FROM review_checklist WHERE id = %s", (item_id,))


def replace_review_checklist(labels: list[str]) -> int:
    """기본 검수 체크리스트를 줄 단위 목록으로 통째로 갱신합니다."""
    cleaned: list[str] = []
    for label in labels or []:
        s = (label or "").strip()
        if s and s not in cleaned:
            cleaned.append(s)
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM review_checklist")
            for i, label in enumerate(cleaned):
                cur.execute(
                    "INSERT INTO review_checklist (label, sort_order) VALUES (%s, %s)",
                    (label, i),
                )
    return len(cleaned)


def get_default_review_checkpoints() -> list[str]:
    """활성 기본 검수 체크포인트 문구 목록."""
    rows = list_review_checklist(active_only=True)
    return [r["label"] for r in rows if r.get("label")]


# --------------------------------------------------------------------------
# 기본 구독자(메일링리스트) 시드 — 이메일이 없을 때만 추가 + 관심 카테고리 연결
#   category_code 는 interest_category.code 와 맞춰야 합니다.
# --------------------------------------------------------------------------
DEFAULT_SUBSCRIBERS = [
    {"email": "lippana@naver.com",  "name": "박희순", "category_code": "ai"},
    {"email": "zerg4572@naver.com", "name": "최인렬", "category_code": "economy"},
    {"email": "secui0101@gmail.com", "name": "오미영", "category_code": "education"},
    {"email": "guard884@gmail.com", "name": "김경호", "category_code": "ai"},
]


def _seed_subscribers() -> None:
    """기본 구독자 중 '이메일이 아직 없는 사람'만 추가하고 관심 카테고리를 연결합니다."""
    existing = {r["email"] for r in fetch_all("SELECT email FROM subscriber")}
    added = []
    for s in DEFAULT_SUBSCRIBERS:
        if s["email"] in existing:
            continue
        cat = fetch_one("SELECT id FROM interest_category WHERE code = %s", (s["category_code"],))
        cat_id = cat["id"] if cat else None
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO subscriber (email, name) VALUES (%s, %s)",
                            (s["email"], s["name"]))
                sub_id = cur.lastrowid
                if cat_id:
                    cur.execute(
                        "INSERT INTO subscriber_interest (subscriber_id, category_id) "
                        "VALUES (%s, %s)",
                        (sub_id, cat_id),
                    )
        added.append(s["name"])
    print(f"[DB]   구독자: 추가 {len(added)}명 / 기존 {len(existing)}명"
          + (f" (추가: {', '.join(added)})" if added else ""))


# --------------------------------------------------------------------------
# 이메일 발송 템플릿 (email_template)
#   템플릿 HTML 안의 {{subject}} {{body}} {{unsubscribe_url}} 가 발송 시 치환됩니다.
# --------------------------------------------------------------------------
_TPL_DEFAULT = """<div style="background:#eef1f5; padding:24px 12px; font-family:'Apple SD Gothic Neo','Malgun Gothic',Helvetica,Arial,sans-serif;">
<div style="max-width:640px; margin:0 auto; background:#ffffff; border-radius:14px; overflow:hidden; box-shadow:0 4px 16px rgba(0,0,0,.08);">
<div style="background:linear-gradient(135deg,#5681d0,#3b6fd4); padding:30px 34px; color:#ffffff;">
<div style="font-size:12px; letter-spacing:1.5px; opacity:.85;">📰 NEWSLETTER</div>
<div style="font-size:23px; font-weight:700; margin-top:8px; line-height:1.35;">{{subject}}</div>
</div>
<div style="padding:30px 34px;">{{body}}</div>
<div style="padding:18px 34px; background:#fafbfc; color:#9aa0a6; font-size:12px; border-top:1px solid #eef0f4; line-height:1.7;">
본 메일은 관심분야를 구독하신 분께 자동 발송되었습니다.<br>
ⓒ <strong style="color:#5a6066;">NewsCrew 팀</strong> · <a href="{{unsubscribe_url}}" style="color:#5681d0; text-decoration:underline;">구독취소</a>
</div></div></div>"""

_TPL_MINIMAL = """<div style="max-width:600px; margin:0 auto; padding:28px 24px; font-family:'Malgun Gothic',Arial,sans-serif; color:#222;">
<h1 style="font-size:22px; margin:0; border-bottom:3px solid #222; padding-bottom:12px;">{{subject}}</h1>
<div style="margin-top:18px;">{{body}}</div>
<hr style="margin-top:28px; border:none; border-top:1px solid #ddd;">
<p style="font-size:12px; color:#999;">ⓒ NewsCrew 팀 · <a href="{{unsubscribe_url}}" style="color:#666;">구독취소</a></p>
</div>"""

_TPL_DARK = """<div style="background:#0f1117; padding:24px 12px; font-family:'Apple SD Gothic Neo','Malgun Gothic',Arial,sans-serif;">
<div style="max-width:640px; margin:0 auto; background:#1b1e27; border-radius:14px; overflow:hidden; border:1px solid #2a2e3a;">
<div style="padding:28px 32px; border-bottom:1px solid #2a2e3a;">
<div style="font-size:12px; letter-spacing:1.5px; color:#7aa2ff;">📰 NEWSLETTER</div>
<div style="font-size:23px; font-weight:700; margin-top:8px; color:#f0f2f8;">{{subject}}</div>
</div>
<div style="padding:28px 32px; color:#cdd2dd;">{{body}}</div>
<div style="padding:18px 32px; background:#161922; color:#7c8294; font-size:12px; border-top:1px solid #2a2e3a;">
ⓒ <strong style="color:#aab1c2;">NewsCrew 팀</strong> · <a href="{{unsubscribe_url}}" style="color:#7aa2ff;">구독취소</a>
</div></div></div>"""

DEFAULT_TEMPLATES = [
    {"code": "default", "name": "기본 (파란 카드)", "html": _TPL_DEFAULT},
    {"code": "minimal", "name": "미니멀 (심플)",   "html": _TPL_MINIMAL},
    {"code": "dark",    "name": "다크",            "html": _TPL_DARK},
]


def _seed_templates() -> None:
    """기본 이메일 템플릿 중 '코드가 아직 없는 것'만 넣습니다."""
    existing = {r["code"] for r in fetch_all("SELECT code FROM email_template")}
    added = []
    for t in DEFAULT_TEMPLATES:
        if t["code"] in existing:
            continue
        execute("INSERT INTO email_template (code, name, html) VALUES (%s, %s, %s)",
                (t["code"], t["name"], t["html"]))
        added.append(t["name"])
    print(f"[DB]   이메일 템플릿: 추가 {len(added)}개 / 기존 {len(existing)}개"
          + (f" (추가: {', '.join(added)})" if added else ""))


def list_templates() -> list[dict]:
    """이메일 템플릿 목록을 조회합니다. (html 포함)"""
    return fetch_all("SELECT id, code, name, html, is_active FROM email_template ORDER BY id")


def create_template(code: str, name: str, html: str) -> int:
    """이메일 템플릿을 추가합니다. (code 중복 시 예외)"""
    return execute("INSERT INTO email_template (code, name, html) VALUES (%s, %s, %s)",
                   (code, name, html))


def delete_template(template_id: int) -> int:
    """이메일 템플릿 한 건을 삭제합니다."""
    return execute("DELETE FROM email_template WHERE id = %s", (template_id,))


def get_template_html(code: str | None) -> str | None:
    """템플릿 코드로 HTML을 가져옵니다. (없으면 None)"""
    if not code:
        return None
    row = fetch_one("SELECT html FROM email_template WHERE code = %s", (code,))
    return row["html"] if row else None
