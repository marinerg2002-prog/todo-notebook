import json
import tempfile
import unittest
from pathlib import Path

from storage import LocalJsonStorage, StorageError


class LocalJsonStorageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "todos.json"
        self.storage = LocalJsonStorage(self.path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_create_list_update_delete(self) -> None:
        created = self.storage.create_todo("課題", "レポートを書く", "2026-08-20")
        todos = self.storage.list_todos()
        self.assertEqual(len(todos), 1)
        self.assertEqual(todos[0].title, "課題")
        self.assertEqual(todos[0].content, "レポートを書く")
        self.assertEqual(todos[0].due_date, "2026-08-20")

        updated = self.storage.update_todo(created.id, "課題提出", "提出前に見直す", "2026-08-21")
        self.assertEqual(updated.title, "課題提出")
        self.assertEqual(self.storage.get_todo(created.id).due_date, "2026-08-21")

        self.storage.delete_todo(created.id)
        self.assertEqual(self.storage.list_todos(), [])

    def test_set_done(self) -> None:
        created = self.storage.create_todo("課題", "書く", "2026-08-20")
        self.assertFalse(created.done)
        updated = self.storage.set_done(created.id, True)
        self.assertTrue(updated.done)
        self.assertTrue(self.storage.get_todo(created.id).done)

    def test_update_missing_raises(self) -> None:
        with self.assertRaises(StorageError):
            self.storage.update_todo("missing", "a", "b", "2026-08-20")


class FlaskAppTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "todos.json"
        import os

        os.environ["USE_LOCAL_STORAGE"] = "true"
        os.environ["LOCAL_DATA_PATH"] = str(self.path)
        os.environ["SECRET_KEY"] = "test"

        import storage
        import app as app_module

        storage.reset_storage_cache()
        self.client = app_module.app.test_client()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_register_and_edit_flow(self) -> None:
        list_page = self.client.get("/")
        self.assertEqual(list_page.status_code, 200)
        self.assertIn("タスクはありません".encode("utf-8"), list_page.data)

        created = self.client.post(
            "/new",
            data={
                "title": "買い物",
                "content": "牛乳を買う",
                "due_date": "2026-08-22",
            },
            follow_redirects=True,
        )
        self.assertEqual(created.status_code, 200)
        self.assertIn("買い物".encode("utf-8"), created.data)
        self.assertIn("牛乳を買う".encode("utf-8"), created.data)
        self.assertIn("New！".encode("utf-8"), created.data)
        self.assertNotIn("追加したよ！".encode("utf-8"), created.data)

        payload = json.loads(self.path.read_text(encoding="utf-8"))
        todo_id = payload[0]["id"]

        edited = self.client.post(
            f"/edit/{todo_id}",
            data={
                "title": "買い物リスト",
                "content": "牛乳とパンを買う",
                "due_date": "2026-08-23",
            },
            follow_redirects=True,
        )
        self.assertEqual(edited.status_code, 200)
        self.assertIn("買い物リスト".encode("utf-8"), edited.data)
        self.assertIn("牛乳とパンを買う".encode("utf-8"), edited.data)

    def test_complete_search_and_remind(self) -> None:
        self.client.post(
            "/new",
            data={"title": "レポート", "content": "3章まで書く", "due_date": "2026-08-20"},
            follow_redirects=True,
        )
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        todo_id = payload[0]["id"]

        searched = self.client.get("/?q=レポート")
        self.assertIn("レポート".encode("utf-8"), searched.data)
        hidden = self.client.get("/?q=存在しない単語")
        self.assertIn("みつかりませんでした".encode("utf-8"), hidden.data)

        done = self.client.post(f"/done/{todo_id}", follow_redirects=True)
        self.assertEqual(done.status_code, 200)
        self.assertIn("タスクはありません".encode("utf-8"), done.data)
        completed = self.client.get("/?status=done")
        self.assertIn("レポート".encode("utf-8"), completed.data)
        self.assertIn("完了".encode("utf-8"), completed.data)

        remind_page = self.client.get("/remind")
        self.assertEqual(remind_page.status_code, 200)
        self.assertIn("いま急ぐタスクはないよ".encode("utf-8"), remind_page.data)


if __name__ == "__main__":
    unittest.main()
