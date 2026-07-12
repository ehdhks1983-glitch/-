@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
if exist "windows\ffmpeg\bin\ffmpeg.exe" (
    set "CUTDAEJANG_FFMPEG=%CD%\windows\ffmpeg\bin\ffmpeg.exe"
    set "CUTDAEJANG_FFPROBE=%CD%\windows\ffmpeg\bin\ffprobe.exe"
)
echo 데모 쇼츠 생성 중... API 키 불필요 — 목소리는 테스트용 톤입니다.
echo.
python -m cutdaejang demo --workdir windows\jobs
if errorlevel 1 (
    echo.
    echo [!] 실패했습니다. 1_설치.bat 을 먼저 실행했는지 확인하세요.
    pause
    exit /b 1
)
echo.
echo 완료! 열리는 폴더에서 날짜 폴더 안의 output.mp4 를 재생해 보세요.
start "" explorer "%CD%\windows\jobs"
pause
