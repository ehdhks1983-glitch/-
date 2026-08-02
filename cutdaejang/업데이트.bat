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
echo         켜진 상태면 새 파일이 적용되지 않습니다.
echo.

rem ── 위치 가드 (v1.22.1, 목록 33) — 이 파일이 설치 폴더 맨 위가 아니면 중단.
rem windows\ 폴더 등에 복사된 채 실행되면 cutdaejang·docs가 그 안에 또 풀려
rem 폴더가 뒤섞인다 (회원님 탐색기 스샷으로 확인된 사고).
if not exist "cutdaejang\__init__.py" (
    echo [!] 이 파일은 컷대장 설치 폴더 "맨 위"에서 실행해야 해요.
    echo     지금 위치: %CD%
    echo     "cutdaejang" 폴더와 "windows" 폴더가 나란히 보이는 곳에
    echo     업데이트.bat 을 두고 다시 실행해 주세요.
    pause
    exit /b 1
)

rem ── 새 zip 찾기 (v0.76.2) ────────────────────────────────────
rem ① 탐색기에서 zip을 "이 파일(업데이트.bat) 아이콘 위"로 끌어놓으면 %1로 들어옴 (유니코드 안전)
rem ② 그냥 더블클릭하면: 이 폴더 → 다운로드 → 바탕화면에서 최신 컷대장*.zip 자동 검색
rem    (예전 '창에 끌어놓고 Enter' 방식은 UTF-8 콘솔의 한글 입력 버그로 경로가 깨져 제거)
set "ZIP=%~1"
if defined ZIP goto :found
for %%D in ("." "%USERPROFILE%\Downloads" "%USERPROFILE%\Desktop" "%USERPROFILE%\OneDrive\바탕 화면" "%USERPROFILE%\OneDrive\Desktop") do (
    if not defined ZIP (
        for /f "delims=" %%F in ('dir /b /o-d "%%~D\컷대장*.zip" 2^>nul') do (
            if not defined ZIP set "ZIP=%%~D\%%F"
        )
    )
)
if not defined ZIP (
    echo [!] 새 컷대장 zip 파일을 찾지 못했어요.
    echo.
    echo     방법 1^) 새 zip을 [다운로드] 폴더나 이 폴더에 넣고 다시 더블클릭
    echo     방법 2^) 탐색기에서 zip 파일을 "업데이트.bat 아이콘 위"로 끌어다 놓기
    echo.
    pause
    exit /b 1
)

:found
if not exist "!ZIP!" (
    echo [!] 파일을 못 찾았어요: !ZIP!
    pause
    exit /b 1
)
for %%A in ("!ZIP!") do echo  찾은 파일: %%~nxA  (수정: %%~tA)
echo.
choice /c YN /m " 이 zip으로 업데이트할까요? [Y=예 / N=아니오]"
if errorlevel 2 exit /b 0

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
if errorlevel 1 (
    echo [!] 파일 교체에 실패했어요 — 컷대장이 켜져 있으면 완전히 끄고 다시 실행하세요.
    rmdir /s /q "!TMP!" >nul 2>nul
    pause
    exit /b 1
)
if exist "!SRC!\windows" xcopy "!SRC!\windows" ".\windows" /E /Y /I >nul
rem docs는 고객용 안내(카페가이드)만 — 내부 기획·오류 목록은 배포하지 않는다 (v1.25)
if exist "!SRC!\docs\카페가이드.txt" xcopy "!SRC!\docs\카페가이드.txt" ".\docs\" /Y /I >nul
if exist "!SRC!\판매문서" xcopy "!SRC!\판매문서" ".\판매문서" /E /Y /I >nul
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
echo    (프로그램 안 [진단 리포트]에서 버전이 위 번호와 같은지 확인!)
echo ============================================================
echo.
pause
