@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
if exist "windows\ffmpeg\bin\ffmpeg.exe" (
    set "CUTDAEJANG_FFMPEG=%CD%\windows\ffmpeg\bin\ffmpeg.exe"
    set "CUTDAEJANG_FFPROBE=%CD%\windows\ffmpeg\bin\ffprobe.exe"
)
echo 잠시 후 브라우저에 컷대장 화면이 열립니다.
echo 이 검은 창은 서버입니다 — 닫으면 UI도 꺼지니 그대로 두세요.
echo.
python -m cutdaejang ui --workdir windows\jobs
if errorlevel 1 (
    echo.
    echo [!] 실행 실패 — 1_설치.bat 을 먼저 실행했는지 확인하세요.
    pause
)
