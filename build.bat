@echo off
chcp 65001 >nul 2>&1

echo ===================================================
echo  GIF Maker Pro - Build (No PyArmor)
echo ===================================================
echo.

echo [1/6] Checking tools...
where python >nul 2>&1 || (echo ERROR: Python not found & pause & exit /b 1)
where pyinstaller >nul 2>&1 || (echo Installing PyInstaller... & pip install pyinstaller)
if not exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (echo ERROR: Inno Setup not found & pause & exit /b 1)

echo [2/6] Dependencies...
pip install -r requirements.txt >nul 2>&1

echo [3/6] Securing files...
if exist "license_generator.py" (
    if not exist "_private" mkdir _private
    move /Y license_generator.py _private\license_generator.py >nul
    echo   license_generator secured
)

echo [4/6] PyInstaller...
if exist "dist" rmdir /s /q dist >nul 2>&1
if exist "build" rmdir /s /q build >nul 2>&1

pyinstaller --noconfirm --onefile --windowed --name "GIF Maker Pro" --icon "app_icon.ico" --add-data "app_icon.ico;." --hidden-import "customtkinter" --hidden-import "PIL" --hidden-import "PIL._tkinter_finder" --hidden-import "mss" --hidden-import "psutil" --collect-all "customtkinter" --exclude-module "license_generator" --exclude-module "matplotlib" --exclude-module "numpy" --exclude-module "scipy" --exclude-module "pandas" main.py

if not exist "dist\GIF Maker Pro.exe" (
    echo ERROR: EXE build failed
    goto :restore
)
echo   EXE OK

echo [5/6] Inno Setup...
if exist "output" rmdir /s /q output >nul 2>&1
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" setup.iss
if not exist "output\GIFMakerPro_Setup.exe" (
    echo ERROR: Setup build failed
    goto :restore
)
echo   Setup OK

echo [6/6] Done!

:restore
if exist "_private\license_generator.py" (
    move /Y _private\license_generator.py license_generator.py >nul
    rmdir _private 2>nul
)

if exist "output\GIFMakerPro_Setup.exe" (
    echo.
    echo ===================================================
    echo  DONE: output\GIFMakerPro_Setup.exe
    echo ===================================================
    explorer output
)
pause
