"""Build and send due-date reminders by email or LINE."""

from __future__ import annotations

import json
import os
import smtplib
import urllib.error
import urllib.parse
import urllib.request
from email.mime.text import MIMEText

from storage import Todo


class ReminderError(RuntimeError):
    pass


def reminder_todos(todos: list[Todo], today: str) -> list[Todo]:
    return [todo for todo in todos if not todo.done and (todo.is_overdue(today) or todo.is_today(today))]


def format_reminder(todos: list[Todo], today: str) -> str:
    if not todos:
        return "今日まで・期限ぎれの未完了タスクはありません。"
    lines = ["【TODO NOTEBOOK】今日のリマインド", ""]
    for todo in todos:
        flag = "期限ぎれ" if todo.is_overdue(today) else "今日まで"
        lines.append(f"・{todo.title}（{flag} / {todo.due_date}）")
        if todo.content:
            lines.append(f"  {todo.content}")
    return "\n".join(lines)


def mailto_link(text: str) -> str:
    subject = urllib.parse.quote("TODO NOTEBOOK リマインド")
    body = urllib.parse.quote(text)
    return f"mailto:?subject={subject}&body={body}"


def email_configured() -> bool:
    return bool(os.getenv("SMTP_USER", "").strip() and os.getenv("SMTP_PASSWORD", "").strip())


def send_email(text: str) -> None:
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    if not user or not password:
        raise ReminderError(
            "メールが未設定です。Render の環境変数に SMTP_USER と SMTP_PASSWORD を入れてください。"
        )
    to_addr = os.getenv("REMINDER_TO", "").strip() or user
    host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip() or "smtp.gmail.com"
    port = int(os.getenv("SMTP_PORT", "587") or "587")

    message = MIMEText(text, "plain", "utf-8")
    message["Subject"] = "TODO NOTEBOOK リマインド"
    message["From"] = user
    message["To"] = to_addr
    try:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.send_message(message)
    except smtplib.SMTPException as exc:
        raise ReminderError(f"メールの送信に失敗しました: {exc}") from exc
    except OSError as exc:
        raise ReminderError(f"メールサーバーに接続できませんでした: {exc}") from exc


def line_configured() -> bool:
    return bool(
        os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
        and os.getenv("LINE_USER_ID", "").strip()
    )


def send_line(text: str) -> None:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    user_id = os.getenv("LINE_USER_ID", "").strip()
    if not token or not user_id:
        raise ReminderError(
            "LINEが未設定です。Render の環境変数に LINE_CHANNEL_ACCESS_TOKEN と LINE_USER_ID を入れてください。"
        )
    payload = json.dumps(
        {
            "to": user_id,
            "messages": [{"type": "text", "text": text[:4900]}],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.line.me/v2/bot/message/push",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        urllib.request.urlopen(request, timeout=20)
    except urllib.error.HTTPError as exc:
        raise ReminderError(f"LINEへの送信に失敗しました: {exc.read().decode('utf-8', 'replace')}") from exc
    except urllib.error.URLError as exc:
        raise ReminderError(f"LINEへの送信に失敗しました: {exc}") from exc
