"""app 패키지 — 임포트 시 .env 로드 + DB 초기화.

  1) .env 를 읽어 환경변수(SMTP_*, DB_*, OPENAI_API_KEY 등)를 채웁니다.
  2) 기본 테이블이 없으면 만들고, 기본 데이터가 비어 있으면 넣습니다.
"""
from dotenv import load_dotenv

# override=True: 셸에 남아 있던 예전 환경변수보다 .env 값을 우선합니다.
load_dotenv(override=True)

from .db import init_db   # noqa: E402  (.env 로드 후에 import)

init_db()

# 내부 자료(data/관련규정, data/관련자료)를 Chroma 벡터DB에 색인 (없으면 최초 1회 임베딩)
try:
    from .knowledge import init_chroma   # noqa: E402
    init_chroma()
except Exception as e:
    print(f"[chroma] 색인 건너뜀: {e}")
