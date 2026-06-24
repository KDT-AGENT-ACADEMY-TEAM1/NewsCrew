"""맞춤형 뉴스레터 에이전트 — 화면(Streamlit).

이 파일은 '화면'만 담당합니다. 실제 일(DB 처리 / 리서치·작성·검수·발송 그래프)은
FastAPI 백엔드(app/main.py)가 하고, 여기서는 api_client 로 그 API를 호출만 합니다.

실행 방법:
    1) 백엔드:  python run_api.py        (FastAPI, 포트 8000)
    2) 화면:    streamlit run web/streamlit_app.py   (포트 8501)

백엔드 주소는 환경변수 API_BASE 로 바꿀 수 있습니다. (기본 http://127.0.0.1:8000)
"""
from __future__ import annotations

import re

import streamlit as st

import api_client as api   # FastAPI 백엔드 호출 (DB/LangGraph는 백엔드가 처리)


# ==========================================================================
# 1) 페이지 기본 설정 + 화면 꾸미기(CSS)
# ==========================================================================
def setup_page():
    st.set_page_config(
        page_title="뉴스레터 에이전트 (학습용)",
        page_icon="📰",
        layout="wide",
    )


def inject_css():
    st.markdown(
        """
        <style>
        .msg      { padding:10px 14px; border-radius:12px; margin:6px 0;
                    max-width:80%; line-height:1.5; }
        .msg.user { background:#5681d0; color:#fff; margin-left:auto; }
        .msg.bot  { background:#2a2a40; color:#eee; }

        /* ---- 생성 결과 테이블 (라이트/다크 테마 모두 대응) ---- */
        .rhead { font-weight:600; opacity:.65; padding:4px 8px; font-size:.85rem; }
        .rcell { padding:2px 8px; font-size:.92rem; line-height:1.3;
                 color:var(--text-color);
                 white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .rcell.title { font-weight:600; }
        .rcell.muted { opacity:.6; font-variant-numeric:tabular-nums; }
        .rdiv      { border:none; border-top:1px solid rgba(128,128,128,.28); margin:0; }
        .rdiv.head { border-top:2px solid rgba(128,128,128,.5); }
        .badge { display:inline-block; padding:3px 11px; border-radius:999px;
                 font-size:.78rem; font-weight:600; line-height:1.5; color:#fff; }
        .badge.s-reviewing { background:#3b6fd4; }
        .badge.s-writing   { background:#e08a3c; }
        .badge.s-awaiting  { background:#caa11e; }
        .badge.s-sent      { background:#2e9d63; }
        .badge.s-default   { background:#6b7280; }

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
# ==========================================================================
def init_state():
    ss = st.session_state
    ss.setdefault("messages", [
        {"role": "assistant", "content": "안녕하세요! 어떤 주제의 뉴스레터를 원하세요? 🙂"},
    ])
    ss.setdefault("thread_id", None)
    ss.setdefault("snap", None)
    ss.setdefault("reports", {})
    ss.setdefault("view_report", None)
    ss.setdefault("pending", None)
    ss.setdefault("menu", "📝 뉴스레터작성")


# ==========================================================================
# 3) 작은 도우미 함수들 (순수 표시용 — 백엔드 호출 없음)
# ==========================================================================
def _inline_md(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def md_to_html(text: str) -> str:
    """마크다운 글을 화면용 HTML로 바꿉니다."""
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
    return f"<div style='font-size:1rem; line-height:1.75;'>{chr(10).join(html)}</div>"


def draft_title(draft: str) -> str:
    for line in draft.split("\n"):
        if line.startswith("# "):
            return line[2:].strip()
    return "뉴스레터"


STATUS_LABELS = {
    "researching": "리서치중", "writing": "작성중", "reviewing": "검수중",
    "awaiting_approval": "승인대기", "sent": "발송완료",
}


def status_label(status: str | None) -> str:
    return STATUS_LABELS.get(status or "", status or "-")


_STATUS_BADGE = {
    "reviewing": "s-reviewing", "writing": "s-writing", "researching": "s-writing",
    "awaiting_approval": "s-awaiting", "sent": "s-sent",
}


def status_badge(status: str | None) -> str:
    cls = _STATUS_BADGE.get(status or "", "s-default")
    return f"<span class='badge {cls}'>{status_label(status)}</span>"


def draft_excerpt(draft: str, length: int = 120) -> str:
    for line in draft.split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith(">"):
            continue
        return line if len(line) <= length else line[:length].rstrip() + "…"
    return ""


# ==========================================================================
# 4) 화면(페이지) — 사용자 입력 + 채팅
# ==========================================================================
def open_report(report_id: str):
    """'더보기' → 해당 보고서의 '상세보기' 화면으로 바로 이동합니다."""
    snap = st.session_state.reports.get(report_id)
    if snap:
        st.session_state.snap = snap
        st.session_state.thread_id = report_id
    st.session_state.view_report = report_id
    st.session_state.goto = "📨 뉴스레터 생성 결과"
    st.rerun()


def page_input():
    st.markdown("## 📝 뉴스레터용 보고서 작성")

    # (1) 지금까지의 대화를 말풍선으로 그리기
    for i, m in enumerate(st.session_state.messages):
        css = "user" if m["role"] == "user" else "bot"
        report_id = m.get("report_id")
        st.markdown(f'<div class="msg {css}">{m["content"]}</div>', unsafe_allow_html=True)
        if report_id:
            if st.button("더보기", key=f"detail_{i}", help="생성 결과 화면에서 전체 보고서 보기"):
                open_report(report_id)

    # (1-2) 작성중이면: '작성중' 카드를 먼저 그린 뒤 그 자리에서 생성(API) 실행.
    pending = st.session_state.pending
    if pending:
        kw = ", ".join(pending["keywords"])
        types = pending.get("types") or [None]
        batch = f"{len(types)}개 타입" if pending.get("types") else "뉴스레터"
        st.markdown(
            f'<div class="msg bot">⏳ <b>작성중...</b> '
            f"'{kw}' 주제로 {batch}를 리서치 → 작성 → 검수 중이에요 🛠️</div>",
            unsafe_allow_html=True,
        )
        try:
            for t in types:                               # 선택된 타입별로 한 건씩 생성
                tcode = t["code"] if t else None           # state 에는 type_code(문자열)만 전달
                tname = t["name"] if t else None           # 화면 표시용
                snap = api.generate(pending["keywords"], pending.get("category_id"), tcode)
                intro = (f"'{kw}'" + (f" · {tname}" if tname else "")
                         + " 뉴스레터를 만들었어요! 📰")
                push_report_message(snap, intro)
        except Exception as e:
            st.error(f"생성 실패 — API 서버(8000)가 실행 중인지 확인하세요: {e}")
        st.session_state.pending = None
        st.rerun()

    # (2) 관심 카테고리로 빠르게 만들기
    with st.expander("📂 관심 카테고리로 만들기", expanded=False):
        try:
            catalog = api.get_flat_categories()
        except Exception as e:
            st.error(f"API 호출 실패 — 서버(8000) 실행을 확인하세요: {e}")
            catalog = []
        if not catalog:
            st.info("등록된 카테고리가 없습니다. '카테고리 등록'에서 추가하세요.")
        else:
            labels = st.multiselect(
                "카테고리 선택 (여러 개 가능)",
                options=[row["label"] for row in catalog],
                key="cat_select",
                placeholder="예: AI/기술 > 생성형 AI",
            )
            if labels:
                kws = api.keywords_for_labels(labels, catalog)
                chips = " ".join(f"<span class='badge s-reviewing'>{kw}</span>" for kw in kws)
                st.markdown(
                    f"<div style='margin:.2rem 0 .6rem;'>"
                    f"<span style='opacity:.7;'>키워드:</span> {chips}</div>",
                    unsafe_allow_html=True,
                )

            # 생성 타입 체크박스 (기본 전체 체크) — 체크된 타입만 생성합니다.
            try:
                types_all = api.list_newsletter_types(active_only=True)
            except Exception:
                types_all = []
            selected_types = []
            if types_all:
                st.markdown("<span style='opacity:.7;'>생성 타입</span>", unsafe_allow_html=True)
                cols = st.columns(len(types_all))
                for col, t in zip(cols, types_all):
                    if col.checkbox(t["name"], value=True, key=f"type_chk_{t['id']}"):
                        selected_types.append(t)

            if st.button("선택한 카테고리로 생성", disabled=not labels, use_container_width=True):
                handle_category_submit(labels, catalog, selected_types)
                st.rerun()

    # (3) 직접 입력 폼
    with st.form("chat_form", clear_on_submit=True):
        prompt = st.text_input("메시지", placeholder="예: 전기차랑 배터리 소식 정리해줘")
        submitted = st.form_submit_button("전송")

    if submitted and prompt.strip():
        handle_submit(prompt.strip())
        st.rerun()


def push_report_message(snap: dict, intro: str):
    """생성/재작성 결과를 채팅창에 '짧은 보고서 카드'로 추가합니다."""
    report_id = snap["thread_id"]
    st.session_state.thread_id = report_id
    st.session_state.snap = snap
    st.session_state.reports[report_id] = snap
    st.session_state.view_report = None

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
    """전송 버튼을 눌렀을 때의 처리 흐름."""
    st.session_state.messages.append({"role": "user", "content": prompt})
    try:
        keywords = api.extract_keywords(prompt)
    except Exception as e:
        st.session_state.messages.append(
            {"role": "assistant", "content": f"키워드 추출 실패 (API 서버 확인): {e}"})
        return
    if not keywords:
        st.session_state.messages.append(
            {"role": "assistant", "content": "주제를 조금 더 구체적으로 적어 주세요."})
        return
    # 실제 생성은 '다음 rerun'에서 (작성중 화면을 먼저 보여 주기 위해 예약만).
    st.session_state.pending = {"keywords": keywords}


def handle_category_submit(labels: list[str], catalog: list[dict],
                           types: list[dict] | None = None):
    """선택한 카테고리 + 체크한 생성 타입으로 생성을 예약합니다."""
    keywords = api.keywords_for_labels(labels, catalog)
    if not keywords:
        return
    by_label = {row["label"]: row["id"] for row in catalog}
    category_id = by_label.get(labels[0]) if labels else None
    types = types or []

    if types:
        type_txt = " · ".join(t["name"] for t in types)
        comment = f"[{', '.join(labels)}] 관련 최신 소식으로 [{type_txt}] 뉴스레터 만들어줘"
    else:
        comment = f"[{', '.join(labels)}] 관련 최신 소식으로 뉴스레터 만들어줘"
    st.session_state.messages.append({"role": "user", "content": comment})
    st.session_state.pending = {"keywords": keywords, "category_id": category_id, "types": types}


def handle_reject_to_chat(thread_id: str, feedback: str):
    """'반려 → 재작성': 수정 요청을 채팅으로 가져와 재작성하고 채팅 화면으로 돌아갑니다."""
    request_text = feedback or "다시 작성해 주세요."
    st.session_state.messages.append(
        {"role": "user", "content": f"↩️ 수정 요청: {request_text}"})
    with st.spinner("수정 요청을 반영해 다시 작성하는 중... ✍️"):
        try:
            snap = api.reject(thread_id, feedback)
        except Exception as e:
            st.error(f"재작성 실패: {e}")
            return
    push_report_message(snap, "수정 요청을 반영해 다시 작성했어요! ✍️")
    st.session_state.goto = "📝 뉴스레터작성"
    st.rerun()


# ==========================================================================
# 5) 화면(페이지) — 생성 결과 + 승인/반려
# ==========================================================================
def page_result():
    st.markdown("## 📨 생성 결과")
    if st.session_state.view_report:
        _result_detail(st.session_state.view_report)
    else:
        _result_list()


def _result_list():
    """생성된 보고서들을 API로 읽어 '테이블'로 보여 줍니다. (카테고리 필터)"""
    try:
        catalog = api.get_flat_categories()
    except Exception as e:
        st.error(f"API 호출 실패 — 서버(8000) 실행을 확인하세요: {e}")
        return
    label_to_id = {row["label"]: row["id"] for row in catalog}
    choice = st.selectbox("관심 카테고리 필터", ["전체"] + list(label_to_id.keys()),
                          key="result_filter")

    try:
        cat_id = None if choice == "전체" else label_to_id[choice]
        rows = api.list_newsletters(cat_id)
    except Exception as e:
        st.error(f"보고서 목록을 불러오지 못했습니다: {e}")
        return

    if not rows:
        msg = "아직 생성된 보고서가 없습니다. '뉴스레터작성'에서 먼저 생성하세요." \
            if choice == "전체" else "이 카테고리로 생성된 보고서가 없습니다."
        st.info(msg)
        return

    st.caption(f"총 {len(rows)}건 · '상세보기'로 본문 확인 및 승인/반려할 수 있어요.")

    with st.container(key="resulttbl"):
        widths = [1.6, 1.6, 1.3, 3.0, 1.2, 0.7, 1.2, 0.7]
        headers = ["작성일", "관심영역", "타입", "메일내용", "상태", "점수", "관리", ""]
        head = st.columns(widths, vertical_alignment="center")
        for col, title in zip(head, headers):
            col.markdown(f"<div class='rhead'>{title}</div>", unsafe_allow_html=True)
        st.markdown("<hr class='rdiv head'>", unsafe_allow_html=True)

        for r in rows:
            c = st.columns(widths, vertical_alignment="center")
            created = str(r["created_at"])[:16]
            category = r.get("category") or "직접입력"
            news_type = r.get("news_type") or "-"
            excerpt = draft_excerpt(r.get("draft") or "", 50) or "-"
            score = r.get("review_score")
            score_txt = score if score is not None else "–"
            c[0].markdown(f"<div class='rcell muted'>{created}</div>", unsafe_allow_html=True)
            c[1].markdown(f"<div class='rcell'>{category}</div>", unsafe_allow_html=True)
            c[2].markdown(f"<div class='rcell'>{news_type}</div>", unsafe_allow_html=True)
            c[3].markdown(f"<div class='rcell'>{excerpt}</div>", unsafe_allow_html=True)
            c[4].markdown(f"<div class='rcell'>{status_badge(r['status'])}</div>", unsafe_allow_html=True)
            c[5].markdown(f"<div class='rcell muted'>{score_txt}</div>", unsafe_allow_html=True)
            if c[6].button("상세보기", key=f"view_{r['thread_id']}", use_container_width=True):
                st.session_state.view_report = r["thread_id"]
                st.rerun()
            if c[7].button("🗑️", key=f"del_{r['thread_id']}", help="삭제", use_container_width=True):
                _delete_report(r["thread_id"])
                st.rerun()
            st.markdown("<hr class='rdiv'>", unsafe_allow_html=True)


def _delete_report(thread_id: str):
    """보고서 한 건을 API로 삭제하고, 화면 상태도 정리합니다."""
    try:
        api.delete_newsletter(thread_id)
    except Exception as e:
        st.error(f"삭제 실패: {e}")
        return
    st.session_state.reports.pop(thread_id, None)
    if st.session_state.view_report == thread_id:
        st.session_state.view_report = None


def _result_detail(thread_id: str):
    """보고서 하나의 본문 + 승인/반려 화면."""
    try:
        snap = api.get_newsletter(thread_id)
    except Exception as e:
        st.error(f"보고서를 불러오지 못했습니다: {e}")
        snap = None

    if st.button("← 목록으로"):
        st.session_state.view_report = None
        st.rerun()

    if not snap:
        st.warning("보고서를 찾을 수 없습니다.")
        return

    st.session_state.thread_id = thread_id
    st.session_state.snap = snap

    st.markdown(
        f"상태: {status_badge(snap.get('status'))} "
        f"<span style='color:#8a93a6;'>· 재작성 {snap.get('revision_count', 0)}회</span>",
        unsafe_allow_html=True,
    )
    st.markdown(md_to_html(snap.get("draft", "")), unsafe_allow_html=True)

    review = snap.get("review") or {}
    if review.get("feedback"):
        st.caption(f"🧾 검수 코멘트: {review['feedback']} (점수 {review.get('score')})")

    if snap.get("_live") and snap.get("awaiting_approval") and snap["status"] != "sent":
        feedback = st.text_input("반려 시 수정 요청(선택)", placeholder="예: 더 짧고 캐주얼하게")
        c1, c2 = st.columns(2)
        if c1.button("✅ 승인 → 발송", use_container_width=True):
            try:
                st.session_state.snap = api.approve(thread_id)
            except Exception as e:
                st.error(f"승인 실패: {e}")
            st.rerun()
        if c2.button("↩️ 반려 → 재작성", use_container_width=True):
            handle_reject_to_chat(thread_id, feedback.strip())
    elif snap.get("status") == "sent":
        st.success("✅ 발송 완료!")
    elif not snap.get("_live"):
        st.caption("ℹ️ 이전 세션에서 생성된 보고서라 읽기 전용입니다. (승인/반려는 이번 세션에서 만든 보고서만 가능)")


# ==========================================================================
# 6) 화면(페이지) — 메일링리스트
# ==========================================================================
def _valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def userlists():
    st.markdown("## 📨 메일링리스트")
    st.caption("뉴스레터를 받을 구독자와 관심분야를 관리합니다.")

    try:
        subs = api.list_subscribers()
        catalog = api.get_flat_categories()
    except Exception as e:
        st.error(f"API 호출 실패 — 서버(8000) 실행을 확인하세요: {e}")
        return
    label_to_id = {row["label"]: row["id"] for row in catalog}

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
                api.create_subscriber(em, name.strip() or None,
                                      [label_to_id[label] for label in picked])
                st.success(f"{em} 추가됨!")
                st.rerun()
            except Exception as e:
                st.error(f"추가 실패 (이메일 중복 등 확인): {e}")

    st.divider()

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
            api.delete_subscriber(s["id"])
            st.rerun()


# ==========================================================================
# 7) 화면(페이지) — 카테고리 등록
# ==========================================================================
def _parse_keywords_input(text: str) -> list[str]:
    keywords: list[str] = []
    for part in text.replace("\n", ",").split(","):
        kw = part.strip()
        if kw and kw not in keywords:
            keywords.append(kw)
    return keywords


def page_categories():
    st.markdown("## 🗂️ 카테고리 등록")
    st.caption("뉴스레터 관심분야를 추가/삭제합니다.")

    try:
        cats = api.list_categories()
    except Exception as e:
        st.error(f"API 호출 실패 — 서버(8000) 실행을 확인하세요: {e}")
        return

    parent_options = {"(없음 - 최상위 분야)": None}
    for c in cats:
        parent_options[f"{c['name']} (#{c['id']})"] = c["id"]

    with st.form("add_category_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        name = col1.text_input("분야 표시명 *", placeholder="예: AI/기술")
        code = col2.text_input("분야 코드 * (영문 슬러그)", placeholder="예: ai_tech")
        keywords_text = st.text_input("키워드 (쉼표로 구분)", placeholder="예: LLM, AI 에이전트, 반도체")
        col3, col4 = st.columns(2)
        parent_label = col3.selectbox("상위 분야", list(parent_options.keys()))
        sort_order = col4.number_input("정렬 순서", min_value=0, value=0, step=1)
        submitted = st.form_submit_button("➕ 카테고리 추가")

    if submitted:
        if not name.strip() or not code.strip():
            st.warning("표시명과 코드는 필수입니다.")
        else:
            try:
                api.create_category(code=code.strip(), name=name.strip(),
                                    keywords=_parse_keywords_input(keywords_text),
                                    parent_id=parent_options[parent_label],
                                    sort_order=int(sort_order))
                st.success(f"'{name.strip()}' 카테고리를 추가했습니다!")
                st.rerun()
            except Exception as e:
                st.error(f"추가 실패 (코드 중복 등 확인): {e}")

    st.divider()

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
            api.delete_category(c["id"])
            st.rerun()


# ==========================================================================
# 8) 화면(페이지) — 환경설정
# ==========================================================================
def page_settings():
    st.markdown("## ⚙️ 환경설정")
    st.caption("뉴스레터 자동 작성 관련 환경을 관리합니다.")

    try:
        settings = api.get_settings()
    except Exception as e:
        st.error(f"API 호출 실패 — 서버(8000) 실행을 확인하세요: {e}")
        return
    if not settings:
        st.info("등록된 설정이 없습니다.")
        return

    with st.form("settings_form"):
        new_values = {}
        for s in settings:
            key = s["setting_key"]
            vtype = s["value_type"]
            label = s["label"] or key
            help_ = s["description"]
            cur = s["setting_value"]
            if vtype == "int":
                new_values[key] = str(int(st.number_input(
                    label, value=int(cur or 0), min_value=0, step=1, help=help_, key=f"set_{key}")))
            elif vtype == "bool":
                new_values[key] = "1" if st.checkbox(
                    label, value=(str(cur) == "1"), help=help_, key=f"set_{key}") else "0"
            else:
                new_values[key] = st.text_input(label, value=cur or "", help=help_, key=f"set_{key}")
        saved = st.form_submit_button("💾 저장")

    if saved:
        try:
            api.update_settings(new_values)
            st.success("환경설정을 저장했습니다.")
            st.rerun()
        except Exception as e:
            st.error(f"저장 실패: {e}")

    st.divider()
    _settings_newsletter_types()


def _settings_newsletter_types():
    """환경설정 화면의 '뉴스레터 생성 타입' 관리 섹션."""
    st.markdown("### 🧩 뉴스레터 생성 타입")
    st.caption("작성 스타일 타입을 관리합니다.")

    try:
        types = api.list_newsletter_types()
    except Exception as e:
        st.error(f"생성 타입을 불러오지 못했습니다: {e}")
        return

    with st.form("add_type_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        name = col1.text_input("타입명 *", placeholder="예: 요약형")
        code = col2.text_input("코드 * (영문 슬러그)", placeholder="예: summary")
        desc = st.text_input("스타일 설명", placeholder="예: 핵심만 간결하게 요약하는 스타일")
        added = st.form_submit_button("➕ 타입 추가")

    if added:
        if not name.strip() or not code.strip():
            st.warning("타입명과 코드는 필수입니다.")
        else:
            try:
                api.create_newsletter_type(code.strip(), name.strip(),
                                           desc.strip() or None, sort_order=len(types))
                st.success(f"'{name.strip()}' 타입을 추가했습니다!")
                st.rerun()
            except Exception as e:
                st.error(f"추가 실패 (코드 중복 등 확인): {e}")

    if not types:
        st.info("등록된 생성 타입이 없습니다. 위에서 추가하세요.")
        return
    for t in types:
        c1, c2 = st.columns([6, 1])
        c1.markdown(
            f"**{t['name']}** `{t['code']}`<br>"
            f"<span style='color:#9ab;'>{t['description'] or '-'}</span>",
            unsafe_allow_html=True,
        )
        if c2.button("🗑️", key=f"deltype_{t['id']}", help="삭제"):
            api.delete_newsletter_type(t["id"])
            st.rerun()


# ==========================================================================
# 9) 사이드바(왼쪽 메뉴) + 페이지 전환
# ==========================================================================
PAGES = {
    "📝 뉴스레터작성": page_input,
    "📨 뉴스레터 생성 결과": page_result,
    "🗂️ 카테고리 등록": page_categories,
    "📨 메일링리스트": userlists,
    "⚙️ 환경설정": page_settings,
}


def render_header():
    st.markdown(
        "<h1 style='text-align:center; margin:0 0 4px;'>뉴스레터 자동 생성 Agent</h1>"
        "<p style='text-align:center; color:#888; margin:0 0 16px;'>"
        "키워드만 입력하면 리서치 → 작성 → 검수 → 발송까지 자동으로!</p>"
        "<hr style='margin:0 0 20px;'>",
        unsafe_allow_html=True,
    )


def render_sidebar() -> str:
    pending = st.session_state.pop("goto", None)
    if pending in PAGES:
        st.session_state.menu = pending

    with st.sidebar:
        st.markdown("### 📰 뉴스레터 에이전트")
        choice = st.radio("메뉴", list(PAGES.keys()), key="menu")
        st.caption("재작성 횟수·승인 기준 점수는 '⚙️ 환경설정'에서 관리합니다.")
    return choice


# ==========================================================================
# 10) 프로그램 시작점
# ==========================================================================
def main():
    setup_page()
    inject_css()
    init_state()
    choice = render_sidebar()
    render_header()
    PAGES[choice]()


main()
