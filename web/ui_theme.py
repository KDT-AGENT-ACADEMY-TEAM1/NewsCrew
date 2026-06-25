"""NewsCrew Streamlit UI — 네이비·골드·그레이 디자인 시스템."""
from __future__ import annotations

import streamlit as st


def inject_global_css() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;800&display=swap');

        :root {
            --nc-navy: #1a2744;
            --nc-navy-mid: #243b5c;
            --nc-navy-light: #2e4d73;
            --nc-gold: #c9a227;
            --nc-gold-light: #dbb94a;
            --nc-gold-dark: #a8861f;
            --nc-gold-soft: rgba(201, 162, 39, 0.14);
            --nc-gray-50: #f7f8fa;
            --nc-gray-100: #eef0f3;
            --nc-gray-200: #d8dce2;
            --nc-gray-400: #9aa3b2;
            --nc-gray-600: #6b7280;
            --nc-gray-800: #3d4554;
            --nc-primary: var(--nc-navy);
            --nc-accent: var(--nc-gold);
            --nc-muted: var(--nc-gray-600);
            --nc-border: var(--nc-gray-200);
            --nc-surface: #ffffff;
            --nc-surface-alt: var(--nc-gray-50);
            --nc-shadow: 0 2px 16px rgba(26, 39, 68, 0.07);
            --nc-radius: 12px;
            --nc-radius-sm: 8px;
        }

        html, body, [class*="css"] {
            font-family: 'Noto Sans KR', -apple-system, BlinkMacSystemFont, sans-serif !important;
            color: var(--nc-gray-800);
        }

        .stApp { background: var(--nc-gray-50); }

        /* ── 레이아웃 ── */
        .block-container {
            max-width: 1080px;
            padding-top: 1.2rem;
            padding-bottom: 4rem;
        }

        #MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; }
        header[data-testid="stHeader"] { height: 0; }

        /* ── 사이드바 ── */
        section[data-testid="stSidebar"] {
            background: var(--nc-navy);
            border-right: 1px solid rgba(201, 162, 39, 0.2);
        }
        section[data-testid="stSidebar"] > div { padding-top: 1.2rem; }
        section[data-testid="stSidebar"] * { color: #e8ecf2; }
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] span { color: #c8d0dc !important; }

        .nc-sidebar-brand {
            padding: 20px 16px 16px;
            margin-bottom: 10px;
            border-radius: var(--nc-radius);
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(201, 162, 39, 0.35);
            border-left: 3px solid var(--nc-gold);
        }
        .nc-sidebar-brand .brand-title {
            font-size: 1.08rem;
            font-weight: 800;
            letter-spacing: -0.2px;
            margin: 0 0 6px;
            color: #fff !important;
        }
        .nc-sidebar-brand .brand-sub {
            font-size: 0.76rem;
            margin: 0;
            line-height: 1.5;
            color: var(--nc-gray-400) !important;
        }

        .nc-nav-group {
            margin: 16px 0 6px;
            padding-left: 6px;
            font-size: 0.68rem;
            font-weight: 700;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            color: var(--nc-gold) !important;
        }

        section[data-testid="stSidebar"] .stButton > button {
            border-radius: var(--nc-radius-sm);
            font-weight: 600;
            font-size: 0.86rem;
            transition: all 0.15s ease;
        }
        section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
            background: var(--nc-gold) !important;
            color: var(--nc-navy) !important;
            border: none !important;
            box-shadow: 0 2px 8px rgba(201, 162, 39, 0.3);
        }
        section[data-testid="stSidebar"] .stButton > button[kind="secondary"] {
            background: transparent !important;
            color: #c8d0dc !important;
            border: 1px solid rgba(255, 255, 255, 0.12) !important;
        }
        section[data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover {
            background: rgba(255, 255, 255, 0.06) !important;
            border-color: rgba(201, 162, 39, 0.4) !important;
        }

        /* ── 히어로 ── */
        .nc-hero {
            text-align: center;
            padding: 32px 28px 26px;
            margin-bottom: 1.6rem;
            border-radius: var(--nc-radius);
            background: var(--nc-navy);
            border-bottom: 3px solid var(--nc-gold);
            box-shadow: var(--nc-shadow);
        }
        .nc-hero h1 {
            margin: 0 0 10px;
            font-size: 1.7rem;
            font-weight: 800;
            letter-spacing: -0.4px;
            color: #fff;
        }
        .nc-hero h1 em {
            font-style: normal;
            color: var(--nc-gold);
        }
        .nc-hero p {
            margin: 0;
            color: #a8b4c4;
            font-size: 0.92rem;
            line-height: 1.6;
        }
        .nc-hero .nc-steps {
            display: flex;
            justify-content: center;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 18px;
        }
        .nc-hero .nc-step {
            display: inline-flex;
            align-items: center;
            gap: 7px;
            padding: 6px 14px;
            border-radius: 999px;
            font-size: 0.76rem;
            font-weight: 600;
            background: rgba(255, 255, 255, 0.07);
            border: 1px solid rgba(255, 255, 255, 0.1);
            color: #c8d0dc;
        }
        .nc-hero .nc-step span {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 18px;
            height: 18px;
            border-radius: 50%;
            background: var(--nc-gold);
            color: var(--nc-navy);
            font-size: 0.65rem;
            font-weight: 800;
        }

        /* ── 페이지 제목 ── */
        .nc-page-head {
            margin: 0 0 1.2rem;
            padding: 0 0 14px 14px;
            border-left: 3px solid var(--nc-gold);
            border-bottom: 1px solid var(--nc-border);
        }
        .nc-page-head h2 {
            margin: 0 0 4px !important;
            font-size: 1.4rem !important;
            font-weight: 800 !important;
            letter-spacing: -0.3px;
            color: var(--nc-navy) !important;
        }
        .nc-page-head p {
            margin: 0;
            color: var(--nc-muted);
            font-size: 0.87rem;
        }

        /* ── 채팅 ── */
        .nc-chat-item {
            padding: 4px 0;
        }
        .nc-chat-user {
            margin: 0 0 10px;
        }
        .nc-chat-bot {
            margin: 6px 0 32px;
        }
        [data-testid="stMarkdownContainer"]:has(.nc-chat-user) {
            margin-bottom: 8px;
        }
        [data-testid="stMarkdownContainer"]:has(.nc-chat-bot) {
            margin-top: 6px;
            margin-bottom: 28px;
        }
        .nc-chat { margin-bottom: 1rem; }
        .msg {
            display: flex;
            gap: 10px;
            max-width: 88%;
            align-items: flex-start;
        }
        .msg.user { margin-left: auto; flex-direction: row-reverse; }
        .msg-avatar {
            flex-shrink: 0;
            width: 34px;
            height: 34px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.88rem;
        }
        .msg.user .msg-avatar {
            background: var(--nc-navy);
            border: 1px solid var(--nc-gold);
        }
        .msg.bot .msg-avatar {
            background: var(--nc-gray-100);
            border: 1px solid var(--nc-gray-200);
        }
        .msg-body {
            padding: 14px 18px;
            border-radius: 12px;
            line-height: 1.65;
            font-size: 0.93rem;
        }
        .msg-body .msg-meta {
            margin-top: 8px;
            font-size: 0.88rem;
            line-height: 1.7;
            color: inherit;
        }
        .msg.bot .msg-body .msg-meta { color: var(--nc-gray-800); }
        .msg.bot .msg-body .msg-meta b { color: var(--nc-navy); }
        .msg.user .msg-body {
            background: var(--nc-navy);
            color: #f0f2f5;
            border-bottom-right-radius: 3px;
            box-shadow: var(--nc-shadow);
        }
        .msg.bot .msg-body {
            background: var(--nc-surface);
            border: 1px solid var(--nc-border);
            border-bottom-left-radius: 3px;
            color: var(--nc-gray-800);
        }
        .msg.bot .msg-body .excerpt {
            color: var(--nc-muted);
            font-size: 0.87rem;
            display: block;
            margin-top: 10px;
        }
        .msg.bot .msg-body a.link-hint {
            color: var(--nc-gold-dark);
            font-weight: 700;
            text-decoration: none;
            margin-left: 4px;
        }
        .msg.bot .msg-body a.link-hint:hover { text-decoration: underline; }

        /* ── 배지 ── */
        .badge {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 4px;
            font-size: 0.74rem;
            font-weight: 600;
            line-height: 1.5;
        }
        .badge.s-reviewing { background: var(--nc-navy-light); color: #fff; }
        .badge.s-writing   { background: var(--nc-gold-soft); color: var(--nc-gold-dark); border: 1px solid rgba(201,162,39,.3); }
        .badge.s-awaiting  { background: #fff8e6; color: var(--nc-gold-dark); border: 1px solid rgba(201,162,39,.4); }
        .badge.s-sent      { background: var(--nc-gray-100); color: var(--nc-navy); border: 1px solid var(--nc-gray-200); }
        .badge.s-default   { background: var(--nc-gray-100); color: var(--nc-gray-600); }
        .nc-chip-row { margin: 0.3rem 0 0.8rem; }
        .nc-chip-row .label { color: var(--nc-muted); font-size: 0.84rem; margin-right: 6px; font-weight: 600; }

        /* ── 결과 테이블 ── */
        .rhead {
            font-weight: 700;
            color: var(--nc-navy);
            opacity: 0.7;
            padding: 6px 8px;
            font-size: 0.74rem;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }
        .rcell {
            padding: 4px 8px;
            font-size: 0.88rem;
            line-height: 1.35;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .rcell.muted { color: var(--nc-muted); font-variant-numeric: tabular-nums; }
        .rdiv { border: none; border-top: 1px solid var(--nc-border); margin: 0; }
        .rdiv.head { border-top: 2px solid var(--nc-navy); opacity: 0.15; }
        .st-key-resulttbl [data-testid="stVerticalBlock"] { gap: 0.1rem; }
        .st-key-resulttbl [data-testid="stHorizontalBlock"] { margin: 0; }
        .st-key-resulttbl .stButton > button {
            padding: 0.05rem 0.5rem;
            min-height: 0;
            line-height: 1.4;
        }

        /* ── 리스트 카드 ── */
        .nc-list-card {
            padding: 14px 18px;
            margin: 6px 0;
            border-radius: var(--nc-radius-sm);
            background: var(--nc-surface);
            border: 1px solid var(--nc-border);
            transition: border-color 0.15s ease, box-shadow 0.15s ease;
        }
        .nc-list-card:hover {
            border-color: rgba(201, 162, 39, 0.45);
            box-shadow: var(--nc-shadow);
        }
        .nc-list-card .title { font-weight: 700; font-size: 0.94rem; color: var(--nc-navy); }
        .nc-list-card .meta {
            color: var(--nc-muted);
            font-size: 0.83rem;
            line-height: 1.55;
            margin-top: 4px;
        }
        .nc-list-card code {
            font-size: 0.76rem;
            padding: 1px 6px;
            border-radius: 4px;
            background: var(--nc-gold-soft);
            color: var(--nc-gold-dark);
        }

        /* ── 폼·위젯 ── */
        [data-testid="stForm"] {
            border: 1px solid var(--nc-border);
            border-radius: var(--nc-radius);
            padding: 20px 24px;
            background: var(--nc-surface);
            box-shadow: var(--nc-shadow);
        }
        [data-testid="stExpander"] {
            border: 1px solid var(--nc-border);
            border-radius: var(--nc-radius-sm);
            background: var(--nc-surface);
        }
        [data-testid="stMetric"] {
            background: var(--nc-surface);
            border: 1px solid var(--nc-border);
            border-top: 3px solid var(--nc-gold);
            border-radius: var(--nc-radius-sm);
            padding: 16px 20px;
        }
        [data-testid="stMetric"] label { font-weight: 600 !important; color: var(--nc-navy) !important; }
        [data-testid="stMetric"] [data-testid="stMetricValue"] { color: var(--nc-navy) !important; }

        .stButton > button {
            border-radius: var(--nc-radius-sm);
            font-weight: 600;
            transition: transform 0.04s ease, box-shadow 0.15s ease;
        }
        .stButton > button[kind="primary"] {
            background: var(--nc-navy) !important;
            color: #fff !important;
            border: 1px solid var(--nc-navy) !important;
        }
        .stButton > button[kind="primary"]:hover {
            background: var(--nc-navy-mid) !important;
            box-shadow: 0 2px 10px rgba(26, 39, 68, 0.2);
        }
        .stButton > button[kind="secondary"] {
            background: var(--nc-surface) !important;
            color: var(--nc-navy) !important;
            border: 1px solid var(--nc-border) !important;
        }
        .stButton > button:active { transform: translateY(1px); }

        [data-baseweb="input"] > div,
        [data-baseweb="select"] > div,
        [data-baseweb="textarea"],
        .stTextArea textarea {
            border-radius: var(--nc-radius-sm) !important;
            border-color: var(--nc-gray-200) !important;
        }
        [data-baseweb="input"]:focus-within,
        [data-baseweb="select"]:focus-within,
        [data-baseweb="textarea"]:focus-within {
            border-color: var(--nc-gold) !important;
            box-shadow: 0 0 0 1px var(--nc-gold) !important;
        }

        hr { border-color: var(--nc-border); }
        [data-testid="stAlert"] { border-radius: var(--nc-radius-sm); }

        [data-testid="stMarkdownContainer"] h3 {
            font-weight: 700;
            font-size: 1.05rem;
            color: var(--nc-navy);
            margin: 1.2rem 0 0.5rem;
        }

        /* ── 상세 본문 ── */
        .nc-draft {
            padding: 22px 26px;
            margin: 1rem 0;
            border-radius: var(--nc-radius-sm);
            background: var(--nc-surface);
            border: 1px solid var(--nc-border);
            border-left: 3px solid var(--nc-gold);
            line-height: 1.75;
        }
        .nc-draft h2, .nc-draft h3, .nc-draft h4 {
            color: var(--nc-navy);
            margin-top: 1rem;
        }
        .nc-draft blockquote {
            color: var(--nc-muted);
            border-left: 3px solid var(--nc-gold);
            margin: 10px 0;
            padding: 4px 14px;
            background: var(--nc-gray-50);
        }

        /* ── 생성 진행 스피너 ── */
        .nc-gen-progress {
            padding: 18px 20px;
            border-radius: var(--nc-radius-sm);
            background: var(--nc-surface);
            border: 1px solid var(--nc-border);
            border-left: 3px solid var(--nc-gold);
            margin: 16px 0 24px;
        }
        .nc-gen-title {
            margin: 0 0 4px;
            font-size: 1rem;
            font-weight: 800;
            color: var(--nc-navy);
        }
        .nc-gen-sub {
            margin: 0 0 16px;
            font-size: 0.84rem;
            color: var(--nc-muted);
        }
        .nc-gen-steps {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0;
            margin-bottom: 14px;
        }
        .nc-gen-step {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 6px;
            min-width: 72px;
        }
        .nc-gen-icon {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.9rem;
            font-weight: 700;
            border: 2px solid var(--nc-gray-200);
            background: var(--nc-gray-50);
            color: var(--nc-muted);
        }
        .nc-gen-step.active .nc-gen-icon {
            border-color: var(--nc-gold);
            background: var(--nc-gold-soft);
            color: var(--nc-navy);
        }
        .nc-gen-step.done .nc-gen-icon {
            border-color: var(--nc-navy);
            background: var(--nc-navy);
            color: #fff;
        }
        .nc-gen-label {
            font-size: 0.76rem;
            font-weight: 600;
            color: var(--nc-muted);
        }
        .nc-gen-step.active .nc-gen-label { color: var(--nc-gold-dark); }
        .nc-gen-step.done .nc-gen-label { color: var(--nc-navy); }
        .nc-gen-line {
            flex: 1;
            height: 2px;
            min-width: 24px;
            max-width: 48px;
            background: var(--nc-gray-200);
            margin-bottom: 22px;
        }
        .nc-gen-line.done { background: var(--nc-navy); }
        .nc-gen-msg {
            margin: 0;
            text-align: center;
            font-size: 0.88rem;
            color: var(--nc-navy);
            font-weight: 600;
        }
        .nc-spinner {
            display: inline-block;
            width: 18px;
            height: 18px;
            border: 2px solid var(--nc-gray-200);
            border-top-color: var(--nc-gold);
            border-radius: 50%;
            animation: nc-spin 0.7s linear infinite;
        }
        @keyframes nc-spin { to { transform: rotate(360deg); } }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero() -> None:
    st.markdown(
        """
        <div class="nc-hero">
            <h1>뉴스레터 자동 생성 <em>Agent</em></h1>
            <p>키워드만 입력하면 리서치 → 작성 → 검수 → 발송까지 자동으로 진행됩니다</p>
            <div class="nc-steps">
                <span class="nc-step"><span>1</span> 리서치</span>
                <span class="nc-step"><span>2</span> 작성</span>
                <span class="nc-step"><span>3</span> 검수</span>
                <span class="nc-step"><span>4</span> 발송</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_page_head(title: str, caption: str = "") -> None:
    cap = f"<p>{caption}</p>" if caption else ""
    st.markdown(
        f'<div class="nc-page-head"><h2>{title}</h2>{cap}</div>',
        unsafe_allow_html=True,
    )


def render_sidebar_brand() -> None:
    st.markdown(
        """
        <div class="nc-sidebar-brand">
            <p class="brand-title">NewsCrew</p>
            <p class="brand-sub">AI 뉴스레터 에이전트 · LangGraph</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_nav_group(label: str) -> None:
    st.markdown(f'<div class="nc-nav-group">{label}</div>', unsafe_allow_html=True)


def chat_bubble(role: str, content: str) -> str:
    avatar = "👤" if role == "user" else "✦"
    css = "user" if role == "user" else "bot"
    return (
        f'<div class="nc-chat-item nc-chat-{css}">'
        f'<div class="msg {css}">'
        f'<div class="msg-avatar">{avatar}</div>'
        f'<div class="msg-body">{content}</div>'
        f"</div></div>"
    )


def list_card(title_html: str, meta_html: str) -> str:
    return (
        f'<div class="nc-list-card">'
        f'<div class="title">{title_html}</div>'
        f'<div class="meta">{meta_html}</div>'
        f"</div>"
    )


GENERATION_STEPS = [
    ("🔍", "리서치", "관련 자료를 수집하고 있습니다..."),
    ("✍️", "작성", "뉴스레터 초안을 작성하고 있습니다..."),
    ("🧾", "검수", "품질을 검수하고 있습니다..."),
]


def render_generation_progress(
    active_step: int,
    message: str,
    keywords: str,
    *,
    done: bool = False,
) -> str:
    """생성 단계(리서치→작성→검수) 진행 UI HTML."""
    parts: list[str] = [
        '<div class="nc-gen-progress">',
    ]
    if done:
        parts.append('<p class="nc-gen-title">생성이 완료되었습니다!</p>')
    else:
        parts.append('<p class="nc-gen-title">생성중입니다...</p>')
    parts.extend([
        f'<p class="nc-gen-sub">\'{keywords}\' 주제로 뉴스레터를 만들고 있어요</p>',
        '<div class="nc-gen-steps">',
    ])
    for i, (_icon, label, _desc) in enumerate(GENERATION_STEPS):
        if done or i < active_step:
            state = "done"
            icon_html = "✓"
        elif i == active_step:
            state = "active"
            icon_html = '<span class="nc-spinner"></span>'
        else:
            state = "pending"
            icon_html = _icon
        parts.append(
            f'<div class="nc-gen-step {state}">'
            f'<div class="nc-gen-icon">{icon_html}</div>'
            f'<div class="nc-gen-label">{label}</div></div>'
        )
        if i < len(GENERATION_STEPS) - 1:
            line_done = done or i < active_step
            parts.append(f'<div class="nc-gen-line {"done" if line_done else ""}"></div>')
    parts.append("</div>")
    parts.append(f'<p class="nc-gen-msg">{message}</p>')
    parts.append("</div>")
    return "".join(parts)
