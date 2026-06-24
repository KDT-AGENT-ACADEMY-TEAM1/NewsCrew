"""이메일 발송 — 승인된 뉴스레터를 '그 카테고리에 관심 있는 구독자'에게 보냅니다.

SMTP 환경변수(SMTP_HOST 등)가 없으면 '가짜(Mock) 모드'로 동작해 실제 발송 없이
대상만 출력합니다. (메일 서버 없이도 흐름을 확인할 수 있게)

설정 환경변수:
  SMTP_HOST / SMTP_PORT(기본 587) / SMTP_USER / SMTP_PASSWORD
  SMTP_FROM(기본 SMTP_USER) / SMTP_TLS(기본 1=켬)
"""
from __future__ import annotations

import os
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


def _send_one(addr: str, subject: str, body: str, cfg: dict) -> None:
    """SMTP로 메일 한 통을 보냅니다. (본문은 일반 텍스트)"""
    msg = MIMEText(body, "plain", "utf-8")
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
                    subject: str, body: str) -> dict:
    """카테고리 관심 구독자에게 뉴스레터를 발송하고, 발송 이력을 기록합니다.

    돌려주는 값: {recipients: 대상 수, sent: 실제 발송 수, mock: 가짜모드 여부, emails: [...]}
    """
    recipients = subscribers_for_category(category_id)
    emails = [r["email"] for r in recipients]
    cfg = _smtp_config()

    if cfg is None:   # 가짜 모드 — 실제 발송 없이 대상만 기록/출력
        print(f"[메일][테스트모드] '{subject}' → {len(emails)}명 대상: {emails}")
        _record_sends(thread_id, recipients)
        return {"recipients": len(emails), "sent": 0, "mock": True, "emails": emails}

    sent_ok = []
    for r in recipients:
        try:
            _send_one(r["email"], subject, body, cfg)
            sent_ok.append(r)
        except Exception as e:
            print(f"[메일] {r['email']} 발송 실패: {e}")
    _record_sends(thread_id, sent_ok)   # 실제 보낸 사람만 기록
    print(f"[메일] '{subject}' 발송 완료: {len(sent_ok)}/{len(emails)}명")
    return {"recipients": len(emails), "sent": len(sent_ok), "mock": False, "emails": emails}
