@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."

echo ==========================================
echo   컷대장 설치 점검  (최초 1회만 실행)
echo ==========================================
echo.

rem ---------- 1) Python ----------
rem "설치포함 풀버전" zip에는 windows\python\ 에 파이썬이 통째로 들어 있어
rem 설치할 것이 없습니다. 없을 때만 예전처럼 자동 설치를 시도합니다.
call "windows\find_python.bat"
if defined PY goto :py_ok
echo [!] Python이 설치되어 있지 않습니다. 자동 설치를 시도합니다...
winget install -e --id Python.Python.3.11 --accept-source-agreements --accept-package-agreements
call "windows\find_python.bat"
if defined PY goto :py_ok
echo.
echo [!] Python을 준비하지 못했습니다. 두 가지 방법이 있어요:
echo     방법 1^) "컷대장 설치포함 풀버전" zip을 받아서 쓰면 이 단계가 아예 없습니다. (추천)
echo     방법 2^) https://www.python.org/downloads/ 에서 직접 설치하되,
echo             설치 화면에서 "Add python.exe to PATH"를 꼭 체크하세요.
pause
exit /b 1
:py_ok
echo [OK] Python 준비됨:
"%PY%" --version

rem ---------- 2) FFmpeg - libass 포함 빌드 ----------
rem 설치포함 풀버전에는 windows\ffmpeg\bin\ 에 이미 들어 있어 바로 통과합니다.
if exist "windows\ffmpeg\bin\ffmpeg.exe" (
    echo [OK] FFmpeg 이미 준비됨
) else (
    echo [..] FFmpeg 내려받는 중... 약 100MB, 몇 분 걸립니다.
    echo      아래에 진행바(%%)가 보이면 정상이에요 — 창을 닫지 말고 기다리세요.
    echo.
    set "FFURL=https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip"
    rem curl(윈도우10 내장)은 진행바가 보여서 '빈 창'처럼 안 보임 — 없으면 PowerShell로 폴백
    curl -L --fail --progress-bar -o "%TEMP%\cutdaejang_ffmpeg.zip" "%FFURL%"
    if errorlevel 1 (
        echo [i] curl 실패/없음 — PowerShell로 다시 시도합니다 (이때는 진행바 없이 몇 분 조용히 받아요)...
        powershell -NoProfile -Command "& {$ProgressPreference='SilentlyContinue'; Invoke-WebRequest '%FFURL%' -OutFile (Join-Path $env:TEMP 'cutdaejang_ffmpeg.zip')}"
    )
    if not exist "%TEMP%\cutdaejang_ffmpeg.zip" (
        echo [!] 다운로드 실패 — 인터넷 연결을 확인하세요.
        echo     "설치포함 풀버전" zip에는 FFmpeg가 들어 있어 이 단계가 없습니다. (추천)
        echo     수동 방법: https://www.gyan.dev/ffmpeg/builds/ 에서 release-full zip을 받아
        echo     압축을 풀고 내용물을 cutdaejang\windows\ffmpeg\ 폴더에 넣으세요.
        pause
        exit /b 1
    )
    echo [..] 압축 푸는 중...
    powershell -NoProfile -Command "& {Expand-Archive -Force (Join-Path $env:TEMP 'cutdaejang_ffmpeg.zip') (Join-Path $env:TEMP 'cutdaejang_ffmpeg')}"
    for /d %%D in ("%TEMP%\cutdaejang_ffmpeg\ffmpeg-*") do xcopy "%%D" "windows\ffmpeg\" /E /I /Y /Q >nul
    del "%TEMP%\cutdaejang_ffmpeg.zip" >nul 2>nul
)
if not exist "windows\ffmpeg\bin\ffmpeg.exe" (
    echo [!] FFmpeg 준비 실패 — 위 안내대로 수동으로 넣은 뒤 다시 실행하세요.
    pause
    exit /b 1
)


rem ---------- 4) 최종 진단 ----------
set "CUTDAEJANG_FFMPEG=%CD%\windows\ffmpeg\bin\ffmpeg.exe"
set "CUTDAEJANG_FFPROBE=%CD%\windows\ffmpeg\bin\ffprobe.exe"
echo.
"%PY%" -m cutdaejang doctor
echo.
echo 위에 "진단 결과: 정상" 이 보이면 성공입니다. 이어서 2_UI실행.bat 을 실행하세요.
if /i not "%~1"=="auto" pause
