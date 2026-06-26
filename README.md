# NewsCrew

NewsCrew는 관심 분야와 키워드를 입력하면 AI가 최신 자료를 조사하고, 뉴스레터/보고서 초안을 작성한 뒤, 검수와 사람의 승인을 거쳐 구독자에게 이메일로 발송하는 자동화 프로젝트입니다.

FastAPI 백엔드, LangGraph 기반 에이전트 워크플로우, Streamlit 관리 화면, MySQL 데이터베이스로 구성되어 있습니다.

## 주요 기능

- 관심 분야/키워드 기반 뉴스레터 또는 보고서 생성
- LangGraph 기반 자동화 흐름: `research -> tools -> write -> review -> send`
- 뉴스 검색, 주식 검색, 로컬 RAG 검색 도구 연동
- AI 검수 점수와 피드백 제공
- 승인/반려 후 재작성 흐름 지원
- 구독자, 카테고리, 뉴스레터 유형, 검수 체크리스트, 이메일 템플릿 관리
- 승인된 뉴스레터를 관심 카테고리별 구독자에게 이메일 발송
- OpenAI API 키나 SMTP 설정이 없어도 Mock 모드로 기본 동작 확인 가능

## 프로젝트 구조

```text
NewsCrew/
├─ app/                    FastAPI 백엔드와 핵심 비즈니스 로직
│  ├─ main.py              API 엔드포인트
│  ├─ graph.py             LangGraph 워크플로우 구성
│  ├─ db.py                MySQL 연결, 테이블 초기화, 기본 데이터 시드
│  ├─ llm.py               LLM 호출 래퍼
│  ├─ mailer.py            이메일 템플릿 렌더링과 SMTP 발송
│  ├─ nodes/               research, tools, write, review, send 노드
│  └─ tools/               뉴스/주식/RAG 검색 도구
├─ web/                    Streamlit 프론트엔드
│  ├─ streamlit_app.py     관리 UI 진입점
│  ├─ api_client.py        FastAPI 호출 클라이언트
│  └─ ui_theme.py          화면 스타일
├─ mysql/
│  └─ docker-compose.yml   MySQL 실행 설정
├─ data/                   RAG 검색용 시드 데이터
├─ schema.sql              DB 테이블 스키마
├─ prompts.yaml            에이전트 프롬프트 설정
├─ requirements.txt        Python 의존성
├─ run_api.py              FastAPI 실행 파일
└─ run.py                  FastAPI와 Streamlit 동시 실행 파일
```

## 실행 전 준비

### 1. Conda 가상환경 만들기

이 프로젝트는 Conda 가상환경에서 실행하는 방식을 권장합니다.

```powershell
conda create -n newscrew python=3.11 -y
conda activate newscrew
python -m pip install --upgrade pip
pip install -r requirements.txt
```

이미 사용 중인 Conda 환경이 있다면 새로 만들지 않고 해당 환경을 활성화한 뒤 의존성만 설치해도 됩니다.

```powershell
conda activate your_env_name
python -m pip install --upgrade pip
pip install -r requirements.txt
```

참고: Conda 환경 안에서도 프로젝트 의존성은 `requirements.txt` 기준으로 `pip install`을 사용합니다.

### 2. MySQL 실행

Docker가 설치되어 있다면 아래 명령으로 MySQL을 실행할 수 있습니다.

```powershell
cd mysql
docker compose up -d
cd ..
```

기본 DB 설정은 다음과 같습니다.

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=1234
DB_NAME=mydatabase
```

앱이 시작될 때 `schema.sql`을 기준으로 필요한 테이블을 만들고, 기본 카테고리/설정/템플릿 데이터를 자동으로 넣습니다.

### 3. 환경변수 설정

프로젝트 루트에 `.env` 파일을 만들고 필요한 값만 입력합니다.

```env
# OpenAI
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-5-nano

# FastAPI
API_HOST=127.0.0.1
API_PORT=80

# Streamlit -> FastAPI 호출 주소
API_BASE=http://127.0.0.1:80

# MySQL
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=1234
DB_NAME=mydatabase

# SMTP 이메일 발송
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@example.com
SMTP_PASSWORD=your_app_password
SMTP_FROM=your_email@example.com
SMTP_TLS=1

# RAG 검색
CHROMA_DB_DIR=.chroma
CHROMA_COLLECTION_NAME=company_research_data
RAG_SOURCE_FILE=data/company_vector_seed_kr_listed_20.txt
```

주의: 실제 API 키, 이메일 비밀번호, 앱 비밀번호는 README나 Git에 올리지 마세요.

## 실행 방법

아래 명령은 프로젝트 폴더에서 실행합니다.

### 1. FastAPI 백엔드 실행

터미널 1에서 백엔드 서버를 실행합니다.

```powershell
python run_api.py
```

API 문서:

```text
http://127.0.0.1/docs
```

### 2. Streamlit 화면 실행

터미널 2에서 웹 화면을 실행합니다.

```powershell
streamlit run web/streamlit_app.py --server.port 8501
```

화면 주소:

```text
http://localhost:8501
```

## 기본 사용 흐름

1. Streamlit 화면에서 관심 분야와 뉴스레터 유형을 선택합니다.
2. 생성하고 싶은 주제나 요청 문장을 입력합니다.
3. 백엔드가 키워드를 추출하고 LangGraph 워크플로우를 실행합니다.
4. `research` 단계에서 자료를 조사하고, 필요하면 검색 도구를 호출합니다.
5. `write` 단계에서 뉴스레터 초안을 작성합니다.
6. `review` 단계에서 체크리스트 기반 검수를 수행하고 점수와 피드백을 생성합니다.
7. 사용자가 승인하면 `send` 단계에서 관련 구독자에게 이메일을 발송합니다.
8. 반려하면 피드백을 반영해 다시 작성할 수 있습니다.

## 주요 API

FastAPI 서버를 실행한 뒤 `/docs`에서 Swagger 문서를 확인할 수 있습니다.

자주 쓰는 엔드포인트:

- `POST /keywords/extract`: 입력 문장에서 키워드 추출
- `GET /categories`: 카테고리 목록 조회
- `POST /categories`: 카테고리 생성
- `GET /types`: 뉴스레터 유형 목록 조회
- `GET /review-checklist`: 검수 체크리스트 조회
- `GET /templates`: 이메일 템플릿 조회
- `GET /subscribers`: 구독자 목록 조회
- `GET /settings`: 앱 설정 조회
- `POST /newsletters/generate`: 뉴스레터 생성
- `GET /newsletters`: 생성된 뉴스레터 목록 조회
- `GET /newsletters/{thread_id}`: 뉴스레터 상세 조회
- `POST /newsletters/{thread_id}/approve`: 승인 및 발송
- `POST /newsletters/{thread_id}/reject`: 반려 및 재작성

## 데이터베이스 테이블

주요 테이블은 다음과 같습니다.

- `interest_category`: 관심 카테고리와 키워드
- `subscriber`: 구독자
- `subscriber_interest`: 구독자와 카테고리 연결
- `newsletter`: 생성된 뉴스레터 본문과 상태
- `newsletter_send`: 발송 이력
- `newsletter_type`: 뉴스레터 생성 유형
- `review_checklist`: 기본 검수 체크리스트
- `app_setting`: 앱 설정
- `email_template`: 이메일 HTML 템플릿

## Mock 모드

처음 설치 후에는 모든 외부 설정을 완벽히 넣지 않아도 기본 흐름을 확인할 수 있습니다.

- `OPENAI_API_KEY`가 없으면 LLM 호출 대신 Mock 응답을 반환합니다.
- `SMTP_HOST`가 없으면 실제 이메일을 발송하지 않고 발송 대상만 기록합니다.
- MySQL은 필요합니다. Docker Compose로 실행하는 방식을 권장합니다.

## 문제 해결

### Streamlit에서 API 연결 오류가 날 때

FastAPI 서버가 실행 중인지 확인합니다.

```powershell
python run_api.py
```

그리고 `.env`의 `API_BASE`가 실제 API 주소와 같은지 확인합니다.

```env
API_BASE=http://127.0.0.1:80
```

### MySQL 연결 오류가 날 때

MySQL 컨테이너가 실행 중인지 확인합니다.

```powershell
docker ps
```

컨테이너가 없다면 다시 실행합니다.

```powershell
cd mysql
docker compose up -d
cd ..
```

### 80번 포트를 사용할 수 없을 때

`.env`에서 API 포트를 바꿉니다.

```env
API_PORT=8000
API_BASE=http://127.0.0.1:8000
```

그 뒤 백엔드와 Streamlit을 다시 실행합니다.

### 이메일이 실제로 발송되지 않을 때

다음 값을 확인합니다.

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@example.com
SMTP_PASSWORD=your_app_password
SMTP_FROM=your_email@example.com
SMTP_TLS=1
```

Gmail을 사용할 경우 일반 계정 비밀번호가 아니라 앱 비밀번호를 사용해야 합니다.

## 개발 참고

- 프롬프트 수정은 `prompts.yaml`에서 관리합니다.
- LangGraph 흐름은 `app/graph.py`에서 확인할 수 있습니다.
- 개별 노드 로직은 `app/nodes/` 아래에 있습니다.
- API 엔드포인트는 `app/main.py`에 모여 있습니다.
- DB 초기화와 기본 데이터 시드는 `app/db.py`에서 처리합니다.
- Streamlit 화면은 `web/streamlit_app.py`에서 시작합니다.
