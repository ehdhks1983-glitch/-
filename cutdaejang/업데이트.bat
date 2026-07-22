@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
title 컷대장 업데이트

echo ============================================================
echo    [UPDATE] 컷대장 업데이트 도우미
echo ------------------------------------------------------------
echo    프로그램만 새 버전으로 바꾸고, 아래는 그대로 지켜요:
echo      - 설정(settings.json)  - API 키(api_keys.json)
echo      - 받아둔 글씨체 - 효과음 - FFmpeg
echo ============================================================
echo.
echo  [중요] 먼저 컷대장을 완전히 끄세요 (검은 서버 창도 X로 닫기).
echo         켜진 상태면 파일이 잠겨서 교체가 안 됩니다.
echo.
echo  새로 받은 zip 파일을 이 창에 마우스로 끌어다 놓고 Enter:
set "ZIP="
set /p "ZIP=> "
set "ZIP=!ZIP:"=!"
if not defined ZIP ( echo. & echo [!] 아무것도 안 들어왔어요. 다시 실행해 zip을 끌어다 놓으세요. & pause & exit /b 1 )
if not exist "!ZIP!" ( echo. & echo [!] 파일을 못 찾았어요: !ZIP! & pause & exit /b 1 )

set "TMP=%TEMP%\cutdaejang_update"
if exist "!TMP!" rmdir /s /q "!TMP!" >nul 2>nul
echo.
echo  [1/3] 압축 푸는 중...
powershell -NoProfile -Command "try { Expand-Archive -Force -LiteralPath '!ZIP!' -DestinationPath '!TMP!' } catch { exit 1 }"
if errorlevel 1 ( echo [!] 압축 풀기 실패 — 올바른 zip 파일인지 확인하세요. & pause & exit /b 1 )

rem 압축 안에서 프로그램 폴더(cutdaejang\__init__.py) 위치 찾기 — 바로 아래 또는 한 겹 안
set "SRC="
if exist "!TMP!\cutdaejang\__init__.py" set "SRC=!TMP!"
if not defined SRC for /d %%D in ("!TMP!\*") do if exist "%%D\cutdaejang\__init__.py" set "SRC=%%D"
if not defined SRC ( echo [!] zip 안에서 컷대장 프로그램 폴더를 못 찾았어요. 컷대장 zip이 맞는지 확인하세요. & rmdir /s /q "!TMP!" >nul 2>nul & pause & exit /b 1 )

echo  [2/3] 프로그램 파일 교체 중... (받아둔 글씨체·효과음·ffmpeg는 그대로 둡니다)
rem xcopy는 원본에 없는 기존 파일(받은 글씨체·ffmpeg 등)은 지우지 않아 안전
xcopy "!SRC!\cutdaejang" ".\cutdaejang" /E /Y /I >nul
if exist "!SRC!\windows" xcopy "!SRC!\windows" ".\windows" /E /Y /I >nul
if exist "!SRC!\docs" xcopy "!SRC!\docs" ".\docs" /E /Y /I >nul
rem [주의] 업데이트.bat(이 파일)는 지금 실행 중이라 덮어쓰면 실행이 깨질 수 있어 제외합니다.
for %%F in (README.md 실행가이드.md pyproject.toml .gitignore .gitattributes) do (
    if exist "!SRC!\%%F" copy /Y "!SRC!\%%F" ".\%%F" >nul 2>nul
)
rmdir /s /q "!TMP!" >nul 2>nul

echo  [3/3] 완료 확인 중...
echo.
echo ============================================================
echo    [OK] 업데이트 완료!  (설정·API키는 그대로 유지됨)
powershell -NoProfile -Command "(Select-String -Path '.\cutdaejang\__init__.py' -Pattern '__version__').Line" 2>nul
echo ------------------------------------------------------------
echo    이제 windows\2_UI실행.bat 로 실행하세요.
echo    (프로그램 안 [진단 리포트]에서 버전이 새 번호로 바뀌었는지 확인!)
echo ============================================================
echo.
pause
