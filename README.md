# TODO NOTEBOOK

Python（Flask）で作った Todo リストです。やることは **タイトル・内容・期日** の3項目で登録・編集でき、一覧ページで確認できます。データの保存先は課題どおり **Google スプレッドシート** です。

認証情報をまだ用意していない場合は、自動でローカルJSONに保存して動きます。課題提出前にスプレッドシートへ切り替えてください。

## できること

- やることの登録
- やることの編集（タイトル・内容・期日）
- 登録したやることの一覧表示（期日が近い順）
- Google スプレッドシートへの保存
- サーバー公開（Render）

## 必要なもの

- Python 3.10 以降
- Google アカウント（スプレッドシート保存時）
- GitHub アカウント（サーバー公開時）

## まずはローカルで動かす

```powershell
cd C:\Users\user\Desktop\todo-app
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

ブラウザで [http://127.0.0.1:5000](http://127.0.0.1:5000) を開きます。

初期状態では `.env` の `USE_LOCAL_STORAGE=true` により、`data/todos.json` へ保存します。画面上部にその旨の案内が出ます。

## Google スプレッドシートに保存する

### 1. スプレッドシートを作る

1. [Google スプレッドシート](https://sheets.google.com) で新規作成する
2. シート名は何でもよい（アプリが `todos` というワークシートを自動作成します）
3. URL の次の部分がスプレッドシート ID です

```
https://docs.google.com/spreadsheets/d/ここがSPREADSHEET_ID/edit
```

### 2. Google Cloud でサービスアカウントを作る

1. [Google Cloud Console](https://console.cloud.google.com/) を開く
2. 新しいプロジェクトを作成する
3. 「APIとサービス」→「ライブラリ」から次を有効化する
   - Google Sheets API
   - Google Drive API
4. 「APIとサービス」→「認証情報」→「認証情報を作成」→「サービスアカウント」
5. 作成後、「キー」タブ → 「鍵を追加」→ JSON を作成
6. ダウンロードした JSON をこのフォルダに置き、ファイル名を `credentials.json` にする

JSON の中の `client_email`（`xxxxx@....iam.gserviceaccount.com`）を控えてください。

### 3. スプレッドシートを共有する

スプレッドシートの「共有」に、サービスアカウントの `client_email` を追加し、権限を **編集者** にします。これを忘れると読み書きできません。

### 4. アプリの設定

`.env.example` をコピーして `.env` を作り、次のようにします。

```env
SECRET_KEY=自分で決めた長い文字列
SPREADSHEET_ID=手順1で控えたID
GOOGLE_CREDENTIALS_FILE=credentials.json
USE_LOCAL_STORAGE=false
```

もう一度 `python app.py` を起動し、Todo を1件登録してください。スプレッドシートに `todos` シートができ、次の列で保存されます。

| id | title | content | due_date | created_at | updated_at |
| --- | --- | --- | --- | --- | --- |

## サーバーで公開する（Render）

Windows 上の `python app.py` は自分の PC だけで見えます。講座の「サーバーで公開」には、無料の [Render](https://render.com/) が使えます。

### 1. GitHub に上げる

```powershell
git init
git add .
git commit -m "Add todo app with Google Sheets storage"
```

GitHub で新しいリポジトリを作り、案内どおり `git remote add` と `git push` します。  
`credentials.json` と `.env` は `.gitignore` 済みなので、秘密情報は公開されません。

### 2. Render で Web Service を作る

1. [Render](https://render.com/) に GitHub アカウントで登録する
2. 「New」→「Web Service」→ このリポジトリを選ぶ
3. 設定例
   - Runtime: Python
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn --bind 0.0.0.0:$PORT app:app`
4. Environment に次を入れる

| Key | Value |
| --- | --- |
| `SECRET_KEY` | 長いランダム文字列 |
| `SPREADSHEET_ID` | スプレッドシート ID |
| `USE_LOCAL_STORAGE` | `false` |
| `GOOGLE_CREDENTIALS_JSON` | `credentials.json` の中身を **1行のJSON** として貼る |

JSON を1行にする例（PowerShell）:

```powershell
(Get-Content .\credentials.json -Raw) -replace '\s+', ' '
```

表示された URL（例: `https://xxxx.onrender.com`）が公開アドレスです。無料プランは初回アクセスで数十秒かかることがあります。

## 画面構成

- `/` … やること一覧
- `/new` … 登録
- `/edit/<id>` … 編集

## トラブルシューティング

- **スプレッドシートを開けませんでした**  
  サービスアカウントのメールアドレスを、スプレッドシートの編集者として共有しているか確認してください。
- **認証情報が見つかりません**  
  ローカルなら `credentials.json`、Render なら `GOOGLE_CREDENTIALS_JSON` を設定してください。
- **画面上部が「ローカルファイルに保存」のまま**  
  `.env` の `USE_LOCAL_STORAGE` を `false` にし、`SPREADSHEET_ID` と認証情報がある状態で再起動してください。
