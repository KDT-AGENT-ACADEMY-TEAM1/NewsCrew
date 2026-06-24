"""FastAPI 서버 실행 진입점 — Streamlit(run.py)과 '따로' 실행합니다.

실행 방법
    python run_api.py
    # 또는 직접:  uvicorn app.main:app --reload --port 80

host/port 는 환경변수로 바꿀 수 있습니다.
    API_HOST (기본 127.0.0.1) / API_PORT (기본 80)

문서(자동 생성):  http://127.0.0.1/docs
"""
from __future__ import annotations

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",            # app/main.py 의 FastAPI 객체
        host=os.getenv("API_HOST", "127.0.0.1"),
        port=int(os.getenv("API_PORT", "80")),
        reload=True,               # 코드 수정 시 자동 재시작
    )
