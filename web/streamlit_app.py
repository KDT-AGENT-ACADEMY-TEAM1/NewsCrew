"""맞춤형 뉴스레터 에이전트 — 화면(Streamlit).

이 파일은 '화면'만 담당합니다. 실제 일(DB 처리 / 리서치·작성·검수·발송 그래프)은
FastAPI 백엔드(app/main.py)가 하고, 여기서는 api_client 로 그 API를 호출만 합니다.

실행 방법:
    1) 백엔드:  python run_api.py        (FastAPI, 포트 8000)
    2) 화면:    streamlit run web/streamlit_app.py   (포트 8501)

백엔드 주소는 환경변수 API_BASE 로 바꿀 수 있습니다. (기본 http://127.0.0.1:8000)
"""
from __future__ import annotations

import concurrent.futures
import re
import time

import streamlit as st

import api_client as api   # FastAPI 백엔드 호출 (DB/LangGraph는 백엔드가 처리)
import ui_theme as ui


# ==========================================================================
# 1) 페이지 기본 설정 + 화면 꾸미기(CSS)
# ==========================================================================
def setup_page():
    st.set_page_config(
        page_title="NewsCrew — 뉴스레터 에이전트",
        page_icon="📰",
        layout="wide",
        initial_sidebar_state="expanded",
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
    ss.setdefault("env_menu_open", False)


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
                f"<blockquote>{_inline_md(line[2:])}</blockquote>"
            )
        else:
            html.append(f"<p style='margin:8px 0; line-height:1.75;'>{_inline_md(line)}</p>")

    close_list()
    return f"<div class='nc-draft'>{chr(10).join(html)}</div>"


def draft_title(draft: str) -> str:
    for line in draft.split("\n"):
        if line.startswith("# "):
            return line[2:].strip()
    return "뉴스레터"


STATUS_LABELS = {
    "researching": "리서치중", "writing": "작성중", "reviewing": "검수중",
    "awaiting_approval": "승인대기", "sent": "메일 발송완료",
}

# 생성 스피너 — 단계 전환 간격(초). API 응답 전까지 리서치→작성→검수 순으로 표시
_GEN_STEP_INTERVAL = 12


def _generate_with_progress(
    keywords: list[str],
    category_id: int | None,
    type_code: str | None,
    type_name: str | None,
    kw_label: str,
    progress_slot,
    category_ids: list[int] | None = None,
) -> dict:
    """단계 스피너를 보여 주며 생성 API를 호출합니다."""
    step_count = len(ui.GENERATION_STEPS)
    _, _, first_desc = ui.GENERATION_STEPS[0]
    progress_slot.markdown(
        ui.render_generation_progress(0, first_desc, kw_label),
        unsafe_allow_html=True,
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            api.generate, keywords, category_id, type_code, category_ids or None,
        )
        step_idx = 0
        started = time.time()

        while not future.done():
            elapsed = time.time() - started
            step_idx = min(step_count - 1, int(elapsed / _GEN_STEP_INTERVAL))
            _, _, desc = ui.GENERATION_STEPS[step_idx]
            progress_slot.markdown(
                ui.render_generation_progress(step_idx, desc, kw_label),
                unsafe_allow_html=True,
            )
            time.sleep(0.35)

        snap = future.result()

    progress_slot.markdown(
        ui.render_generation_progress(step_count, "모든 단계가 완료되었습니다.", kw_label, done=True),
        unsafe_allow_html=True,
    )
    return snap


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
    ui.render_page_head(
        "📝 뉴스레터용 보고서 작성",
        "관심분야·보고서 유형·메시지를 모두 입력한 뒤 '생성'을 눌러 주세요.",
    )

    detail_id = st.query_params.get("detail")
    if detail_id:
        st.query_params.clear()
        open_report(detail_id)
        return

    messages = st.session_state.messages
    for i, m in enumerate(messages):
        content = m["content"]
        report_id = m.get("report_id")
        if report_id and "<span class='link-hint'>" in content:
            content = content.replace(
                "<span class='link-hint'>더보기 →</span>",
                f"<a class='link-hint' href='?detail={report_id}'>더보기 →</a>",
            )
        st.markdown(
            ui.chat_bubble(m["role"], content, last=(i == len(messages) - 1)),
            unsafe_allow_html=True,
        )

    # (1-2) 생성 예약(pending) — 진행 카드 1개만 표시 후 키워드 추출·API 실행
    pending = st.session_state.pending
    if pending:
        kw_preview = (
            ", ".join(pending.get("label_keywords") or [])
            or pending.get("display", "")[:60]
        )
        progress_slot = st.empty()
        progress_slot.markdown(
            ui.render_generation_progress(0, ui.GENERATION_STEPS[0][2], kw_preview),
            unsafe_allow_html=True,
        )

        keywords = list(pending.get("label_keywords") or [])
        try:
            extracted = api.extract_keywords(pending["display"])
        except Exception as e:
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"키워드 추출 실패 (API 서버 확인): {e}",
            })
            st.session_state.pending = None
            st.rerun()

        for kw in extracted:
            if kw not in keywords:
                keywords.append(kw)

        if not keywords:
            st.session_state.messages.append({
                "role": "assistant",
                "content": "주제를 조금 더 구체적으로 적어 주세요.",
            })
            st.session_state.pending = None
            st.rerun()

        kw = ", ".join(keywords)
        types = pending.get("types") or [None]
        try:
            for t in types:
                tcode = t["code"] if t else None
                tname = t["name"] if t else None
                snap = _generate_with_progress(
                    keywords,
                    pending.get("category_id"),
                    tcode,
                    tname,
                    kw,
                    progress_slot,
                    category_ids=pending.get("category_ids"),
                )
                push_report_message(snap, type_name=tname)
        except Exception as e:
            st.error(f"생성 실패 — API 서버(8000)가 실행 중인지 확인하세요: {e}")
        st.session_state.pending = None
        st.rerun()

    st.markdown('<div class="nc-form-section">', unsafe_allow_html=True)

    # (2) 카테고리·타입 선택 + 메시지 입력 (통합 생성)
    try:
        catalog = api.get_flat_categories()
    except Exception as e:
        st.error(f"API 호출 실패 — 서버(8000) 실행을 확인하세요: {e}")
        catalog = []

    labels = st.multiselect(
        "관심분야 * (필수, 여러 개 가능)",
        options=[row["label"] for row in catalog],
        key="cat_select",
        placeholder="예: AI/기술 > 생성형 AI",
        disabled=not catalog,
    )
    if labels:
        kws = api.keywords_for_labels(labels, catalog)
        chips = " ".join(f"<span class='badge s-reviewing'>{kw}</span>" for kw in kws)
        st.markdown(
            f"<div class='nc-chip-row'>"
            f"<span class='label'>키워드</span> {chips}</div>",
            unsafe_allow_html=True,
        )
    elif not catalog:
        st.info("등록된 카테고리가 없습니다. '카테고리 등록'에서 추가하세요.")

    try:
        types_all = api.list_newsletter_types(active_only=True)
    except Exception:
        types_all = []
    selected_types: list[dict] = []
    if types_all:
        st.markdown(
            "<span style='color:var(--nc-muted);font-size:.85rem;font-weight:600;'>보고서 유형 * (필수, 1개 이상)</span>",
            unsafe_allow_html=True,
        )
        cols = st.columns(len(types_all))
        for col, t in zip(cols, types_all):
            if col.checkbox(t["name"], value=False, key=f"type_chk_{t['id']}"):
                selected_types.append(t)

    with st.form("chat_form", clear_on_submit=True):
        st.markdown(
            "메시지 * (필수) "
            "<span style='color:#eeee;font-size:0.85rem;'>"
            "최신 주가 정보 및 법령 등을 포함한 뉴스레터를 작성해줘"
            "</span>",
            unsafe_allow_html=True,
        )
        prompt = st.text_input(
            "메시지",
            placeholder="예: 전기차·배터리 최신 동향을 포함해서 정리해줘",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("생성", use_container_width=True)

    if submitted:
        handle_combined_submit(
            prompt, labels, catalog, selected_types,
            types_required=bool(types_all),
        )
        st.rerun()


def push_report_message(snap: dict, type_name: str | None = None, *, done_label: str = "생성 완료!"):
    """생성/재작성 결과를 채팅창에 '짧은 보고서 카드'로 추가합니다."""
    report_id = snap["thread_id"]
    st.session_state.thread_id = report_id
    st.session_state.snap = snap
    st.session_state.reports[report_id] = snap
    st.session_state.view_report = None

    draft = snap["draft"]
    title = snap.get("title") or draft_title(draft)
    type_label = type_name or snap.get("type_label") or "-"
    score = snap.get("review", {}).get("score", "-")
    st.session_state.messages.append({
        "role": "assistant",
        "report_id": report_id,
        "content": (
            f"✅ <b>{done_label}</b>"
            f"<div class='msg-meta'>"
            f"<b>제목</b> {title}<br>"
            f"<b>타입</b> {type_label}<br>"
            f"검수 {score}점 · 상태: {status_label(snap.get('status'))}"
            f"</div>"
            f"<span class='excerpt'>{draft_excerpt(draft)}</span> "
            f"<a class='link-hint' href='?detail={report_id}'>더보기 →</a>"
        ),
    })


def _build_user_request(prompt: str, labels: list[str], types: list[dict]) -> str:
    """채팅에 표시·에이전트에 전달할 통합 요청 문장을 만듭니다."""
    prompt = prompt.strip()
    type_txt = " · ".join(t["name"] for t in types) if types else ""

    if labels and prompt:
        base = f"[{', '.join(labels)}] {prompt}"
    elif labels:
        base = f"[{', '.join(labels)}] 관련 최신 소식으로 뉴스레터 만들어줘"
    else:
        base = prompt

    if type_txt and labels:
        return f"{base} · 타입: {type_txt}"
    if type_txt and not labels and prompt:
        return f"{prompt} · 타입: {type_txt}"
    return base


def handle_combined_submit(
    prompt: str,
    labels: list[str],
    catalog: list[dict],
    types: list[dict] | None = None,
    *,
    types_required: bool = False,
):
    """카테고리 선택 + 메시지를 합쳐 작성 에이전트 호출을 예약합니다."""
    types = types or []
    prompt = prompt.strip()

    if not prompt:
        st.session_state.messages.append({
            "role": "assistant",
            "content": "메시지를 입력해 주세요.",
        })
        return

    missing: list[str] = []
    if not labels:
        missing.append("관심분야")
    if types_required and not types:
        missing.append("보고서 유형")

    if missing:
        st.session_state.messages.append({
            "role": "assistant",
            "content": " · ".join(missing) + "을(를) 선택해 주세요.",
        })
        return

    display = _build_user_request(prompt, labels, types)
    st.session_state.messages.append({"role": "user", "content": display})

    by_label = {row["label"]: row["id"] for row in catalog}
    category_ids = [by_label[label] for label in labels if label in by_label]
    category_id = category_ids[0] if category_ids else None
    label_keywords = api.keywords_for_labels(labels, catalog) if labels else []

    st.session_state.pending = {
        "display": display,
        "label_keywords": label_keywords,
        "category_id": category_id,
        "category_ids": category_ids,
        "types": types or None,
    }


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
    push_report_message(snap, type_name=snap.get("type_label"), done_label="재작성 완료!")
    st.session_state.goto = "📝 뉴스레터작성"
    st.rerun()


# ==========================================================================
# 5) 화면(페이지) — 생성 결과 + 승인/반려
# ==========================================================================
def page_result():
    ui.render_page_head("📨 생성 결과", "생성된 뉴스레터를 확인하고 승인·반려·발송할 수 있습니다.")
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
        widths = [1.5, 1.4, 1.2, 1.9, 1.8, 0.6, 1.5, 0.6]
        headers = ["작성일", "관심영역", "타입", "메일내용", "상태", "점수", "관리", ""]
        status_codes = list(STATUS_LABELS.keys())
        head = st.columns(widths, vertical_alignment="center")
        for col, title in zip(head, headers):
            col.markdown(f"<div class='rhead'>{title}</div>", unsafe_allow_html=True)
        st.markdown("<hr class='rdiv head'>", unsafe_allow_html=True)

        for r in rows:
            c = st.columns(widths, vertical_alignment="center")
            created = str(r["created_at"])[:16]
            category = r.get("category") or "직접입력"
            news_type = r.get("type_label") or r.get("news_type") or "-"
            excerpt = draft_excerpt(r.get("draft") or "", 50) or "-"
            score = r.get("review_score")
            score_txt = score if score is not None else "–"
            c[0].markdown(f"<div class='rcell muted'>{created}</div>", unsafe_allow_html=True)
            c[1].markdown(f"<div class='rcell'>{category}</div>", unsafe_allow_html=True)
            c[2].markdown(f"<div class='rcell'>{news_type}</div>", unsafe_allow_html=True)
            c[3].markdown(f"<div class='rcell'>{excerpt}</div>", unsafe_allow_html=True)
            # 상태: 선택박스로 바로 수정 (변경 시 API로 저장)
            cur_status = r["status"] if r["status"] in status_codes else status_codes[0]
            new_status = c[4].selectbox(
                "상태", status_codes, index=status_codes.index(cur_status),
                format_func=status_label, key=f"st_{r['thread_id']}",
                label_visibility="collapsed")
            if new_status != cur_status:
                try:
                    api.update_status(r["thread_id"], new_status)
                except Exception as e:
                    st.error(f"상태 변경 실패: {e}")
                st.rerun()
            c[5].markdown(f"<div class='rcell muted'>{score_txt}</div>", unsafe_allow_html=True)
            if c[6].button("🔍 상세보기", key=f"view_{r['thread_id']}",
                           use_container_width=True, type="primary"):
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

    type_label = snap.get("type_label")
    type_html = (f" · 타입: <b>{type_label}</b>" if type_label else "")
    st.markdown(
        f"상태: {status_badge(snap.get('status'))} "
        f"<span style='color:var(--nc-muted);'>· 재작성 {snap.get('revision_count', 0)}회{type_html}</span>",
        unsafe_allow_html=True,
    )
    st.markdown(md_to_html(snap.get("draft", "")), unsafe_allow_html=True)

    review = snap.get("review") or {}
    if review.get("feedback"):
        st.markdown(
            ui.render_review_feedback(review["feedback"], review.get("score")),
            unsafe_allow_html=True,
        )

    reasons = review.get("deduction_reasons")
    if isinstance(reasons, dict) and any(val and val != "없음" for val in reasons.values()):
        with st.expander("📊 항목별 상세 감점 사유 확인", expanded=not review.get("passed", True)):
            for cat_key, cat_name in [
                ("structure", "🧱 구조 (도입부 Hooking & 문단 연결성)"),
                ("expression", "✨ 표현 (상투적 표현 & 동의어 반복)"),
                ("readability", "📱 가독성 (정보 완급 조절 & 예시/비유)"),
                ("tone", "🗣️ 톤앤매너 (어미 일관성 & 기계적 중립성)"),
                ("value", "💎 정보가치 (핵심 요약 & 할루시네이션)"),
            ]:
                reason_desc = reasons.get(cat_key, "없음")
                if reason_desc and reason_desc != "없음":
                    st.markdown(f"**{cat_name}**")
                    st.caption(reason_desc)
                    st.divider()

    suggested_fix = review.get("suggested_fix")
    if suggested_fix and suggested_fix != "없음":
        st.warning(f"**🛠️ AI 작성자를 위한 피드백 및 행동 지침:**  \n{suggested_fix}")

    # 발송 전(sent 아님)이면 세션과 무관하게 승인/반려 가능
    if snap["status"] != "sent":
        # 발송에 쓸 이메일 템플릿 선택 (기본 = 환경설정의 기본 템플릿)
        tpl_code = None
        try:
            templates = api.list_templates()
        except Exception:
            templates = []
        if templates:
            codes = [t["code"] for t in templates]
            name_by = {t["code"]: t["name"] for t in templates}
            default_code = _default_template_code()
            idx = codes.index(default_code) if default_code in codes else 0
            tpl_code = st.selectbox("이메일 템플릿", codes, index=idx,
                                    format_func=lambda c: name_by.get(c, c),
                                    key=f"tpl_{thread_id}")

        feedback = st.text_input("반려 시 수정 요청(선택)", placeholder="예: 더 짧고 캐주얼하게")
        c1, c2 = st.columns(2)
        if c1.button("✅ 승인 → 발송", use_container_width=True):
            try:
                st.session_state.snap = api.approve(thread_id, tpl_code)
            except Exception as e:
                st.error(f"승인 실패: {e}")
            st.rerun()
        if c2.button("↩️ 반려 → 재작성", use_container_width=True):
            handle_reject_to_chat(thread_id, feedback.strip())
    else:
        st.success("✅ 메일 발송 완료!")
        # 누구에게 언제 보냈는지 발송 내역 표시
        sends = snap.get("sends") or []
        if sends:
            st.markdown(f"**📬 발송 내역** · 총 {len(sends)}명")
            for s in sends:
                nm = f" ({s['name']})" if s.get("name") else ""
                st.write(f"- {s['email']}{nm} · {s['sent_at']}")
        else:
            st.caption("이 카테고리에 관심 있는 구독자가 없어 발송 대상이 없었습니다.")


# ==========================================================================
# 6) 화면(페이지) — 메일링리스트
# ==========================================================================
def _valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def userlists():
    ui.render_page_head("📨 메일링리스트", "뉴스레터를 받을 구독자와 관심분야를 관리합니다.")

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

    st.markdown(f"<p style='color:var(--nc-muted);font-size:.9rem;'>총 <b>{len(subs)}</b>명 구독 중</p>",
                unsafe_allow_html=True)
    for s in subs:
        c1, c2 = st.columns([6, 1])
        nm = f" ({s['name']})" if s.get("name") else ""
        cats = s.get("categories") or "관심분야 미선택"
        c1.markdown(
            ui.list_card(f"{s['email']}{nm}", f"관심분야: {cats}"),
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


def _parse_checkpoints_lines(text: str) -> list[str]:
    """체크포인트 입력 — 한 줄에 하나 (엔터 구분)."""
    out: list[str] = []
    for line in (text or "").split("\n"):
        s = line.strip()
        if s and s not in out:
            out.append(s)
    return out


def _parse_checkpoints_input(text: str) -> list[str]:
    """체크포인트 일괄 입력 — 줄 단위 또는 쉼표(,) 구분. (환경설정용)"""
    out: list[str] = []
    for part in (text or "").replace("\n", ",").split(","):
        s = part.strip()
        if s and s not in out:
            out.append(s)
    return out


def page_categories():
    ui.render_page_head("🗂️ 카테고리 등록", "뉴스레터 관심분야·키워드·체크포인트를 관리합니다.")

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
        checkpoints_text = st.text_area(
            "주요 체크포인트 (한 줄에 하나 — 엔터로 구분)",
            placeholder="예:\n어떤 모델·도구인지 명확히 했는가\n실전 적용 포인트를 제시했는가",
            height=90)
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
                                    sort_order=int(sort_order),
                                    checkpoints=_parse_checkpoints_lines(checkpoints_text))
                st.success(f"'{name.strip()}' 카테고리를 추가했습니다!")
                st.rerun()
            except Exception as e:
                st.error(f"추가 실패 (코드 중복 등 확인): {e}")

    st.divider()

    if not cats:
        st.info("아직 등록된 카테고리가 없습니다. 위에서 추가하세요.")
        return

    st.markdown(f"<p style='color:var(--nc-muted);font-size:.9rem;'>총 <b>{len(cats)}</b>개 등록됨</p>",
                unsafe_allow_html=True)
    for c in cats:
        c1, c2 = st.columns([6, 1])
        parent = f" · 상위: {c['parent_name']}" if c.get("parent_name") else ""
        kw = ", ".join(c["keywords"]) if c["keywords"] else "-"
        cps = c.get("checkpoints") or []
        active = "" if c["is_active"] else " · ⛔비활성"
        c1.markdown(
            ui.list_card(
                f"{c['name']} <code>{c['code']}</code>{parent}{active}",
                f"키워드: {kw}<br>체크포인트: {(' · '.join(cps)) if cps else '-'}",
            ),
            unsafe_allow_html=True,
        )
        if c2.button("🗑️", key=f"delcat_{c['id']}", help="삭제"):
            api.delete_category(c["id"])
            st.rerun()
        with c1.expander("✏️ 키워드 편집"):
            kw_edit = st.text_input(
                "키워드 (쉼표로 구분)",
                value=", ".join(c["keywords"]) if c["keywords"] else "",
                key=f"kw_{c['id']}",
                placeholder="예: LLM, AI 에이전트, 반도체",
            )
            if st.button("저장", key=f"kwsave_{c['id']}"):
                try:
                    api.update_keywords(c["id"], _parse_keywords_input(kw_edit))
                    st.success("키워드를 저장했습니다.")
                    st.rerun()
                except Exception as e:
                    st.error(f"저장 실패: {e}")
        with c1.expander("✏️ 체크포인트 편집"):
            cp_edit = st.text_area(
                "한 줄에 하나 (엔터로 구분)",
                value="\n".join(cps),
                key=f"cp_{c['id']}",
                height=110,
            )
            if st.button("저장", key=f"cpsave_{c['id']}"):
                try:
                    api.update_checkpoints(c["id"], _parse_checkpoints_lines(cp_edit))
                    st.success("체크포인트를 저장했습니다.")
                    st.rerun()
                except Exception as e:
                    st.error(f"저장 실패: {e}")


# ==========================================================================
# 8) 화면(페이지) — 환경설정
# ==========================================================================
def page_settings():
    ui.render_page_head("⚙️ 환경설정", "뉴스레터 자동 작성 관련 환경을 관리합니다.")

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
            elif vtype == "template":
                # 기본 이메일 템플릿 — 등록된 템플릿 목록에서 선택
                tpls = _safe_list_templates()
                codes = [t["code"] for t in tpls] or ["default"]
                name_by = {t["code"]: t["name"] for t in tpls}
                idx = codes.index(cur) if cur in codes else 0
                new_values[key] = st.selectbox(
                    label, codes, index=idx, format_func=lambda c: name_by.get(c, c),
                    help=help_, key=f"set_{key}")
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
    _settings_review_checklist()


# ==========================================================================
# 8-1) 화면(페이지) — 뉴스레터 생성 타입 관리
# ==========================================================================
def page_newsletter_types():
    ui.render_page_head(
        "🧩 뉴스레터 생성 타입",
        "요약형·트렌드분석형 등 작성 스타일 타입을 등록·수정합니다. 생성 시 선택되며 검수에도 반영됩니다.",
    )

    try:
        types = api.list_newsletter_types()
    except Exception as e:
        st.error(f"API 호출 실패 — 서버(8000) 실행을 확인하세요: {e}")
        return

    with st.form("add_type_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        name = col1.text_input("타입명 *", placeholder="예: 요약형")
        code = col2.text_input("코드 * (영문 슬러그)", placeholder="예: summary")
        desc = st.text_input("스타일 설명", placeholder="예: 핵심만 간결하게 요약하는 스타일")
        sort_order = st.number_input("정렬 순서", min_value=0, value=len(types), step=1)
        added = st.form_submit_button("➕ 타입 추가")

    if added:
        if not name.strip() or not code.strip():
            st.warning("타입명과 코드는 필수입니다.")
        else:
            try:
                api.create_newsletter_type(
                    code.strip(), name.strip(), desc.strip() or None, int(sort_order),
                )
                st.success(f"'{name.strip()}' 타입을 추가했습니다!")
                st.rerun()
            except Exception as e:
                st.error(f"추가 실패 (코드 중복 등 확인): {e}")

    st.divider()

    if not types:
        st.info("등록된 생성 타입이 없습니다. 위에서 추가하세요.")
        return

    st.markdown(
        f"<p style='color:var(--nc-muted);font-size:.9rem;'>총 <b>{len(types)}</b>개 등록됨</p>",
        unsafe_allow_html=True,
    )
    for t in types:
        c1, c2 = st.columns([6, 1])
        active = "" if t.get("is_active", 1) else " · ⛔비활성"
        c1.markdown(
            ui.list_card(
                f"{t['name']} <code>{t['code']}</code>{active}",
                t["description"] or "-",
            ),
            unsafe_allow_html=True,
        )
        if c2.button("🗑️", key=f"deltype_{t['id']}", help="삭제"):
            try:
                api.delete_newsletter_type(t["id"])
                st.rerun()
            except Exception as e:
                st.error(f"삭제 실패: {e}")
        with c1.expander("✏️ 수정"):
            new_name = st.text_input("타입명", value=t["name"], key=f"typename_{t['id']}")
            new_desc = st.text_input(
                "스타일 설명", value=t.get("description") or "", key=f"typedesc_{t['id']}",
            )
            new_order = st.number_input(
                "정렬 순서", min_value=0, value=int(t.get("sort_order") or 0),
                step=1, key=f"typeorder_{t['id']}",
            )
            new_active = st.checkbox(
                "사용", value=bool(t.get("is_active", 1)), key=f"typeactive_{t['id']}",
            )
            if st.button("저장", key=f"typesave_{t['id']}"):
                try:
                    api.update_newsletter_type(
                        t["id"],
                        name=new_name.strip(),
                        description=new_desc.strip() or None,
                        sort_order=int(new_order),
                        is_active=new_active,
                    )
                    st.success("저장했습니다.")
                    st.rerun()
                except Exception as e:
                    st.error(f"저장 실패: {e}")


# ==========================================================================
# 8-2) 화면(페이지) — 환경설정 (기본 검수 체크리스트)
# ==========================================================================
def _settings_review_checklist():
    """환경설정 화면의 '기본 검수 체크리스트' 관리 섹션."""
    st.markdown("### ✅ 기본 검수 체크리스트")
    st.caption(
        "카테고리에 체크포인트가 없을 때 검수에 사용합니다. "
        "한 줄에 하나, 또는 쉼표(,)로 여러 항목을 등록할 수 있습니다."
    )

    try:
        items = api.list_review_checklist()
    except Exception as e:
        st.error(f"체크리스트를 불러오지 못했습니다: {e}")
        return

    with st.form("add_review_checklist_form", clear_on_submit=True):
        labels_text = st.text_area(
            "체크포인트 추가",
            placeholder="예: 핵심 개념을 쉽게 설명했는가, 실제 사례를 제시했는가",
            height=90,
        )
        added = st.form_submit_button("➕ 체크포인트 추가")

    if added:
        labels = _parse_checkpoints_input(labels_text)
        if not labels:
            st.warning("추가할 체크포인트를 입력하세요.")
        else:
            try:
                api.create_review_checklist_bulk(labels)
                st.success(f"체크포인트 {len(labels)}개를 추가했습니다!")
                st.rerun()
            except Exception as e:
                st.error(f"추가 실패: {e}")

    if not items:
        st.info("등록된 기본 검수 체크리스트가 없습니다. 위에서 추가하세요.")
        return

    st.markdown(
        f"<p style='color:var(--nc-muted);font-size:.9rem;'>총 <b>{len(items)}</b>개 등록됨</p>",
        unsafe_allow_html=True,
    )
    for it in items:
        c1, c2 = st.columns([6, 1])
        active = "" if it.get("is_active", 1) else " · ⛔비활성"
        c1.markdown(
            ui.list_card(f"#{it['sort_order']} {it['label']}{active}", "-"),
            unsafe_allow_html=True,
        )
        if c2.button("🗑️", key=f"delrc_{it['id']}", help="삭제"):
            try:
                api.delete_review_checklist_item(it["id"])
                st.rerun()
            except Exception as e:
                st.error(f"삭제 실패: {e}")
        with c1.expander("✏️ 수정"):
            new_label = st.text_input("체크포인트", value=it["label"], key=f"rclabel_{it['id']}")
            new_order = st.number_input(
                "정렬 순서", min_value=0, value=int(it.get("sort_order") or 0),
                step=1, key=f"rcorder_{it['id']}",
            )
            new_active = st.checkbox(
                "사용", value=bool(it.get("is_active", 1)), key=f"rcactive_{it['id']}",
            )
            if st.button("저장", key=f"rcsave_{it['id']}"):
                try:
                    api.update_review_checklist_item(
                        it["id"], label=new_label.strip(), sort_order=int(new_order),
                        is_active=new_active,
                    )
                    st.success("저장했습니다.")
                    st.rerun()
                except Exception as e:
                    st.error(f"저장 실패: {e}")


# ==========================================================================
# 8-3) 화면(페이지) — 이메일 템플릿 등록
# ==========================================================================
def _safe_list_templates() -> list[dict]:
    try:
        return api.list_templates()
    except Exception:
        return []


def _default_template_code() -> str:
    """환경설정의 기본 이메일 템플릿 코드를 읽어 옵니다. (실패 시 'default')"""
    try:
        for s in api.get_settings():
            if s["setting_key"] == "default_template_code":
                return s["setting_value"] or "default"
    except Exception:
        pass
    return "default"


def page_templates():
    ui.render_page_head(
        "📧 이메일 템플릿 등록",
        "발송 시 사용할 HTML 템플릿을 등록합니다. "
        "{{subject}} · {{body}} · {{unsubscribe_url}} 가 자동 치환됩니다.",
    )

    templates = _safe_list_templates()

    # (1) 새 템플릿 추가
    with st.form("add_tpl_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        name = col1.text_input("템플릿명 *", placeholder="예: 깔끔한 카드형")
        code = col2.text_input("코드 * (영문 슬러그)", placeholder="예: card")
        html = st.text_area(
            "HTML * ({{body}} 자리에 본문이 들어갑니다)", height=240,
            placeholder="<div>...{{subject}}... {{body}} ...<a href='{{unsubscribe_url}}'>구독취소</a></div>")
        submitted = st.form_submit_button("➕ 템플릿 추가")

    if submitted:
        if not name.strip() or not code.strip() or not html.strip():
            st.warning("템플릿명·코드·HTML 은 필수입니다.")
        elif "{{body}}" not in html:
            st.warning("HTML 안에 본문이 들어갈 자리 {{body}} 가 반드시 있어야 합니다.")
        else:
            try:
                api.create_template(code.strip(), name.strip(), html)
                st.success(f"'{name.strip()}' 템플릿을 추가했습니다!")
                st.rerun()
            except Exception as e:
                st.error(f"추가 실패 (코드 중복 등 확인): {e}")

    st.divider()

    # (2) 등록된 템플릿 목록 + 미리보기 + 삭제
    if not templates:
        st.info("등록된 템플릿이 없습니다. 위에서 추가하세요.")
        return
    for t in templates:
        c1, c2 = st.columns([6, 1])
        c1.markdown(ui.list_card(f"{t['name']} <code>{t['code']}</code>", "HTML 이메일 템플릿"),
                    unsafe_allow_html=True)
        if c2.button("🗑️", key=f"deltpl_{t['id']}", help="삭제"):
            api.delete_template(t["id"])
            st.rerun()
        with c1.expander("👁️ 미리보기"):
            preview = (t["html"] or "").replace("{{subject}}", "미리보기 제목 — 모빌리티 뉴스레터") \
                .replace("{{body}}", "<h2>소제목</h2><p>본문 예시입니다. <strong>굵게</strong>도 됩니다.</p>"
                                     "<ul><li>항목 1</li><li>항목 2</li></ul>") \
                .replace("{{unsubscribe_url}}", "#")
            st.components.v1.html(preview, height=360, scrolling=True)


# ==========================================================================
# 8-3) 화면(페이지) — 내부 자료 (Chroma)
# ==========================================================================
def page_knowledge():
    ui.render_page_head(
        "📚 내부 자료 (지식DB)",
        "data/ 폴더의 txt·pdf를 Chroma 벡터DB에 색인합니다. "
        "생성 시 search_internal_docs 도구가 이 자료를 검색해 참고합니다.",
    )

    try:
        status = api.knowledge_status()
    except Exception as e:
        st.error(f"API 호출 실패 — 서버 실행을 확인하세요: {e}")
        return

    c1, c2 = st.columns([3, 1])
    c1.metric("색인된 조각 수", status.get("count", 0))
    if c2.button("🔄 재색인", help="data 폴더를 다시 읽어 임베딩"):
        with st.spinner("내부 자료를 다시 임베딩하는 중..."):
            try:
                res = api.knowledge_reindex()
                st.success(f"재색인 완료 — {res.get('count', 0)} 조각")
                st.rerun()
            except Exception as e:
                st.error(f"재색인 실패: {e}")
    st.caption("자료 폴더: " + " · ".join(status.get("dirs", [])))

    st.divider()
    st.markdown("### 🔍 내부 자료 검색 테스트")
    q = st.text_input("검색어", placeholder="예: 뉴스레터 발송 정책")
    if q.strip():
        try:
            hits = api.knowledge_search(q.strip(), 3)
        except Exception as e:
            st.error(f"검색 실패: {e}")
            hits = []
        if not hits:
            st.info("관련 내용을 찾지 못했습니다. (먼저 재색인했는지 확인)")
        for h in hits:
            st.markdown(
                ui.list_card(
                    f"📄 {h.get('source', '내부자료')}",
                    (h.get("text", "")[:400] + "…") if len(h.get("text", "")) > 400 else h.get("text", ""),
                ),
                unsafe_allow_html=True,
            )


# ==========================================================================
# 9) 사이드바(왼쪽 메뉴) + 페이지 전환
# ==========================================================================
PAGES = {
    "📝 뉴스레터작성": page_input,
    "📨 뉴스레터 생성 결과": page_result,
    "🗂️ 카테고리 등록": page_categories,
    "🧩 생성 타입 관리": page_newsletter_types,
    "📚 내부 자료": page_knowledge,
    "📨 메일링리스트": userlists,
    "📧 템플릿 등록": page_templates,
    "⚙️ 환경설정": page_settings,
}

# 사이드바 메뉴 — 뉴스레터 작성(평면) / 환경관리(접이식)
NEWSLETTER_MENU_ITEMS = ["📝 뉴스레터작성", "📨 뉴스레터 생성 결과"]
ENV_MENU_LABEL = "⚙️ 환경관리"
ENV_MENU_ITEMS = [
    "🗂️ 카테고리 등록",
    "🧩 생성 타입 관리",
    "📨 메일링리스트",
    "📚 내부 자료",
    "📧 템플릿 등록",
    "⚙️ 환경설정",
]


def render_sidebar() -> str:
    """사이드바: 뉴스레터 작성 메뉴 + 접이식 환경관리 메뉴."""
    pending = st.session_state.pop("goto", None)
    if pending in PAGES:
        st.session_state.menu = pending
        if pending in ENV_MENU_ITEMS:
            st.session_state.env_menu_open = True

    current = st.session_state.menu
    if current in ENV_MENU_ITEMS:
        st.session_state.env_menu_open = True

    env_open = st.session_state.env_menu_open

    with st.sidebar:
        ui.render_sidebar_brand()

        ui.render_nav_group("뉴스레터 작성")
        for label in NEWSLETTER_MENU_ITEMS:
            if st.button(label, key=f"nav_{label}", use_container_width=True,
                         type="primary" if label == current else "secondary"):
                st.session_state.menu = label
                st.rerun()

        st.markdown('<div class="nc-nav-divider"></div>', unsafe_allow_html=True)

        toggle_label = f"{'▼' if env_open else '▶'} {ENV_MENU_LABEL}"
        if st.button(
            toggle_label,
            key="nav_env_toggle",
            use_container_width=True,
            type="primary" if env_open else "secondary",
        ):
            st.session_state.env_menu_open = not env_open
            st.rerun()

        if env_open:
            for label in ENV_MENU_ITEMS:
                if st.button(
                    label,
                    key=f"nav_sub_{label}",
                    use_container_width=True,
                    type="primary" if label == current else "secondary",
                ):
                    st.session_state.menu = label
                    st.session_state.env_menu_open = True
                    st.rerun()

    return st.session_state.menu


# ==========================================================================
# 10) 프로그램 시작점
# ==========================================================================
def main():
    setup_page()
    ui.inject_global_css()
    init_state()
    choice = render_sidebar()
    ui.render_hero()
    PAGES[choice]()


main()
