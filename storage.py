"""Todo persistence: Google Sheets (assignment requirement) or local JSON (dev fallback)."""

from __future__ import annotations

import json
import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))

HEADERS = ["id", "title", "content", "due_date", "created_at", "updated_at", "done"]


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")


def new_id() -> str:
    return uuid.uuid4().hex[:10]


def parse_done(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "完了"}


def todo_from_record(record: dict) -> Todo:
    return Todo(
        id=str(record.get("id", "")).strip(),
        title=str(record.get("title", "")),
        content=str(record.get("content", "")),
        due_date=str(record.get("due_date", "")),
        created_at=str(record.get("created_at", "")),
        updated_at=str(record.get("updated_at", "")),
        done=parse_done(record.get("done", "")),
    )


def sheet_row(todo: Todo) -> list:
    return [
        todo.id,
        todo.title,
        todo.content,
        todo.due_date,
        todo.created_at,
        todo.updated_at,
        "TRUE" if todo.done else "",
    ]


@dataclass
class Todo:
    id: str
    title: str
    content: str
    due_date: str
    created_at: str
    updated_at: str
    done: bool = False

    def remaining_days(self, today: str) -> int | None:
        if not self.due_date:
            return None
        try:
            due = datetime.strptime(self.due_date, "%Y-%m-%d").date()
            current = datetime.strptime(today, "%Y-%m-%d").date()
            return (due - current).days
        except ValueError:
            return None

    def is_overdue(self, today: str) -> bool:
        days = self.remaining_days(today)
        return days is not None and days < 0

    def is_today(self, today: str) -> bool:
        return bool(self.due_date) and self.due_date == today

    def due_month(self) -> str:
        if len(self.due_date) >= 7:
            return self.due_date[5:7]
        return "--"

    def due_day(self) -> str:
        if len(self.due_date) >= 10:
            return self.due_date[8:10]
        return "--"


class StorageError(RuntimeError):
    """Raised when Google Sheets (or local storage) cannot be used."""


class TodoStorage(ABC):
    @abstractmethod
    def list_todos(self) -> list[Todo]:
        raise NotImplementedError

    @abstractmethod
    def get_todo(self, todo_id: str) -> Todo | None:
        raise NotImplementedError

    @abstractmethod
    def create_todo(self, title: str, content: str, due_date: str) -> Todo:
        raise NotImplementedError

    @abstractmethod
    def update_todo(self, todo_id: str, title: str, content: str, due_date: str) -> Todo:
        raise NotImplementedError

    @abstractmethod
    def set_done(self, todo_id: str, done: bool) -> Todo:
        raise NotImplementedError

    @abstractmethod
    def delete_todo(self, todo_id: str) -> None:
        raise NotImplementedError


class LocalJsonStorage(TodoStorage):
    """Fallback used when Google credentials are not configured yet."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or os.getenv("LOCAL_DATA_PATH", "data/todos.json"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write([])

    def _read(self) -> list[dict]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StorageError(f"ローカルデータの読み込みに失敗しました: {exc}") from exc

    def _write(self, rows: list[dict]) -> None:
        self.path.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_todos(self) -> list[Todo]:
        todos = [todo_from_record(row) for row in self._read()]
        return sorted(todos, key=lambda t: (t.due_date or "9999-99-99", t.created_at))

    def get_todo(self, todo_id: str) -> Todo | None:
        for todo in self.list_todos():
            if todo.id == todo_id:
                return todo
        return None

    def create_todo(self, title: str, content: str, due_date: str) -> Todo:
        rows = self._read()
        stamp = now_iso()
        todo = Todo(
            id=new_id(),
            title=title,
            content=content,
            due_date=due_date,
            created_at=stamp,
            updated_at=stamp,
            done=False,
        )
        rows.append(asdict(todo))
        self._write(rows)
        return todo

    def update_todo(self, todo_id: str, title: str, content: str, due_date: str) -> Todo:
        rows = self._read()
        for row in rows:
            if row["id"] == todo_id:
                row["title"] = title
                row["content"] = content
                row["due_date"] = due_date
                row["updated_at"] = now_iso()
                self._write(rows)
                return todo_from_record(row)
        raise StorageError("指定されたやることが見つかりませんでした。")

    def set_done(self, todo_id: str, done: bool) -> Todo:
        rows = self._read()
        for row in rows:
            if row["id"] == todo_id:
                row["done"] = done
                row["updated_at"] = now_iso()
                self._write(rows)
                return todo_from_record(row)
        raise StorageError("指定されたやることが見つかりませんでした。")

    def delete_todo(self, todo_id: str) -> None:
        rows = self._read()
        next_rows = [row for row in rows if row["id"] != todo_id]
        if len(next_rows) == len(rows):
            raise StorageError("指定されたやることが見つかりませんでした。")
        self._write(next_rows)


class GoogleSheetsStorage(TodoStorage):
    """Stores todos in a Google Spreadsheet via a service account."""

    def __init__(self) -> None:
        self.spreadsheet_id = os.getenv("SPREADSHEET_ID", "").strip()
        if not self.spreadsheet_id:
            raise StorageError(
                "環境変数 SPREADSHEET_ID が未設定です。GoogleスプレッドシートのIDを設定してください。"
            )
        self._worksheet = None

    def _client(self):
        try:
            import gspread
            from google.oauth2.service_account import Credentials
        except ImportError as exc:
            raise StorageError(
                "gspread / google-auth がインストールされていません。pip install -r requirements.txt を実行してください。"
            ) from exc

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        credentials_json = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()
        credentials_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")

        try:
            if credentials_json:
                info = json.loads(credentials_json)
                creds = Credentials.from_service_account_info(info, scopes=scopes)
            elif Path(credentials_file).exists():
                creds = Credentials.from_service_account_file(credentials_file, scopes=scopes)
            else:
                raise StorageError(
                    "Googleの認証情報が見つかりません。credentials.json を置くか、"
                    "GOOGLE_CREDENTIALS_JSON を設定してください。"
                )
            return gspread.authorize(creds)
        except StorageError:
            raise
        except json.JSONDecodeError as exc:
            raise StorageError("GOOGLE_CREDENTIALS_JSON の形式が正しくありません。") from exc
        except Exception as exc:
            raise StorageError(f"Googleスプレッドシートへの認証に失敗しました: {exc}") from exc

    def _sheet(self):
        if self._worksheet is not None:
            return self._worksheet

        import gspread

        try:
            client = self._client()
            spreadsheet = client.open_by_key(self.spreadsheet_id)
        except Exception as exc:
            raise StorageError(
                "スプレッドシートを開けませんでした。"
                "IDが正しいか、サービスアカウントに編集者権限が付与されているか確認してください。"
                f" 詳細: {exc}"
            ) from exc

        try:
            worksheet = spreadsheet.worksheet("todos")
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title="todos", rows=1000, cols=len(HEADERS))
            worksheet.append_row(HEADERS, value_input_option="USER_ENTERED")

        try:
            values = worksheet.get_all_values()
            if not values:
                worksheet.append_row(HEADERS, value_input_option="USER_ENTERED")
            else:
                current = [h.strip().lower() for h in values[0]]
                if current[:6] == ["id", "title", "content", "due_date", "created_at", "updated_at"]:
                    if len(current) < 7 or current[6] != "done":
                        if worksheet.col_count < 7:
                            worksheet.resize(cols=7)
                        worksheet.update_acell("G1", "done")
                elif current != [h.lower() for h in HEADERS]:
                    worksheet.insert_row(HEADERS, index=1)
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(f"スプレッドシートの準備に失敗しました: {exc}") from exc

        self._worksheet = worksheet
        return worksheet

    def _rows(self) -> list[dict]:
        sheet = self._sheet()
        records = sheet.get_all_records()
        todos = []
        for record in records:
            todo_id = str(record.get("id", "")).strip()
            if not todo_id:
                continue
            todos.append(
                {
                    "id": todo_id,
                    "title": str(record.get("title", "")),
                    "content": str(record.get("content", "")),
                    "due_date": str(record.get("due_date", "")),
                    "created_at": str(record.get("created_at", "")),
                    "updated_at": str(record.get("updated_at", "")),
                    "done": record.get("done", ""),
                }
            )
        return todos

    def _find_row_number(self, todo_id: str) -> int:
        sheet = self._sheet()
        cell = sheet.find(todo_id, in_column=1)
        if cell is None:
            raise StorageError("指定されたやることが見つかりませんでした。")
        return cell.row

    def list_todos(self) -> list[Todo]:
        todos = [todo_from_record(row) for row in self._rows()]
        return sorted(todos, key=lambda t: (t.due_date or "9999-99-99", t.created_at))

    def get_todo(self, todo_id: str) -> Todo | None:
        for todo in self.list_todos():
            if todo.id == todo_id:
                return todo
        return None

    def create_todo(self, title: str, content: str, due_date: str) -> Todo:
        stamp = now_iso()
        todo = Todo(
            id=new_id(),
            title=title,
            content=content,
            due_date=due_date,
            created_at=stamp,
            updated_at=stamp,
            done=False,
        )
        self._sheet().append_row(sheet_row(todo), value_input_option="USER_ENTERED")
        return todo

    def update_todo(self, todo_id: str, title: str, content: str, due_date: str) -> Todo:
        existing = self.get_todo(todo_id)
        if existing is None:
            raise StorageError("指定されたやることが見つかりませんでした。")
        updated = Todo(
            id=existing.id,
            title=title,
            content=content,
            due_date=due_date,
            created_at=existing.created_at,
            updated_at=now_iso(),
            done=existing.done,
        )
        row_number = self._find_row_number(todo_id)
        self._sheet().update(
            f"A{row_number}:G{row_number}",
            [sheet_row(updated)],
            value_input_option="USER_ENTERED",
        )
        return updated

    def set_done(self, todo_id: str, done: bool) -> Todo:
        existing = self.get_todo(todo_id)
        if existing is None:
            raise StorageError("指定されたやることが見つかりませんでした。")
        updated = Todo(
            id=existing.id,
            title=existing.title,
            content=existing.content,
            due_date=existing.due_date,
            created_at=existing.created_at,
            updated_at=now_iso(),
            done=done,
        )
        row_number = self._find_row_number(todo_id)
        self._sheet().update(
            f"A{row_number}:G{row_number}",
            [sheet_row(updated)],
            value_input_option="USER_ENTERED",
        )
        return updated

    def delete_todo(self, todo_id: str) -> None:
        row_number = self._find_row_number(todo_id)
        self._sheet().delete_rows(row_number)


_storage: TodoStorage | None = None
_using_local: bool = False


def using_local_storage() -> bool:
    return _using_local


def get_storage() -> TodoStorage:
    global _storage, _using_local
    if _storage is not None:
        return _storage

    force_local = os.getenv("USE_LOCAL_STORAGE", "").strip().lower() in {"1", "true", "yes"}
    has_sheet_id = bool(os.getenv("SPREADSHEET_ID", "").strip())
    has_creds = bool(os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()) or Path(
        os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    ).exists()

    if force_local or not (has_sheet_id and has_creds):
        _storage = LocalJsonStorage()
        _using_local = True
        return _storage

    _storage = GoogleSheetsStorage()
    _using_local = False
    return _storage


def reset_storage_cache() -> None:
    global _storage, _using_local
    _storage = None
    _using_local = False
