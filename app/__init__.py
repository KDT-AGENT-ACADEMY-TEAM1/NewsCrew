"""app 패키지 — 임포트 시 DB를 한 번 초기화합니다.

기본 테이블이 없으면 만들고, 관심 카테고리가 비어 있으면 기본값을 넣습니다.
(실제 동작은 app/db.py 의 init_db 에 구현되어 있습니다)
"""
from .db import init_db

init_db()
