@echo off
cd /d "%~dp0"
title TODO NOTEBOOK
echo TODO NOTEBOOK を起動しています...
echo ブラウザで http://127.0.0.1:5000 を開いてください。
echo.
echo この黒い画面を閉じるとアプリは止まります。
echo.
".venv\Scripts\python.exe" app.py
pause
