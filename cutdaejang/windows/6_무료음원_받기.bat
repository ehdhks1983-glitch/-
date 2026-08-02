@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."

call "%~dp0find_python.bat"
if not defined PY (
    echo [!] 파이썬을 찾지 못했어요 - windows\1_설치.bat 을 먼저 실행해 주세요.
    pause
    exit /b 1
)
echo ==========================================
echo   무료 BGM 자동 받기 (50곡+ - 분위기별 유튜브 국민 BGM)
echo ==========================================
echo.
echo 전 세계 유튜버가 가장 많이 쓰는 Kevin MacLeod 무료 음원을
echo resources\bgm 폴더에 자동으로 받아옵니다. (약 150MB, 3~8분)
echo 전부 CC BY(저작자표시) - 영상 설명란에 크레딧 한 줄만 붙이면
echo 수익화 영상에도 무료로 쓸 수 있어요. (크레딧 파일 자동 생성)
echo.
"%PY%" -m cutdaejang.tools.fetch_bgm
if errorlevel 1 (
    echo.
    echo [!] 실패 - 인터넷 연결을 확인하고 다시 실행하세요.
    pause
    exit /b 1
)
echo.
echo [OK] 컷대장 화면을 새로고침(F5)하면 BGM 목록에 나타납니다!
pause
