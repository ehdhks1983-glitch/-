@echo off
chcp 65001 >nul
rem 검은 서버 창을 자동 최소화로 연다 (v1.50 목록 100) — 자기 자신을 /min으로 한 번 재실행
if not defined CUTDAEJANG_MINIMIZED (
    set "CUTDAEJANG_MINIMIZED=1"
    start "컷대장 서버" /min cmd /c ""%~f0" %*"
    exit /b
)
setlocal
cd /d "%~dp0.."

rem 파이썬 찾기 — 설치포함 풀버전이면 동봉본(windows\python)이 바로 잡힙니다
call "windows\find_python.bat"
if not defined PY (
    echo Python이 아직 없어 설치 점검을 먼저 실행합니다...
    echo.
    call "windows\1_설치.bat" auto
    if errorlevel 1 exit /b 1
    call "windows\find_python.bat"
)
if not defined PY (
    echo [!] Python을 찾지 못했습니다 — windows\1_설치.bat 을 먼저 실행하세요.
    pause
    exit /b 1
)

rem FFmpeg가 전혀 없으면 설치 점검을 자동으로 먼저 실행 (새 폴더에 zip만 푼 경우)
if not exist "windows\ffmpeg\bin\ffmpeg.exe" (
    where ffmpeg >nul 2>nul
    if errorlevel 1 (
        echo FFmpeg가 아직 없어 설치 점검을 먼저 실행합니다...
        echo.
        call "windows\1_설치.bat" auto
        if errorlevel 1 exit /b 1
    )
)

if exist "windows\ffmpeg\bin\ffmpeg.exe" (
    set "CUTDAEJANG_FFMPEG=%CD%\windows\ffmpeg\bin\ffmpeg.exe"
    set "CUTDAEJANG_FFPROBE=%CD%\windows\ffmpeg\bin\ffprobe.exe"
)
echo.
echo 잠시 후 브라우저에 컷대장 화면이 열립니다.
echo 이 검은 창은 서버라 최소화된 채 두면 됩니다 — 닫으면 컷대장도 꺼져요.
echo.
"%PY%" -m cutdaejang ui --workdir windows\jobs
if errorlevel 1 (
    echo.
    echo [!] 실행 실패 — 위 오류 문구를 캡처해서 보내주세요.
    pause
)
