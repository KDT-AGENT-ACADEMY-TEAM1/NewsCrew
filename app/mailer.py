"""이메일 발송 — 승인된 뉴스레터를 '그 카테고리에 관심 있는 구독자'에게 보냅니다.

SMTP 환경변수(SMTP_HOST 등)가 없으면 '가짜(Mock) 모드'로 동작해 실제 발송 없이
대상만 출력합니다. (메일 서버 없이도 흐름을 확인할 수 있게)

설정 환경변수:
  SMTP_HOST / SMTP_PORT(기본 587) / SMTP_USER / SMTP_PASSWORD
  SMTP_FROM(기본 SMTP_USER) / SMTP_TLS(기본 1=켬)
"""
from __future__ import annotations

import os
import re
import smtplib
from email.mime.text import MIMEText

from . import db
from .db import connection

from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()


def _smtp_config() -> dict | None:
    """SMTP 설정을 환경변수에서 읽습니다. SMTP_HOST 가 없으면 None(=가짜 모드)."""
    host = os.getenv("SMTP_HOST")
    if not host:
        return None
    user = os.getenv("SMTP_USER")
    return {
        "host": host,
        "port": int(os.getenv("SMTP_PORT", "587")),
        "user": user,
        "password": os.getenv("SMTP_PASSWORD"),
        "from": os.getenv("SMTP_FROM", user or "newsletter@example.com"),
        "use_tls": os.getenv("SMTP_TLS", "1") != "0",
    }


def subscribers_for_category(category_id: int | None) -> list[dict]:
    """해당 카테고리에 관심 있는 활성 구독자 목록을 가져옵니다.

    category_id 가 None(직접입력 등)이면 전체 활성 구독자에게 보냅니다.
    """
    if category_id:
        return db.fetch_all(
            "SELECT DISTINCT s.email, s.name "
            "FROM subscriber s "
            "JOIN subscriber_interest si ON si.subscriber_id = s.id "
            "WHERE s.is_active = 1 AND si.category_id = %s",
            (category_id,),
        )
    return db.fetch_all("SELECT email, name FROM subscriber WHERE is_active = 1")


def _inline_md(text: str) -> str:
    """문장 안의 **굵게** 를 <strong> 으로 바꿉니다."""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)


def _markdown_to_html_body(markdown: str) -> str:
    """마크다운 본문(##, -, > 등)을 인라인 스타일이 적용된 HTML 조각으로 바꿉니다.

    이메일 클라이언트는 외부 CSS를 잘 못 읽으므로 스타일을 인라인으로 박아 넣습니다.
    맨 위 '# 제목' 줄은 헤더에서 따로 보여 주므로 본문에서는 건너뜁니다.
    """
    html: list[str] = []
    in_list = False
    title_skipped = False

    def close_list():
        nonlocal in_list
        if in_list:
            html.append("</ul>")
            in_list = False

    for raw in (markdown or "").split("\n"):
        line = raw.strip()
        if not line:
            close_list()
            continue
        if line.startswith("# ") and not title_skipped:
            title_skipped = True            # 대제목은 헤더에 있으니 본문에서 제외
            continue
        if line.startswith(("- ", "* ")):
            if not in_list:
                html.append("<ul style='margin:10px 0 10px 20px; padding:0; color:#333;'>")
                in_list = True
            html.append(f"<li style='margin:5px 0; line-height:1.7; font-size:15px;'>{_inline_md(line[2:])}</li>")
            continue
        close_list()
        if line.startswith("### "):
            html.append(f"<h3 style='font-size:16px; color:#222; margin:18px 0 6px;'>{_inline_md(line[4:])}</h3>")
        elif line.startswith("## "):
            html.append("<h2 style='font-size:19px; color:#1a1a1a; margin:24px 0 10px; "
                        "padding-bottom:6px; border-bottom:2px solid #eef0f4;'>"
                        f"{_inline_md(line[3:])}</h2>")
        elif line.startswith("# "):
            html.append(f"<h2 style='font-size:20px; color:#111; margin:18px 0 10px;'>{_inline_md(line[2:])}</h2>")
        elif line.startswith("> "):
            html.append("<blockquote style='margin:12px 0; padding:10px 16px; "
                        "border-left:4px solid #5681d0; background:#f5f7fb; color:#555;'>"
                        f"{_inline_md(line[2:])}</blockquote>")
        else:
            html.append(f"<p style='margin:12px 0; line-height:1.8; color:#333; font-size:15px;'>{_inline_md(line)}</p>")

    close_list()
    return "\n".join(html)


# 템플릿이 하나도 없을 때를 대비한 최소 폴백
_FALLBACK_TEMPLATE = (
    "<div style=\"max-width:640px;margin:0 auto;font-family:'Malgun Gothic',Arial,sans-serif;\">"
    "<h1 style='font-size:22px;'>{{subject}}</h1>{{body}}"
    "<hr><p style='font-size:12px;color:#999;'>ⓒ NewsCrew 팀 · "
    "<a href='{{unsubscribe_url}}'>구독취소</a></p></div>"
)


def render_template(template_html: str | None, subject: str, markdown_body: str) -> str:
    """템플릿 HTML 의 치환자({{subject}}/{{body}}/{{unsubscribe_url}})를 채워 메일 HTML을 만듭니다.

    {{body}} 에는 마크다운 초안을 HTML로 변환한 내용이 들어갑니다.
    """
    inner = _markdown_to_html_body(markdown_body)
    unsub_url = os.getenv("UNSUBSCRIBE_URL", "#")
    html = template_html or _FALLBACK_TEMPLATE
    return (html.replace("{{subject}}", subject)
                .replace("{{body}}", inner)
                .replace("{{unsubscribe_url}}", unsub_url))


def _resolve_template_html(template_code: str | None) -> str | None:
    """발송에 쓸 템플릿 HTML을 정합니다.

    1) 지정된 template_code, 2) 환경설정의 기본 템플릿, 순으로 찾습니다.
    """
    code = template_code or db.get_setting("default_template_code", "default")
    html = db.get_template_html(code)
    if html is None and code != "default":
        html = db.get_template_html("default")   # 마지막 폴백
    return html


def _send_one(addr: str, subject: str, html_body: str, cfg: dict) -> None:
    """SMTP로 HTML 메일 한 통을 보냅니다."""
    msg = MIMEText(html_body, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = cfg["from"]
    msg["To"] = addr
    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as smtp:
        if cfg["use_tls"]:
            smtp.starttls()
        if cfg["user"]:
            smtp.login(cfg["user"], cfg["password"])
        smtp.sendmail(cfg["from"], [addr], msg.as_string())


def _record_sends(thread_id: str, recipients: list[dict]) -> None:
    """발송 대상(누구에게)·발송시각(언제)을 newsletter_send 에 기록합니다.

    같은 보고서를 다시 발송하면 이전 기록을 지우고 새로 남깁니다(중복 방지).
    """
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM newsletter_send WHERE thread_id = %s", (thread_id,))
            if recipients:
                cur.executemany(
                    "INSERT INTO newsletter_send (thread_id, email, name) VALUES (%s, %s, %s)",
                    [(thread_id, r["email"], r.get("name")) for r in recipients],
                )


def send_newsletter(thread_id: str, category_id: int | None,
                    subject: str, body: str, template_code: str | None = None) -> dict:
    """카테고리 관심 구독자에게 뉴스레터를 발송하고, 발송 이력을 기록합니다.

    template_code: 사용할 이메일 템플릿(없으면 환경설정의 기본 템플릿).
    돌려주는 값: {recipients: 대상 수, sent: 실제 발송 수, mock: 가짜모드 여부, emails: [...]}
    """
    recipients = subscribers_for_category(category_id)
    emails = [r["email"] for r in recipients]
    cfg = _smtp_config()

    if cfg is None:   # 가짜 모드 — 실제 발송 없이 대상만 기록/출력
        print(f"[메일][테스트모드] '{subject}'(템플릿={template_code or '기본'}) "
              f"→ {len(emails)}명 대상: {emails}")
        _record_sends(thread_id, recipients)
        return {"recipients": len(emails), "sent": 0, "mock": True, "emails": emails}

    # 선택된(또는 기본) 템플릿에 제목·본문을 채워 메일 HTML 생성
    template_html = _resolve_template_html(template_code)
    html_body = render_template(template_html, subject, body)
    sent_ok = []
    for r in recipients:
        try:
            _send_one(r["email"], subject, html_body, cfg)
            sent_ok.append(r)
        except Exception as e:
            print(f"[메일] {r['email']} 발송 실패: {e}")
    _record_sends(thread_id, sent_ok)   # 실제 보낸 사람만 기록
    print(f"[메일] '{subject}' 발송 완료: {len(sent_ok)}/{len(emails)}명")
    return {"recipients": len(emails), "sent": len(sent_ok), "mock": False, "emails": emails}
