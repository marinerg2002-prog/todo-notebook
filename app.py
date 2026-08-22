"""Todo list web app backed by Google Spreadsheets."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from whitenoise import WhiteNoise

from remind import (
    ReminderError,
    email_configured,
    format_reminder,
    line_configured,
    mailto_link,
    reminder_todos,
    send_email,
    send_line,
)
from storage import JST, StorageError, get_storage

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.wsgi_app = WhiteNoise(
    app.wsgi_app,
    root=str(Path(__file__).resolve().parent / "static"),
    prefix="/static/",
)

TITLE_MAX = 100
CONTENT_MAX = 2000


def today_str() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


def list_url(**overrides) -> str:
    params = {
        "sort": request.args.get("sort", request.form.get("sort", "created")),
        "status": request.args.get("status", request.form.get("status", "open")),
        "q": request.args.get("q", request.form.get("q", "")).strip(),
    }
    params.update(overrides)
    return url_for("index", **{key: value for key, value in params.items() if value})


def validate_form(title: str, content: str, due_date: str) -> list[str]:
    errors: list[str] = []
    if not title:
        errors.append("タイトルを書いてね。")
    elif len(title) > TITLE_MAX:
        errors.append(f"タイトルは{TITLE_MAX}文字以内にしてください。")
    if not content:
        errors.append("内容を書いてね。")
    elif len(content) > CONTENT_MAX:
        errors.append(f"内容は{CONTENT_MAX}文字以内にしてください。")
    if not due_date:
        errors.append("期日を選んでね。")
    else:
        try:
            datetime.strptime(due_date, "%Y-%m-%d")
        except ValueError:
            errors.append("期日の形式が正しくありません。")
    return errors


@app.context_processor
def inject_globals():
    return {
        "today": today_str(),
        "list_url": list_url,
    }


@app.route("/")
def index():
    sort = request.args.get("sort", "created")
    if sort not in {"created", "due"}:
        sort = "created"
    status = request.args.get("status", "open")
    if status not in {"open", "done", "all"}:
        status = "open"
    query = request.args.get("q", "").strip()
    try:
        todos = get_storage().list_todos()
    except StorageError as exc:
        flash(str(exc), "error")
        todos = []
    if sort == "due":
        todos = sorted(todos, key=lambda t: (t.due_date or "9999-99-99", t.created_at))
    else:
        todos = sorted(todos, key=lambda t: t.created_at, reverse=True)

    today = today_str()
    open_todos = [todo for todo in todos if not todo.done]
    overdue_count = sum(1 for todo in open_todos if todo.is_overdue(today))
    due_today_count = sum(1 for todo in open_todos if todo.is_today(today))

    visible = todos
    if status == "open":
        visible = open_todos
    elif status == "done":
        visible = [todo for todo in todos if todo.done]
    if query:
        needle = query.lower()
        visible = [
            todo
            for todo in visible
            if needle in todo.title.lower() or needle in todo.content.lower()
        ]

    return render_template(
        "index.html",
        todos=visible,
        total_open=len(open_todos),
        overdue_count=overdue_count,
        due_today_count=due_today_count,
        sort=sort,
        status=status,
        query=query,
        new_todo_id=session.get("new_todo_id"),
    )


@app.route("/new", methods=["GET", "POST"])
def new_todo():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        due_date = request.form.get("due_date", "").strip()
        errors = validate_form(title, content, due_date)
        if errors:
            for message in errors:
                flash(message, "error")
            return render_template(
                "form.html",
                mode="new",
                title_value=title,
                content_value=content,
                due_date_value=due_date,
            )
        try:
            todo = get_storage().create_todo(title, content, due_date)
        except StorageError as exc:
            flash(str(exc), "error")
            return render_template(
                "form.html",
                mode="new",
                title_value=title,
                content_value=content,
                due_date_value=due_date,
            )
        session["new_todo_id"] = todo.id
        return redirect(url_for("index"))

    return render_template(
        "form.html",
        mode="new",
        title_value="",
        content_value="",
        due_date_value=today_str(),
    )


@app.route("/edit/<todo_id>", methods=["GET", "POST"])
def edit_todo(todo_id: str):
    storage = get_storage()
    try:
        todo = storage.get_todo(todo_id)
    except StorageError as exc:
        flash(str(exc), "error")
        return redirect(url_for("index"))

    if todo is None:
        flash("そのタスク、見つからなかったよ。", "error")
        return redirect(url_for("index"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        due_date = request.form.get("due_date", "").strip()
        errors = validate_form(title, content, due_date)
        if errors:
            for message in errors:
                flash(message, "error")
            return render_template(
                "form.html",
                mode="edit",
                todo=todo,
                title_value=title,
                content_value=content,
                due_date_value=due_date,
            )
        try:
            storage.update_todo(todo_id, title, content, due_date)
        except StorageError as exc:
            flash(str(exc), "error")
            return render_template(
                "form.html",
                mode="edit",
                todo=todo,
                title_value=title,
                content_value=content,
                due_date_value=due_date,
            )
        flash("保存したよ！", "success")
        return redirect(url_for("index"))

    return render_template(
        "form.html",
        mode="edit",
        todo=todo,
        title_value=todo.title,
        content_value=todo.content,
        due_date_value=todo.due_date,
    )


@app.route("/done/<todo_id>", methods=["POST"])
def toggle_done(todo_id: str):
    try:
        todo = get_storage().get_todo(todo_id)
        if todo is None:
            flash("そのタスク、見つからなかったよ。", "error")
        else:
            get_storage().set_done(todo_id, not todo.done)
    except StorageError as exc:
        flash(str(exc), "error")
    return redirect(list_url())


@app.route("/delete/<todo_id>", methods=["POST"])
def delete_todo(todo_id: str):
    try:
        get_storage().delete_todo(todo_id)
        if session.get("new_todo_id") == todo_id:
            session.pop("new_todo_id", None)
    except StorageError as exc:
        flash(str(exc), "error")
    return redirect(list_url())


@app.route("/remind")
def remind():
    today = today_str()
    try:
        todos = reminder_todos(get_storage().list_todos(), today)
    except StorageError as exc:
        flash(str(exc), "error")
        todos = []
    text = format_reminder(todos, today)
    return render_template(
        "remind.html",
        todos=todos,
        reminder_text=text,
        mailto=mailto_link(text),
        email_ready=email_configured(),
        line_ready=line_configured(),
    )


@app.route("/remind/email", methods=["POST"])
def remind_email():
    today = today_str()
    try:
        todos = reminder_todos(get_storage().list_todos(), today)
        if not todos:
            flash("送るタスクがありません。", "error")
            return redirect(url_for("remind"))
        send_email(format_reminder(todos, today))
        flash("メールを送りました。", "success")
    except (StorageError, ReminderError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("remind"))


@app.route("/remind/line", methods=["POST"])
def remind_line():
    today = today_str()
    try:
        todos = reminder_todos(get_storage().list_todos(), today)
        if not todos:
            flash("送るタスクがありません。", "error")
            return redirect(url_for("remind"))
        send_line(format_reminder(todos, today))
        flash("LINEに送りました。", "success")
    except (StorageError, ReminderError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("remind"))


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
