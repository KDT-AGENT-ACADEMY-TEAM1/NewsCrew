-- ============================================================
-- 뉴스레터 에이전트 — DB 스키마 (mydatabase)
--   실행:  mysql -u root -p mydatabase < schema.sql
--   IF NOT EXISTS 라 여러 번 실행해도 안전합니다.
--   FK 의존성 때문에 interest_category → subscriber → subscriber_interest → newsletter 순서로 둡니다.
-- ============================================================

-- ------------------------------------------------------------
-- 관심분야 (대분류-소분류 계층)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS interest_category (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '관심분야 ID',
    parent_id       BIGINT UNSIGNED NULL                    COMMENT '상위 분야 ID (대분류-소분류 계층용, NULL이면 최상위)',
    code            VARCHAR(50)     NOT NULL                COMMENT '분야 코드 (영문 슬러그, 예: ai_tech)',
    name            VARCHAR(100)    NOT NULL                COMMENT '분야 표시명 (예: AI/기술)',
    description     VARCHAR(500)    NULL                    COMMENT '분야 설명',
    keywords        JSON            NULL                    COMMENT '콘텐츠 수집·필터링용 키워드 배열 (예: ["LLM","에이전트"])',
    checkpoints     JSON            NULL                    COMMENT '검수용 주요 체크포인트 배열 (LLM 주제별 체크에 사용)',
    sort_order      INT             NOT NULL DEFAULT 0       COMMENT '정렬 순서',
    is_active       TINYINT(1)      NOT NULL DEFAULT 1       COMMENT '사용 여부 (1:활성, 0:비활성)',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP                          COMMENT '생성일시',
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정일시',
    PRIMARY KEY (id),
    UNIQUE KEY uk_interest_category_code (code),
    KEY idx_interest_category_parent (parent_id),
    KEY idx_interest_category_active (is_active, sort_order),
    CONSTRAINT fk_interest_category_parent
        FOREIGN KEY (parent_id) REFERENCES interest_category (id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='뉴스레터 관심분야';


-- ------------------------------------------------------------
-- 구독자 (메일링리스트)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS subscriber (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '구독자 ID',
    email           VARCHAR(255)    NOT NULL                COMMENT '이메일 주소',
    name            VARCHAR(100)    NULL                    COMMENT '구독자 이름(선택)',
    is_active       TINYINT(1)      NOT NULL DEFAULT 1       COMMENT '수신 여부 (1:활성, 0:해지)',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP                          COMMENT '등록일시',
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정일시',
    PRIMARY KEY (id),
    UNIQUE KEY uk_subscriber_email (email),
    KEY idx_subscriber_active (is_active)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='뉴스레터 구독자';


-- ------------------------------------------------------------
-- 구독자 ↔ 관심분야 연결 (N:M)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS subscriber_interest (
    subscriber_id   BIGINT UNSIGNED NOT NULL COMMENT '구독자 ID',
    category_id     BIGINT UNSIGNED NOT NULL COMMENT '관심분야 ID (interest_category.id)',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '선택일시',

    -- 같은 구독자가 같은 분야를 중복 선택하지 못하도록 두 컬럼을 묶어 PK 로
    PRIMARY KEY (subscriber_id, category_id),
    KEY idx_subscriber_interest_category (category_id),

    CONSTRAINT fk_subscriber_interest_subscriber
        FOREIGN KEY (subscriber_id) REFERENCES subscriber (id)
        ON DELETE CASCADE ON UPDATE CASCADE,      -- 구독자 삭제 시 선택내역도 함께 삭제
    CONSTRAINT fk_subscriber_interest_category
        FOREIGN KEY (category_id) REFERENCES interest_category (id)
        ON DELETE CASCADE ON UPDATE CASCADE       -- 분야 삭제 시 선택내역도 함께 삭제
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='구독자 관심분야 매핑';


-- ------------------------------------------------------------
-- 생성된 뉴스레터(보고서) 결과
--   그래프가 만든 초안/검수/최종본을 보관합니다. (thread_id = 그래프 작업 ID)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS newsletter (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '보고서 ID',
    thread_id       VARCHAR(64)     NOT NULL                COMMENT '그래프 작업 ID (LangGraph thread_id)',
    title           VARCHAR(255)    NULL                    COMMENT '뉴스레터 제목 (초안 # 제목)',
    keywords        JSON            NULL                    COMMENT '생성에 사용한 키워드 배열',
    draft           MEDIUMTEXT      NULL                    COMMENT '작성된 초안 본문 (마크다운)',
    final_body      MEDIUMTEXT      NULL                    COMMENT '발송된 최종 본문',
    review_score    INT             NULL                    COMMENT '검수 점수 (0~100)',
    review_feedback VARCHAR(1000)   NULL                    COMMENT '검수 코멘트',
    revision_count  INT             NOT NULL DEFAULT 0       COMMENT '재작성 횟수',
    status          VARCHAR(30)     NOT NULL DEFAULT 'reviewing' COMMENT '진행 상태 (researching/writing/reviewing/awaiting_approval/sent)',
    category_id     BIGINT UNSIGNED NULL                    COMMENT '연관 관심분야 ID (선택)',
    news_type       VARCHAR(100)    NULL                    COMMENT '생성 타입명 (예: 요약형)',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP                          COMMENT '생성일시',
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정일시',
    PRIMARY KEY (id),
    UNIQUE KEY uk_newsletter_thread (thread_id),
    KEY idx_newsletter_status (status),
    KEY idx_newsletter_category (category_id),
    CONSTRAINT fk_newsletter_category
        FOREIGN KEY (category_id) REFERENCES interest_category (id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='생성된 뉴스레터(보고서) 결과';


-- ------------------------------------------------------------
-- 환경설정 (뉴스레터 자동작성 관련 환경)
--   key/value 방식. 기본값은 app/db.py 의 _seed_settings() 가 넣습니다.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS app_setting (
    setting_key   VARCHAR(50)  NOT NULL                COMMENT '설정 키',
    setting_value VARCHAR(255) NULL                    COMMENT '설정 값(문자열로 저장)',
    value_type    VARCHAR(20)  NOT NULL DEFAULT 'str'  COMMENT '값 타입(int/bool/str)',
    label         VARCHAR(100) NULL                    COMMENT '화면 표시명',
    description   VARCHAR(500) NULL                    COMMENT '설명',
    sort_order    INT          NOT NULL DEFAULT 0      COMMENT '정렬 순서',
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정일시',
    PRIMARY KEY (setting_key)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='뉴스레터 자동작성 환경설정';


-- ------------------------------------------------------------
-- 뉴스레터 생성 타입 (요약형 / 트렌드분석형 / 실무요약형 …)
--   기본값은 app/db.py 의 _seed_newsletter_types() 가 넣습니다.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS email_template (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '템플릿 ID',
    code        VARCHAR(50)  NOT NULL                COMMENT '템플릿 코드(영문 슬러그)',
    name        VARCHAR(100) NOT NULL                COMMENT '템플릿 표시명',
    html        MEDIUMTEXT   NULL                    COMMENT '템플릿 HTML ({{subject}}, {{body}}, {{unsubscribe_url}} 치환)',
    is_active   TINYINT(1)   NOT NULL DEFAULT 1      COMMENT '사용 여부',
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성일시',
    updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정일시',
    PRIMARY KEY (id),
    UNIQUE KEY uk_email_template_code (code)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='이메일 발송 템플릿';


CREATE TABLE IF NOT EXISTS newsletter_send (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '발송 로그 ID',
    thread_id   VARCHAR(64)  NOT NULL                COMMENT '보고서 thread_id',
    email       VARCHAR(255) NOT NULL                COMMENT '수신자 이메일',
    name        VARCHAR(100) NULL                    COMMENT '수신자 이름',
    sent_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '발송일시',
    PRIMARY KEY (id),
    KEY idx_newsletter_send_thread (thread_id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='뉴스레터 발송 이력';


CREATE TABLE IF NOT EXISTS newsletter_type (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '타입 ID',
    code        VARCHAR(50)  NOT NULL                COMMENT '타입 코드(영문 슬러그)',
    name        VARCHAR(100) NOT NULL                COMMENT '타입 표시명(예: 요약형)',
    description VARCHAR(500) NULL                    COMMENT '작성 스타일 설명',
    is_active   TINYINT(1)   NOT NULL DEFAULT 1      COMMENT '사용 여부(1:활성,0:비활성)',
    sort_order  INT          NOT NULL DEFAULT 0      COMMENT '정렬 순서',
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성일시',
    updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정일시',
    PRIMARY KEY (id),
    UNIQUE KEY uk_newsletter_type_code (code)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='뉴스레터 생성 타입';


-- ------------------------------------------------------------
-- 기본 검수 체크리스트 (카테고리 체크포인트 없을 때 사용)
--   기본값은 app/db.py 의 _seed_review_checklist() 가 넣습니다.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS review_checklist (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '체크리스트 항목 ID',
    label       VARCHAR(200)    NOT NULL                COMMENT '체크포인트 문구',
    sort_order  INT             NOT NULL DEFAULT 0       COMMENT '정렬 순서',
    is_active   TINYINT(1)      NOT NULL DEFAULT 1       COMMENT '사용 여부 (1:활성, 0:비활성)',
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP                          COMMENT '생성일시',
    updated_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정일시',
    PRIMARY KEY (id),
    KEY idx_review_checklist_active (is_active, sort_order)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='기본 검수 체크리스트';
