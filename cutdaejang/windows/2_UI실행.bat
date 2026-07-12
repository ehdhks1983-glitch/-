@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."

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
echo 이 검은 창은 서버입니다 — 닫으면 UI도 꺼지니 그대로 두세요.
echo.
python -m cutdaejang ui --workdir windows\jobs
if errorlevel 1 (
    echo.
    echo [!] 실행 실패 — 위 오류 문구를 캡처해서 보내주세요.
    pause
)
