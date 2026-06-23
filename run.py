"""맞춤형 뉴스레터 에이전트 — 화면(Streamlit) · 학습용 심플 버전.

이 파일은 '화면'만 담당합니다. 실제 일(리서치/작성/검수/발송)은
app/graph.py 의 그래프가 합니다. 여기서는 그 그래프를 호출하고
결과를 보여 줄 뿐입니다.

  - 기능마다 함수 1개로 나눠 놓았습니다. (위에서 아래로 읽으면 흐름이 보입니다)
  - 더 똑똑하게 만들 부분은  # TODO: 여기 채우기  주석을 달아 두었습니다.

실행 방법:
    streamlit run main_page.py
"""
from __future__ import annotations

import uuid                      # 매번 다른 작업 ID(thread_id) 만들 때 사용

import streamlit as st

from app.agents import ask_ai    # LLM 호출 도우미 (키워드 추출에 사용)
from app.graph import graph      # 실제 일을 하는 AI 그래프(백엔드)


# ==========================================================================
# 1) 페이지 기본 설정 + 화면 꾸미기(CSS)
# ==========================================================================
def setup_page():
    st.set_page_config(
        page_title="뉴스레터 에이전트 (학습용)",
        page_icon="📰",
        layout="centered",   # 가운데 정렬. 넓게 쓰려면 "wide"
    )


def inject_css():
    # 채팅 말풍선 정도만 간단히 꾸밉니다. (복잡한 디자인은 일부러 뺐습니다)
    st.markdown(
        """
        <style>
        .msg      { padding:10px 14px; border-radius:12px; margin:6px 0;
                    max-width:80%; line-height:1.5; }
        .msg.user { background:#5681d0; color:#fff; margin-left:auto; }  /* 내 말 */
        .msg.bot  { background:#2a2a40; color:#eee; }                    /* AI 말  */
        </style>
        """,
        unsafe_allow_html=True,
    )


# ==========================================================================
# 2) 세션 상태 초기화
#    - Streamlit 은 화면을 새로 그릴 때마다 코드를 처음부터 다시 실행합니다.
#    - 그래도 값이 유지되도록 st.session_state 라는 '기억 상자'에 담아 둡니다.
#    - setdefault: 값이 없을 때만 처음 한 번 넣어 줍니다.
# ==========================================================================
def init_state():
    ss = st.session_state
    ss.setdefault("messages", [                       # 채팅 기록
        {"role": "assistant", "content": "안녕하세요! 어떤 주제의 뉴스레터를 원하세요? 🙂"},
    ])
    ss.setdefault("thread_id", None)                  # 현재 작업 ID
    ss.setdefault("snap", None)                        # AI가 만든 결과(초안 등)
    ss.setdefault("max_rev", 2)                        # 최대 재작성 횟수
    ss.setdefault("subscribers", [])                   # 메일링리스트(구독자 이메일)
    ss.setdefault("reports", {})                        # 보고서 ID → 생성 결과(snap)
    ss.setdefault("menu", "📝 뉴스레터작성")             # 현재 선택된 메뉴(페이지)


# ==========================================================================
# 3) 작은 도우미 함수들
# ==========================================================================
import re   # 자연어 문장에서 한글/영문/숫자만 골라낼 때 사용

# 키워드가 아닌, 자주 나오는 '요청/꾸밈' 단어들 (이 단어 자체는 버립니다)
STOPWORDS = {
    "뉴스", "소식", "정보", "기사", "내용", "관련", "주제", "오늘", "최근", "요즘",
    "정리", "요약", "작성", "생성", "만들", "만들어", "만들어줘", "해줘", "해주세요",
    "알려줘", "알려주세요", "보여줘", "보여주세요", "부탁", "부탁해", "부탁해요",
    "그리고", "또는", "관해", "대해", "대한", "위한", "좀", "것", "수",
}

# 단어 끝에 붙는 한글 조사 (긴 것부터 떼어 내야 정확합니다: '에서' 먼저, 그다음 '서')
PARTICLES = (
    "이랑", "랑", "이나", "나", "에서", "에게", "에", "으로", "로",
    "은", "는", "이", "가", "을", "를", "와", "과", "도", "의", "께",
)

# 단어 끝에 이런 '요청 동사 어미'가 붙어 있으면 키워드가 아니라 부탁 표현으로 봅니다.
# (예: '정리해줘', '만들어주세요', '알려줘' → 통째로 버림)
REQUEST_ENDINGS = (
    "해주세요", "해줘요", "해줘", "해주", "주세요", "줘요", "줘",
    "할게", "해요", "합니다", "해", "하기",
)


def _strip_particle(word: str) -> str:
    """단어 끝의 조사를 한 번 떼어 냅니다. (예: '전기차랑' → '전기차')"""
    for p in PARTICLES:
        # 조사만 남는 1글자짜리가 되지 않도록, 떼고 난 뒤 길이가 2 이상일 때만
        if word.endswith(p) and len(word) - len(p) >= 2:
            return word[: -len(p)]
    return word


def extract_keywords(text: str) -> list[str]:
    """사용자의 '자연어 문장'에서 핵심 키워드를 뽑아냅니다.

    예) "전기차랑 배터리 소식 정리해줘" → ["전기차", "배터리"]

    1순위로 LLM(ask_ai)에게 키워드 추출을 맡기고,
    LLM을 못 쓰거나(키 없음/오류) 결과가 비면 규칙 기반(_keywords_by_rule)으로 폴백합니다.
    """
    llm_keywords = _keywords_by_llm(text)
    if llm_keywords:
        return llm_keywords
    return _keywords_by_rule(text)   # 폴백


def _keywords_by_llm(text: str) -> list[str]:
    """LLM에게 자연어 문장에서 검색 키워드만 뽑아 달라고 시킵니다.

    실패하거나(가짜 모드 포함) 결과가 비면 빈 리스트를 돌려줘서
    호출 쪽이 규칙 기반으로 폴백할 수 있게 합니다.
    """
    system = (
        "너는 뉴스 검색용 키워드 추출기다. "
        "사용자 문장에서 핵심 주제어(명사구)만 뽑아라. "
        "'뉴스/소식/정리해줘' 같은 요청·꾸밈 표현과 조사는 빼라. "
        "최대 4개를 한국어로, 쉼표(,)로만 구분해서 출력하라. "
        "설명·번호·따옴표 없이 키워드만 출력하라."
    )
    answer = ask_ai(system, text)

    # 가짜 모드면 "[가짜 AI 답변] ..." 가 오므로 키워드로 쓰지 않고 폴백
    if not answer or answer.startswith("[가짜 AI 답변]"):
        return []

    keywords: list[str] = []
    for part in answer.replace("\n", ",").split(","):
        kw = part.strip().strip("\"'·-•").strip()
        if kw and kw not in keywords:
            keywords.append(kw)
    return keywords[:4]


def _keywords_by_rule(text: str) -> list[str]:
    """규칙 기반 키워드 추출 (LLM 폴백용).

    처리 순서:
      1) 기호/문장부호 제거 (한글·영문·숫자·공백만 남김)
      2) 띄어쓰기로 단어 나누기
      3) '~해줘/~주세요' 부탁 표현 버림
      4) 단어 끝의 조사 떼기 ('전기차랑' → '전기차')
      5) 불필요한 단어(STOPWORDS)·1글자 단어 거르기
      6) 중복 제거 후 최대 4개만
    """
    cleaned = re.sub(r"[^0-9A-Za-z가-힣\s]", " ", text)   # 1) 기호 제거

    keywords: list[str] = []
    for raw in cleaned.split():                            # 2) 단어 나누기
        if raw.endswith(REQUEST_ENDINGS):                  # 3) '~해줘/~주세요' 부탁 표현 버림
            continue
        word = _strip_particle(raw)                        # 4) 조사 떼기
        if len(word) < 2 or word in STOPWORDS:             # 5) 불용어·1글자 거르기
            continue
        if word not in keywords:                           # 6) 중복 제거
            keywords.append(word)

    return keywords[:4]   # 최대 4개만


def md_to_html(text: str) -> str:
    """마크다운 글(# 제목, - 목록 등)을 화면에 보여줄 HTML로 바꿉니다.

    지금은 '줄바꿈만' 처리하는 가장 단순한 버전입니다.
    """
    # TODO: 여기 채우기 —— '# 제목' → <h3>, '- 항목' → <li> 처럼
    #       마크다운 기호를 HTML 태그로 바꾸는 규칙을 넣어 보세요.
    return text.replace("\n", "<br>")


def draft_title(draft: str) -> str:
    """초안 글의 맨 위 제목(# 으로 시작하는 줄)을 찾아 돌려줍니다."""
    for line in draft.split("\n"):
        if line.startswith("# "):
            return line[2:].strip()
    return "뉴스레터"


def draft_excerpt(draft: str, length: int = 120) -> str:
    """초안에서 제목/소제목·빈 줄을 빼고 첫 본문 문장을 짧게 뽑아냅니다."""
    for line in draft.split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith(">"):
            continue
        return line if len(line) <= length else line[:length].rstrip() + "…"
    return ""


# ==========================================================================
# 4) AI 백엔드(app/graph.py) 연동
#    여기 3개 함수가 '화면'과 'AI 그래프'를 이어 주는 다리입니다.
# ==========================================================================
def _config(thread_id: str) -> dict:
    """그래프에게 '어느 작업(thread)을 이어서 할지' 알려주는 설정값."""
    return {"configurable": {"thread_id": thread_id}}


def _read_state(thread_id: str) -> dict:
    """그래프에 저장된 현재 상태를 꺼내, 화면이 쓰기 편한 형태로 정리합니다."""
    state = graph.get_state(_config(thread_id))
    v = state.values
    return {
        "thread_id": thread_id,
        "status": v.get("status"),
        "keywords": v.get("keywords", []),
        "draft": v.get("draft", ""),
        "review": v.get("review", {}),
        "revision_count": v.get("revision_count", 0),
        # 'send' 직전에서 멈춰 있으면 = 사람 승인을 기다리는 중
        "awaiting_approval": "send" in state.next,
    }


def run_pipeline(keywords: list[str], max_rev: int) -> dict:
    """키워드로 그래프를 처음부터 실행 → 리서치·작성·검수 후 '승인 대기'에서 멈춤."""
    thread_id = uuid.uuid4().hex[:12]              # 이번 작업의 새 ID
    graph.invoke(
        {"keywords": keywords, "revision_count": 0,
         "max_revisions": max_rev, "status": "researching"},
        _config(thread_id),
    )
    return _read_state(thread_id)


def approve(thread_id: str) -> dict:
    """'승인' → 멈춰 있던 지점부터 재개해서 발송까지 진행."""
    graph.invoke(None, _config(thread_id))         # None = '이어서 진행'
    return _read_state(thread_id)


def reject(thread_id: str, feedback: str) -> dict:
    """'반려' → 피드백을 그래프에 넣고 작성 단계부터 다시 진행."""
    cfg = _config(thread_id)
    graph.update_state(
        cfg,
        {"human_feedback": feedback, "status": "writing"},
        as_node="research",   # research→write 길로 작성 단계 재진입
    )
    graph.invoke(None, cfg)
    return _read_state(thread_id)


# ==========================================================================
# 5) 화면(페이지) — 사용자 입력 + 채팅
# ==========================================================================
def open_report(report_id: str):
    """보고서 ID로 결과를 불러와 '뉴스레터 생성 결과' 화면으로 이동합니다."""
    snap = st.session_state.reports.get(report_id)
    if snap:
        st.session_state.snap = snap
        st.session_state.thread_id = report_id
    # 주의) 라디오(key="menu") 위젯이 이미 만들어진 뒤라 menu 를 직접 못 바꿉니다.
    #       '이동 예약(goto)'만 남기고, 다음 실행 때 위젯 생성 전에 적용합니다.
    st.session_state.goto = "📨 뉴스레터 생성 결과"
    st.rerun()


def page_input():
    st.markdown("## 📝 뉴스레터용 보고서 작성")

    # (1) 지금까지의 대화를 말풍선으로 그리기
    #     - 보고서 ID(report_id)가 달린 AI 답변에는 네이비 말풍선 안에 🔍 아이콘을 둡니다.
    for i, m in enumerate(st.session_state.messages):
        css = "user" if m["role"] == "user" else "bot"
        report_id = m.get("report_id")

        # 보고서 답변이면 말풍선(요약) + 그 아래 [자세히 보기] 버튼
        st.markdown(f'<div class="msg {css}">{m["content"]}</div>',
                    unsafe_allow_html=True)
        if report_id:
            if st.button("자세히 보기 →", key=f"detail_{i}",
                         help="생성 결과 화면에서 전체 보고서 보기"):
                open_report(report_id)

    # (2) 입력 폼 — 전송 버튼을 누르면 submitted 가 True 가 됩니다.
    with st.form("chat_form", clear_on_submit=True):
        prompt = st.text_input("메시지", placeholder="예: 전기차랑 배터리 소식 정리해줘")
        submitted = st.form_submit_button("전송")

    # (3) 전송됐고 내용이 있으면 → AI 실행
    if submitted and prompt.strip():
        handle_submit(prompt.strip())
        st.rerun()   # 화면을 새로 그려 방금 대화를 반영


def handle_submit(prompt: str):
    """전송 버튼을 눌렀을 때의 처리 흐름 (여기만 보면 동작이 다 보입니다)."""
    # 1. 내가 한 말을 대화에 추가
    st.session_state.messages.append({"role": "user", "content": prompt})

    # 2. 키워드 뽑기
    keywords = extract_keywords(prompt)
    if not keywords:
        st.session_state.messages.append(
            {"role": "assistant", "content": "주제를 조금 더 구체적으로 적어 주세요."})
        return

    # 3. AI 실행 (스피너 = 빙글빙글 도는 표시)
    with st.spinner("뉴스레터를 만드는 중... 🛠️"):
        snap = run_pipeline(keywords, st.session_state.max_rev)

    # 4. 결과 저장 + AI 답변 추가
    report_id = snap["thread_id"]
    st.session_state.thread_id = report_id
    st.session_state.snap = snap
    st.session_state.reports[report_id] = snap   # 보고서 ID로 다시 찾을 수 있게 보관
    draft = snap["draft"]
    score = snap.get("review", {}).get("score", "-")
    st.session_state.messages.append({
        "role": "assistant",
        "report_id": report_id,                   # 이 답변에 연결된 보고서 ID
        # 채팅 답변 안에 '짧은 보고서 카드'를 보여 줍니다.
        "content": (
            f"'{', '.join(keywords)}' 뉴스레터를 만들었어요! 📰<br>"
            f"<b>{draft_title(draft)}</b> · 검수 {score}점<br>"
            f"<span style='color:#bcd;'>{draft_excerpt(draft)}</span>"
        ),
    })


# ==========================================================================
# 6) 화면(페이지) — 생성 결과 + 승인/반려
# ==========================================================================
def page_result():
    st.markdown("## 📨 생성 결과")
    snap = st.session_state.snap

    if not snap:
        st.info("아직 만든 초안이 없습니다. '사용자 입력'에서 먼저 생성하세요.")
        return

    # (1) 상태 + 초안 본문 보여주기
    st.write(f"상태: **{snap['status']}** · 재작성 {snap['revision_count']}회")
    st.markdown(md_to_html(snap["draft"]), unsafe_allow_html=True)

    # 검수 코멘트가 있으면 함께 표시
    review = snap.get("review", {})
    if review.get("feedback"):
        st.caption(f"🧾 검수 코멘트: {review['feedback']} (점수 {review.get('score')})")

    # (2) 아직 승인 대기 중이면 → 승인 / 반려 버튼
    if snap.get("awaiting_approval") and snap["status"] != "sent":
        feedback = st.text_input("반려 시 수정 요청(선택)", placeholder="예: 더 짧고 캐주얼하게")
        c1, c2 = st.columns(2)

        if c1.button("✅ 승인 → 발송", use_container_width=True):
            st.session_state.snap = approve(st.session_state.thread_id)
            st.rerun()

        if c2.button("↩️ 반려 → 재작성", use_container_width=True):
            st.session_state.snap = reject(st.session_state.thread_id, feedback.strip())
            st.rerun()

    elif snap["status"] == "sent":
        st.success("✅ 발송 완료!")


# ==========================================================================
# 6-2) 화면(페이지) — 메일링리스트(구독자 이메일) 관리
# ==========================================================================
def _valid_email(email: str) -> bool:
    """아주 단순한 이메일 형식 검사 (a@b.c 꼴)."""
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def userlists():
    st.markdown("## 📨 메일링리스트")
    st.caption("뉴스레터를 받을 구독자 이메일을 관리합니다.")

    subs = st.session_state.subscribers

    # (1) 새 구독자 추가 폼
    with st.form("add_sub_form", clear_on_submit=True):
        email = st.text_input("구독자 이메일", placeholder="예: reader@example.com")
        added = st.form_submit_button("➕ 추가")

    if added:
        email = email.strip().lower()
        if not _valid_email(email):
            st.warning("올바른 이메일 형식이 아닙니다.")
        elif email in subs:
            st.info("이미 등록된 이메일입니다.")
        else:
            subs.append(email)
            st.success(f"{email} 추가됨!")
            st.rerun()

    st.divider()

    # (2) 등록된 구독자 목록 + 삭제 버튼
    if not subs:
        st.info("아직 등록된 구독자가 없습니다. 위에서 이메일을 추가하세요.")
        return

    st.write(f"총 **{len(subs)}명** 구독 중")
    for i, email in enumerate(subs):
        c1, c2 = st.columns([5, 1])
        c1.write(f"{i + 1}. {email}")
        if c2.button("🗑️", key=f"del_{i}", help="삭제"):
            subs.pop(i)
            st.rerun()


# ==========================================================================
# 7) 사이드바(왼쪽 메뉴) + 페이지 전환
#    - 메뉴를 추가하려면 PAGES 에 ("이름": 함수) 한 줄만 더하면 됩니다.
# ==========================================================================
PAGES = {
    "📝 뉴스레터작성": page_input,
    "📨 뉴스레터 생성 결과": page_result,
    "📨 메일링리스트": userlists,
}


def render_header():
    """모든 페이지 상단에 공통으로 보이는 큰 제목."""
    st.markdown(
        "<h1 style='text-align:center; margin:0 0 4px;'>뉴스레터 자동 생성 Agent</h1>"
        "<p style='text-align:center; color:#888; margin:0 0 16px;'>"
        "키워드만 입력하면 리서치 → 작성 → 검수 → 발송까지 자동으로!</p>"
        "<hr style='margin:0 0 20px;'>",
        unsafe_allow_html=True,
    )


def render_sidebar() -> str:
    """왼쪽 메뉴를 그리고, 사용자가 고른 페이지 이름을 돌려줍니다.

    key="menu" 로 선택값을 st.session_state.menu 에 묶어 두었습니다.
    → open_report() 가 남긴 '이동 예약(goto)'을 위젯 생성 '전에' 반영해 페이지를 전환합니다.
    """
    # 라디오 위젯을 만들기 전에만 menu 값을 바꿀 수 있습니다.
    pending = st.session_state.pop("goto", None)
    if pending in PAGES:
        st.session_state.menu = pending

    with st.sidebar:
        st.markdown("### 📰 뉴스레터 에이전트")
        st.session_state.max_rev = st.number_input(
            "최대 재작성 횟수", min_value=1, max_value=5,
            value=st.session_state.max_rev,
            help="검수에서 품질 미달 시 작성 단계로 되돌아가는 최대 횟수",
        )
        choice = st.radio("메뉴", list(PAGES.keys()), key="menu")
    return choice


# ==========================================================================
# 8) 프로그램 시작점 (맨 위에서부터 순서대로 실행됩니다)
# ==========================================================================
def main():
    setup_page()                 # 1. 페이지 기본 설정
    inject_css()                 # 2. 화면 꾸미기
    init_state()                 # 3. 기억 상자 준비
    choice = render_sidebar()    # 4. 왼쪽 메뉴 그리기
    render_header()              # 5. 모든 페이지 공통 상단 제목
    PAGES[choice]()              # 6. 고른 메뉴의 페이지 함수 실행


main()
