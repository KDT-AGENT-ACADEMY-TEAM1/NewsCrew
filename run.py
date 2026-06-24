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

from app.llm import ask_ai       # LLM 호출 도우미 (키워드 추출에 사용)
from app.graph import graph      # 실제 일을 하는 AI 그래프(백엔드)
from app.db import execute, fetch_all, fetch_one   # 보고서 목록/상세/삭제 (DB: newsletter)
from app.categories import (   # 관심 카테고리 (DB: interest_category)
    create_category,
    delete_category,
    get_flat_categories,
    keywords_for_labels,
    list_categories,
)
from app.subscribers import (   # 메일링리스트 (DB: subscriber)
    create_subscriber,
    delete_subscriber,
    list_subscribers,
)


# ==========================================================================
# 1) 페이지 기본 설정 + 화면 꾸미기(CSS)
# ==========================================================================
def setup_page():
    st.set_page_config(
        page_title="뉴스레터 에이전트 (학습용)",
        page_icon="📰",
        layout="wide",   # 넓게 사용 (가운데 정렬로 좁게 쓰려면 "centered")
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

        /* ---- 생성 결과 테이블 (라이트/다크 테마 모두 대응) ---- */
        .rhead { font-weight:600; opacity:.65; padding:4px 8px; font-size:.85rem; }
        .rcell { padding:2px 8px; font-size:.92rem; line-height:1.3;
                 color:var(--text-color);
                 white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .rcell.title { font-weight:600; }
        .rcell.muted { opacity:.6; font-variant-numeric:tabular-nums; }
        /* 행 전체를 가로지르는 구분선 (버튼 칸에서 끊기지 않게) */
        .rdiv      { border:none; border-top:1px solid rgba(128,128,128,.28); margin:0; }
        .rdiv.head { border-top:2px solid rgba(128,128,128,.5); }
        /* 상태 뱃지 (자체 배경+흰 글자 → 어느 테마에서도 잘 보임) */
        .badge { display:inline-block; padding:3px 11px; border-radius:999px;
                 font-size:.78rem; font-weight:600; line-height:1.5; color:#fff; }
        .badge.s-reviewing { background:#3b6fd4; }   /* 검수중   */
        .badge.s-writing   { background:#e08a3c; }   /* 작성중   */
        .badge.s-awaiting  { background:#caa11e; }   /* 승인대기 */
        .badge.s-sent      { background:#2e9d63; }   /* 발송완료 */
        .badge.s-default   { background:#6b7280; }

        /* 생성 결과 테이블만 행 높이 컴팩트하게 (st.container(key="resulttbl")) */
        .st-key-resulttbl [data-testid="stVerticalBlock"] { gap:.1rem; }
        .st-key-resulttbl [data-testid="stHorizontalBlock"] { margin:0; }
        .st-key-resulttbl .stButton > button {
            padding:.05rem .5rem; min-height:0; line-height:1.4; }
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
    ss.setdefault("reports", {})                        # 보고서 ID → 생성 결과(snap)
    ss.setdefault("view_report", None)                  # 상세보기 중인 보고서 ID (None이면 목록)
    ss.setdefault("pending", None)                      # 생성 대기 중인 작업({"keywords": [...]}) — '작성중' 화면용
    ss.setdefault("menu", "📝 뉴스레터작성")             # 현재 선택된 메뉴(페이지) — PAGES 의 첫 키


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


def _inline_md(text: str) -> str:
    """문장 안의 **굵게** 표시만 <b>로 바꿉니다."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def md_to_html(text: str) -> str:
    """마크다운 글(# 제목, - 목록 등)을 화면에 '적당한 크기'의 HTML로 바꿉니다.

    제목/소제목/목록/인용/본문을 화면에 보기 좋은 폰트 크기로 렌더링합니다.
    """
    html: list[str] = []
    in_list = False

    def close_list():
        nonlocal in_list
        if in_list:
            html.append("</ul>")
            in_list = False

    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            close_list()
            continue

        # 목록: '- ' 또는 '* '
        if line.startswith(("- ", "* ")):
            if not in_list:
                html.append("<ul style='margin:6px 0 6px 1.1rem; padding:0;'>")
                in_list = True
            html.append(f"<li style='margin:3px 0; line-height:1.7;'>{_inline_md(line[2:])}</li>")
            continue

        close_list()

        if line.startswith("### "):
            html.append(f"<h4 style='font-size:1.05rem; margin:12px 0 4px;'>{_inline_md(line[4:])}</h4>")
        elif line.startswith("## "):
            html.append(f"<h3 style='font-size:1.25rem; margin:16px 0 6px;'>{_inline_md(line[3:])}</h3>")
        elif line.startswith("# "):
            html.append(f"<h2 style='font-size:1.6rem; margin:4px 0 12px;'>{_inline_md(line[2:])}</h2>")
        elif line.startswith("> "):
            html.append(
                "<blockquote style='color:#9aa3b2; border-left:3px solid #444; "
                f"margin:8px 0; padding:2px 12px;'>{_inline_md(line[2:])}</blockquote>"
            )
        else:
            html.append(f"<p style='margin:8px 0; line-height:1.75;'>{_inline_md(line)}</p>")

    close_list()
    body = "\n".join(html)
    return f"<div style='font-size:1rem; line-height:1.75;'>{body}</div>"


def draft_title(draft: str) -> str:
    """초안 글의 맨 위 제목(# 으로 시작하는 줄)을 찾아 돌려줍니다."""
    for line in draft.split("\n"):
        if line.startswith("# "):
            return line[2:].strip()
    return "뉴스레터"


# 그래프 status 코드 → 화면용 한글 라벨
STATUS_LABELS = {
    "researching": "리서치중",
    "writing": "작성중",
    "reviewing": "검수중",
    "awaiting_approval": "승인대기",
    "sent": "발송완료",
}


def status_label(status: str | None) -> str:
    """상태 코드를 한글 표시명으로 바꿉니다. (모르는 값이면 그대로)"""
    return STATUS_LABELS.get(status or "", status or "-")


# 상태 코드 → 뱃지 CSS 클래스 (inject_css 의 .badge.s-* 와 짝)
_STATUS_BADGE = {
    "reviewing": "s-reviewing",
    "writing": "s-writing",
    "researching": "s-writing",
    "awaiting_approval": "s-awaiting",
    "sent": "s-sent",
}


def status_badge(status: str | None) -> str:
    """상태를 색깔 뱃지(HTML)로 만듭니다."""
    cls = _STATUS_BADGE.get(status or "", "s-default")
    return f"<span class='badge {cls}'>{status_label(status)}</span>"


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


def run_pipeline(keywords: list[str], max_rev: int, category_id: int | None = None) -> dict:
    """키워드로 그래프를 처음부터 실행 → 리서치·작성·검수 후 '승인 대기'에서 멈춤."""
    thread_id = uuid.uuid4().hex[:12]              # 이번 작업의 새 ID
    initial = {"keywords": keywords, "revision_count": 0,
               "max_revisions": max_rev, "status": "researching"}
    if category_id is not None:                    # 카테고리로 생성한 경우만 연결
        initial["category_id"] = category_id
    graph.invoke(initial, _config(thread_id))
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
    """'더보기' → 해당 보고서의 '상세보기' 화면으로 바로 이동합니다."""
    snap = st.session_state.reports.get(report_id)
    if snap:
        st.session_state.snap = snap
        st.session_state.thread_id = report_id
    # 이 보고서를 상세보기 대상으로 지정 → 생성 결과 화면이 목록 대신 상세를 보여줍니다.
    st.session_state.view_report = report_id
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
            if st.button("더보기", key=f"detail_{i}",
                         help="생성 결과 화면에서 전체 보고서 보기"):
                open_report(report_id)

    # (1-2) 작성중이면: 채팅 영역 끝에 '작성중...' 카드를 먼저 그린 뒤, 그 자리에서 생성 실행.
    #   Streamlit 은 블로킹 호출(run_pipeline) '전에' 그린 요소를 먼저 브라우저에 보내므로,
    #   사용자는 생성이 도는 동안 이 '작성중' 말풍선을 보게 됩니다. 끝나면 rerun 으로 결과 카드로 교체됩니다.
    pending = st.session_state.pending
    if pending:
        kw = ", ".join(pending["keywords"])
        st.markdown(
            f'<div class="msg bot">⏳ <b>작성중...</b> '
            f"'{kw}' 주제로 리서치 → 작성 → 검수를 진행하고 있어요 🛠️</div>",
            unsafe_allow_html=True,
        )
        snap = run_pipeline(pending["keywords"], st.session_state.max_rev,
                            pending.get("category_id"))
        push_report_message(snap, f"'{kw}' 뉴스레터를 만들었어요! 📰")

        st.session_state.pending = None
        st.rerun()   # '작성중' 카드를 결과 카드로 교체

    # (2) 관심 카테고리로 빠르게 만들기 — 고르고 버튼을 누르면 '생성요청 코멘트'가 자동으로 채팅에 올라갑니다.
    with st.expander("📂 관심 카테고리로 만들기", expanded=False):
        catalog = get_flat_categories()                  # DB(interest_category)에 등록된 카테고리만
        if not catalog:
            st.info("등록된 카테고리가 없습니다. DB(interest_category) 에 카테고리를 추가하면 여기에 표시됩니다.")
        else:
            labels = st.multiselect(
                "카테고리 선택 (여러 개 가능)",
                options=[row["label"] for row in catalog],
                key="cat_select",
                placeholder="예: AI/기술 > 생성형 AI",
            )

            # 선택한 카테고리의 키워드를 아래에 자동으로 보여 줍니다.
            if labels:
                kws = keywords_for_labels(labels, catalog)
                chips = " ".join(
                    f"<span class='badge s-reviewing'>{kw}</span>" for kw in kws)
                st.markdown(
                    f"<div style='margin:.2rem 0 .6rem;'>"
                    f"<span style='opacity:.7;'>키워드:</span> {chips}</div>",
                    unsafe_allow_html=True,
                )

            if st.button("선택한 카테고리로 생성", disabled=not labels, use_container_width=True):
                handle_category_submit(labels, catalog)
                st.rerun()

    # (3) 직접 입력 폼 — 전송 버튼을 누르면 submitted 가 True 가 됩니다.
    with st.form("chat_form", clear_on_submit=True):
        prompt = st.text_input("메시지", placeholder="예: 전기차랑 배터리 소식 정리해줘")
        submitted = st.form_submit_button("전송")

    # (4) 전송됐고 내용이 있으면 → AI 실행
    if submitted and prompt.strip():
        handle_submit(prompt.strip())
        st.rerun()   # 화면을 새로 그려 방금 대화를 반영


def push_report_message(snap: dict, intro: str):
    """생성/재작성 결과를 채팅창에 '짧은 보고서 카드'로 추가합니다.

    - 현재 보고서로 저장하고, report_id 로 다시 찾을 수 있게 보관합니다.
    - 카드 끝에는 '더보기' 링크(아래 [더보기] 버튼이 실제 동작)를 붙입니다.
    """
    report_id = snap["thread_id"]
    st.session_state.thread_id = report_id
    st.session_state.snap = snap
    st.session_state.reports[report_id] = snap
    st.session_state.view_report = None   # 생성 결과 화면은 기본적으로 목록부터 보이게
    # ※ DB 저장은 write 노드(app/nodes/write.py)가 그래프 안에서 자동으로 합니다.

    draft = snap["draft"]
    score = snap.get("review", {}).get("score", "-")
    st.session_state.messages.append({
        "role": "assistant",
        "report_id": report_id,
        "content": (
            f"{intro}<br>"
            f"<b>{draft_title(draft)}</b> · 검수 {score}점 "
            f"· 상태: {status_label(snap.get('status'))}<br>"
            f"<span style='color:#bcd;'>{draft_excerpt(draft)}</span> "
            f"<span style='color:#8ab4ff;'>더보기</span>"
        ),
    })


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

    # 3. 실제 생성은 '다음 rerun'에서 실행합니다. (여기서 바로 돌리면 '작성중' 화면을 못 보여 줌)
    #    pending 만 예약해 두면, page_input() 이 '작성중' 카드를 먼저 그린 뒤 생성을 실행합니다.
    st.session_state.pending = {"keywords": keywords}


def handle_category_submit(labels: list[str], catalog: list[dict]):
    """선택한 카테고리로 '생성요청 코멘트'를 자동 작성해 채팅에 올리고 생성을 예약합니다.

    카테고리는 키워드가 이미 정해져 있으므로 extract_keywords(추출) 없이 바로 씁니다.
    """
    keywords = keywords_for_labels(labels, catalog)
    if not keywords:
        return

    # 선택한 카테고리(첫 번째)를 이 보고서의 관심분야로 연결합니다.
    by_label = {row["label"]: row["id"] for row in catalog}
    category_id = by_label.get(labels[0]) if labels else None

    # 자동 생성된 요청 코멘트 (사용자가 직접 친 것처럼 채팅에 올라갑니다)
    comment = f"[{', '.join(labels)}] 관련 최신 소식으로 뉴스레터 만들어줘"
    st.session_state.messages.append({"role": "user", "content": comment})

    # 작성중 화면 → 생성 → 결과 (직접 입력과 동일한 흐름)
    st.session_state.pending = {"keywords": keywords, "category_id": category_id}


def handle_reject_to_chat(thread_id: str, feedback: str):
    """'반려 → 재작성': 수정 요청을 채팅으로 가져와 재작성하고 채팅 화면으로 돌아갑니다."""
    # 1. 수정 요청 문구를 채팅창에 내 메시지로 추가
    request_text = feedback or "다시 작성해 주세요."
    st.session_state.messages.append(
        {"role": "user", "content": f"↩️ 수정 요청: {request_text}"})

    # 2. 피드백을 반영해 재작성 실행
    with st.spinner("수정 요청을 반영해 다시 작성하는 중... ✍️"):
        snap = reject(thread_id, feedback)

    # 3. 새 결과 카드를 채팅에 추가 + 채팅 화면으로 이동
    push_report_message(snap, "수정 요청을 반영해 다시 작성했어요! ✍️")
    st.session_state.goto = "📝 뉴스레터작성"
    st.rerun()


# ==========================================================================
# 6) 화면(페이지) — 생성 결과 + 승인/반려
# ==========================================================================
def page_result():
    st.markdown("## 📨 생성 결과")
    # 상세보기 대상이 지정돼 있으면 상세 화면, 아니면 목록(테이블) 화면을 보여 줍니다.
    if st.session_state.view_report:
        _result_detail(st.session_state.view_report)
    else:
        _result_list()


def _result_list():
    """생성된 보고서들을 DB(newsletter)에서 읽어 '테이블'로 보여 줍니다.

    상단에서 관심 카테고리로 필터링할 수 있습니다.
    컬럼: 작성일 · 관심영역 · 메일내용(짧게) · 상태 · 점수 · 관리
    """
    # (1) 카테고리 필터
    catalog = get_flat_categories()                       # interest_category 의 활성 분야
    label_to_id = {row["label"]: row["id"] for row in catalog}
    choice = st.selectbox("관심 카테고리 필터", ["전체"] + list(label_to_id.keys()),
                          key="result_filter")

    # (2) 필터 조건에 맞춰 조회 (관심분야명은 join 으로)
    sql = (
        "SELECT n.thread_id, n.title, n.draft, n.status, n.review_score, n.created_at, "
        "       c.name AS category "
        "FROM newsletter n "
        "LEFT JOIN interest_category c ON c.id = n.category_id "
    )
    try:
        if choice != "전체":
            rows = fetch_all(sql + "WHERE n.category_id = %s ORDER BY n.created_at DESC, n.id DESC",
                             (label_to_id[choice],))
        else:
            rows = fetch_all(sql + "ORDER BY n.created_at DESC, n.id DESC")
    except Exception as e:
        st.error(f"DB 연결에 실패했습니다: {e}")
        return

    if not rows:
        msg = "아직 생성된 보고서가 없습니다. '뉴스레터작성'에서 먼저 생성하세요." \
            if choice == "전체" else "이 카테고리로 생성된 보고서가 없습니다."
        st.info(msg)
        return

    st.caption(f"총 {len(rows)}건 · '상세보기'로 본문 확인 및 승인/반려할 수 있어요.")

    # keyed 컨테이너로 감싸 '이 테이블에만' 컴팩트 CSS(inject_css 의 .st-key-resulttbl)를 적용.
    with st.container(key="resulttbl"):
        # 표 헤더:  작성일 · 관심영역 · 메일내용 · 상태 · 점수 · 관리(상세/삭제)
        widths = [1.7, 1.7, 3.2, 1.3, 0.7, 1.3, 0.7]
        headers = ["작성일", "관심영역", "메일내용", "상태", "점수", "관리", ""]
        head = st.columns(widths, vertical_alignment="center")
        for col, title in zip(head, headers):
            col.markdown(f"<div class='rhead'>{title}</div>", unsafe_allow_html=True)
        st.markdown("<hr class='rdiv head'>", unsafe_allow_html=True)   # 헤더 아래 굵은 선

        # 표 본문 (한 행씩)
        for r in rows:
            c = st.columns(widths, vertical_alignment="center")
            created = str(r["created_at"])[:16]              # YYYY-MM-DD HH:MM
            category = r["category"] or "직접입력"
            excerpt = draft_excerpt(r["draft"] or "", 50) or "-"
            score = r["review_score"]
            score_txt = score if score is not None else "–"
            c[0].markdown(f"<div class='rcell muted'>{created}</div>", unsafe_allow_html=True)
            c[1].markdown(f"<div class='rcell'>{category}</div>", unsafe_allow_html=True)
            c[2].markdown(f"<div class='rcell'>{excerpt}</div>", unsafe_allow_html=True)
            c[3].markdown(f"<div class='rcell'>{status_badge(r['status'])}</div>", unsafe_allow_html=True)
            c[4].markdown(f"<div class='rcell muted'>{score_txt}</div>", unsafe_allow_html=True)
            if c[5].button("상세보기", key=f"view_{r['thread_id']}", use_container_width=True):
                st.session_state.view_report = r["thread_id"]
                st.rerun()
            if c[6].button("🗑️", key=f"del_{r['thread_id']}", help="삭제", use_container_width=True):
                _delete_report(r["thread_id"])
                st.rerun()
            st.markdown("<hr class='rdiv'>", unsafe_allow_html=True)    # 행 구분선(가로 전체)


def _delete_report(thread_id: str):
    """보고서 한 건을 DB(newsletter)에서 삭제하고, 화면 상태도 정리합니다."""
    try:
        execute("DELETE FROM newsletter WHERE thread_id = %s", (thread_id,))
    except Exception as e:
        st.error(f"삭제 실패: {e}")
        return
    # 메모리 캐시 / 보던 상세 화면도 함께 정리
    st.session_state.reports.pop(thread_id, None)
    if st.session_state.view_report == thread_id:
        st.session_state.view_report = None


def _load_report(thread_id: str) -> dict | None:
    """상세보기용 보고서 데이터를 가져옵니다.

    - 이번 세션에서 만든 보고서면 그래프 상태(_read_state)를 써서 승인/반려까지 가능.
    - 과거(다른 세션) 보고서면 그래프 상태가 없으므로 DB(newsletter)에서 읽어 '읽기 전용'으로.
    """
    state = graph.get_state(_config(thread_id))
    if state.values:                       # 이번 세션 그래프에 살아 있는 작업
        snap = _read_state(thread_id)
        snap["_live"] = True
        return snap

    row = fetch_one(
        "SELECT thread_id, title, draft, status, review_score, review_feedback, revision_count "
        "FROM newsletter WHERE thread_id = %s",
        (thread_id,),
    )
    if not row:
        return None
    return {
        "thread_id": row["thread_id"],
        "status": row["status"],
        "draft": row["draft"] or "",
        "review": {"score": row["review_score"], "feedback": row["review_feedback"]},
        "revision_count": row["revision_count"] or 0,
        "awaiting_approval": False,
        "_live": False,                    # 읽기 전용 (승인/반려 불가)
    }


def _result_detail(thread_id: str):
    """보고서 하나의 본문 + 승인/반려 화면."""
    snap = _load_report(thread_id)

    # 목록으로 돌아가기
    if st.button("← 목록으로"):
        st.session_state.view_report = None
        st.rerun()

    if not snap:
        st.warning("보고서를 찾을 수 없습니다.")
        return

    st.session_state.thread_id = thread_id
    st.session_state.snap = snap

    # (1) 상태 + 초안 본문 (상태는 색깔 뱃지로)
    st.markdown(
        f"상태: {status_badge(snap.get('status'))} "
        f"<span style='color:#8a93a6;'>· 재작성 {snap.get('revision_count', 0)}회</span>",
        unsafe_allow_html=True,
    )
    st.markdown(md_to_html(snap.get("draft", "")), unsafe_allow_html=True)

    # 검수 코멘트가 있으면 함께 표시
    review = snap.get("review") or {}
    if review.get("feedback"):
        st.caption(f"🧾 검수 코멘트: {review['feedback']} (점수 {review.get('score')})")

    # (2) 이번 세션 작업이고 승인 대기 중이면 → 승인 / 반려 버튼
    if snap.get("_live") and snap.get("awaiting_approval") and snap["status"] != "sent":
        feedback = st.text_input("반려 시 수정 요청(선택)", placeholder="예: 더 짧고 캐주얼하게")
        c1, c2 = st.columns(2)

        if c1.button("✅ 승인 → 발송", use_container_width=True):
            st.session_state.snap = approve(thread_id)
            st.rerun()

        if c2.button("↩️ 반려 → 재작성", use_container_width=True):
            # 수정 요청 문구를 채팅창으로 가져가 재작성합니다.
            handle_reject_to_chat(thread_id, feedback.strip())

    elif snap.get("status") == "sent":
        st.success("✅ 발송 완료!")
    elif not snap.get("_live"):
        st.caption("ℹ️ 이전 세션에서 생성된 보고서라 읽기 전용입니다. (승인/반려는 이번 세션에서 만든 보고서만 가능)")


# ==========================================================================
# 6-2) 화면(페이지) — 메일링리스트(구독자 이메일) 관리
# ==========================================================================
def _valid_email(email: str) -> bool:
    """아주 단순한 이메일 형식 검사 (a@b.c 꼴)."""
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def userlists():
    st.markdown("## 📨 메일링리스트")
    st.caption("뉴스레터를 받을 구독자와 관심분야를 관리합니다. (DB: subscriber)")

    # DB에서 구독자 + 관심분야 옵션을 읽습니다. (실패 시 안내 후 종료)
    try:
        subs = list_subscribers()
    except Exception as e:
        st.error(f"DB 연결에 실패했습니다: {e}")
        st.caption("app/db.py 의 접속 정보를 확인하고, schema.sql 로 테이블을 만들었는지 확인하세요.")
        return

    catalog = get_flat_categories()                       # 활성 카테고리 (id 포함)
    label_to_id = {row["label"]: row["id"] for row in catalog}

    # (1) 새 구독자 추가 폼 — 이메일 + 관심분야(여러 개) 선택
    with st.form("add_sub_form", clear_on_submit=True):
        email = st.text_input("구독자 이메일 *", placeholder="예: reader@example.com")
        name = st.text_input("이름(선택)", placeholder="예: 홍길동")
        picked = st.multiselect(
            "관심분야 선택 (여러 개 가능)",
            options=list(label_to_id.keys()),
            placeholder="예: AI/기술 > 생성형 AI",
        )
        added = st.form_submit_button("➕ 추가")

    if added:
        em = email.strip().lower()
        if not _valid_email(em):
            st.warning("올바른 이메일 형식이 아닙니다.")
        else:
            try:
                create_subscriber(
                    email=em,
                    name=name.strip() or None,
                    category_ids=[label_to_id[label] for label in picked],
                )
                st.success(f"{em} 추가됨!")
                st.rerun()
            except Exception as e:
                st.error(f"추가 실패 (이메일 중복 등 확인): {e}")

    st.divider()

    # (2) 등록된 구독자 목록 + 삭제 버튼
    if not subs:
        st.info("아직 등록된 구독자가 없습니다. 위에서 추가하세요.")
        return

    st.write(f"총 **{len(subs)}명** 구독 중")
    for s in subs:
        c1, c2 = st.columns([6, 1])
        nm = f" ({s['name']})" if s.get("name") else ""
        cats = s.get("categories") or "관심분야 미선택"
        c1.markdown(
            f"**{s['email']}**{nm}<br>"
            f"<span style='color:#9ab;'>관심분야: {cats}</span>",
            unsafe_allow_html=True,
        )
        if c2.button("🗑️", key=f"delsub_{s['id']}", help="삭제"):
            delete_subscriber(s["id"])
            st.rerun()


# ==========================================================================
# 6-3) 화면(페이지) — 카테고리 등록 (DB: interest_category)
# ==========================================================================
def _parse_keywords_input(text: str) -> list[str]:
    """입력창의 '쉼표/줄바꿈으로 구분한 키워드'를 리스트로 바꿉니다. (중복/공백 제거)"""
    keywords: list[str] = []
    for part in text.replace("\n", ",").split(","):
        kw = part.strip()
        if kw and kw not in keywords:
            keywords.append(kw)
    return keywords


def page_categories():
    st.markdown("## 🗂️ 카테고리 등록")
    st.caption("뉴스레터 관심분야(interest_category)를 추가/삭제합니다. DB에 바로 반영됩니다.")

    # DB에서 현재 카테고리 목록을 읽습니다. (실패하면 안내 후 종료)
    try:
        cats = list_categories()
    except Exception as e:
        st.error(f"DB 연결에 실패했습니다: {e}")
        st.caption("app/db.py 의 접속 정보(mydatabase / root)를 확인하세요.")
        return

    # 상위 분야 선택용 옵션 ('(없음)' + 기존 카테고리들)
    parent_options = {"(없음 - 최상위 분야)": None}
    for c in cats:
        parent_options[f"{c['name']} (#{c['id']})"] = c["id"]

    # (1) 새 카테고리 추가 폼
    with st.form("add_category_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        name = col1.text_input("분야 표시명 *", placeholder="예: AI/기술")
        code = col2.text_input("분야 코드 * (영문 슬러그)", placeholder="예: ai_tech")
        keywords_text = st.text_input(
            "키워드 (쉼표로 구분)", placeholder="예: LLM, AI 에이전트, 반도체")
        col3, col4 = st.columns(2)
        parent_label = col3.selectbox("상위 분야", list(parent_options.keys()))
        sort_order = col4.number_input("정렬 순서", min_value=0, value=0, step=1)
        submitted = st.form_submit_button("➕ 카테고리 추가")

    if submitted:
        if not name.strip() or not code.strip():
            st.warning("표시명과 코드는 필수입니다.")
        else:
            try:
                create_category(
                    code=code.strip(),
                    name=name.strip(),
                    keywords=_parse_keywords_input(keywords_text),
                    parent_id=parent_options[parent_label],
                    sort_order=int(sort_order),
                )
                st.success(f"'{name.strip()}' 카테고리를 추가했습니다!")
                st.rerun()
            except Exception as e:
                st.error(f"추가 실패 (코드 중복 등 확인): {e}")

    st.divider()

    # (2) 등록된 카테고리 목록 + 삭제 버튼
    if not cats:
        st.info("아직 등록된 카테고리가 없습니다. 위에서 추가하세요.")
        return

    st.write(f"총 **{len(cats)}개** 등록됨")
    for c in cats:
        c1, c2 = st.columns([6, 1])
        parent = f" · 상위: {c['parent_name']}" if c.get("parent_name") else ""
        kw = ", ".join(c["keywords"]) if c["keywords"] else "-"
        active = "" if c["is_active"] else " · ⛔비활성"
        c1.markdown(
            f"**{c['name']}** `{c['code']}`{parent}{active}<br>"
            f"<span style='color:#9ab;'>키워드: {kw}</span>",
            unsafe_allow_html=True,
        )
        if c2.button("🗑️", key=f"delcat_{c['id']}", help="삭제"):
            delete_category(c["id"])
            st.rerun()


# ==========================================================================
# 7) 사이드바(왼쪽 메뉴) + 페이지 전환
#    - 메뉴를 추가하려면 PAGES 에 ("이름": 함수) 한 줄만 더하면 됩니다.
# ==========================================================================
PAGES = {
    "📝 뉴스레터작성": page_input,
    "📨 뉴스레터 생성 결과": page_result,
    "🗂️ 카테고리 등록": page_categories,
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

    key="menu" 로 선택값을 묶어 두어, handle_reject_to_chat() 처럼 코드에서
    '이동 예약(goto)'을 남기면 위젯 생성 '전에' 반영되어 페이지가 전환됩니다.
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
