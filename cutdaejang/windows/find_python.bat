@echo off
rem 컷대장 파이썬 찾기 (v1.19 설치포함 풀버전) — 호출한 bat에 PY 변수를 채워줍니다.
rem 우선순위: ① 동봉 파이썬(windows\python\ — 설치포함 zip에 들어 있음)
rem           ② PATH에 잡힌 python  ③ 사용자 폴더에 설치된 Python 3.x
rem 이 파일은 setlocal을 쓰지 않습니다 — PY 변수가 호출한 쪽에 남아야 해서요.
set "PY="
if exist "%~dp0python\python.exe" set "PY=%~dp0python\python.exe"
if defined PY goto :eof
python --version >nul 2>nul
if not errorlevel 1 set "PY=python"
if defined PY goto :eof
for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" set "PY=%%D\python.exe"
)
