@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
call "windows\find_python.bat"
if not defined PY (
    echo [!] Python을 찾지 못했습니다 — windows\1_설치.bat 을 먼저 실행하세요.
    pause
    exit /b 1
)
if exist "windows\ffmpeg\bin\ffmpeg.exe" (
    set "CUTDAEJANG_FFMPEG=%CD%\windows\ffmpeg\bin\ffmpeg.exe"
    set "CUTDAEJANG_FFPROBE=%CD%\windows\ffmpeg\bin\ffprobe.exe"
)
echo 콘솔 데모: API 키 없이 쇼츠 1편을 생성합니다. 목소리는 테스트용 톤.
echo.
"%PY%" -m cutdaejang demo --workdir windows\jobs
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
