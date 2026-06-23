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
    """사용자의 '자연어 문장'에서 핵심 키워드만 뽑아냅니다.

    예) "전기차랑 배터리 소식 정리해줘" → ["전기차", "배터리"]

    처리 순서:
      1) 기호/문장부호 제거 (한글·영문·숫자·공백만 남김)
      2) 띄어쓰기로 단어 나누기
      3) 단어 끝의 조사 떼기 ('전기차랑' → '전기차')
      4) 불필요한 단어(STOPWORDS)·1글자 단어 거르기
      5) 중복 제거 후 최대 4개만
    """
    # TODO: 더 똑똑하게: ask_ai() 로 LLM에게 키워드 추출을 맡기거나,
    #       형태소 분석기(예: konlpy)로 명사만 뽑으면 정확도가 올라갑니다.
    cleaned = re.sub(r"[^0-9A-Za-z가-힣\s]", " ", text)   # 1) 기호 제거

    keywords: list[str] = []
    for raw in cleaned.split():                            # 2) 단어 나누기
        if raw.endswith(REQUEST_ENDINGS):                  # 3) '~해줘/~주세요' 부탁 표현 버림
            continue
        word = _strip_particle(raw)                        # 4) 조사 떼기
        if len(word) < 2 or word in STOPWORDS:             # 5) 불용어·1글자 거르기
            continue
        if word not in keywords:                           # 5) 중복 제거
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
def page_input():
    st.markdown("## 📝 사용자 입력")

    # (1) 지금까지의 대화를 말풍선으로 그리기
    for m in st.session_state.messages:
        css = "user" if m["role"] == "user" else "bot"
        st.markdown(f'<div class="msg {css}">{m["content"]}</div>',
                    unsafe_allow_html=True)

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
    st.session_state.thread_id = snap["thread_id"]
    st.session_state.snap = snap
    score = snap.get("review", {}).get("score", "-")
    st.session_state.messages.append({
        "role": "assistant",
        "content": (f"'{', '.join(keywords)}' 뉴스레터를 만들었어요!<br>"
                    f"📰 <b>{draft_title(snap['draft'])}</b> · 검수 {score}점<br>"
                    "왼쪽 메뉴 '생성 결과'에서 확인 후 승인/반려해 주세요."),
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
# 7) 사이드바(왼쪽 메뉴) + 페이지 전환
#    - 메뉴를 추가하려면 PAGES 에 ("이름": 함수) 한 줄만 더하면 됩니다.
# ==========================================================================
PAGES = {
    "📝 사용자 입력": page_input,
    "📨 생성 결과": page_result,
}


def render_sidebar() -> str:
    """왼쪽 메뉴를 그리고, 사용자가 고른 페이지 이름을 돌려줍니다."""
    with st.sidebar:
        st.markdown("### 📰 뉴스레터 에이전트")
        st.session_state.max_rev = st.number_input(
            "최대 재작성 횟수", min_value=1, max_value=5,
            value=st.session_state.max_rev,
            help="검수에서 품질 미달 시 작성 단계로 되돌아가는 최대 횟수",
        )
        choice = st.radio("메뉴", list(PAGES.keys()))
    return choice


# ==========================================================================
# 8) 프로그램 시작점 (맨 위에서부터 순서대로 실행됩니다)
# ==========================================================================
def main():
    setup_page()                 # 1. 페이지 기본 설정
    inject_css()                 # 2. 화면 꾸미기
    init_state()                 # 3. 기억 상자 준비
    choice = render_sidebar()    # 4. 왼쪽 메뉴 그리기
    PAGES[choice]()              # 5. 고른 메뉴의 페이지 함수 실행


main()
