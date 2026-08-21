"""Build and send due-date reminders by email (mailto) or LINE."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

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
