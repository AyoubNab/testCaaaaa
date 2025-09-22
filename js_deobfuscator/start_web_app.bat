@echo off
echo ======================================================
echo  JavaScript Deobfuscator Web App Installer & Launcher
echo ======================================================
echo.

echo [+] Checking for Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] ERROR: Python is not installed or not found in your PATH.
    echo     Please install Python 3 and try again.
    pause
    exit /b
)

echo [+] Checking for pip...
pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] ERROR: pip is not installed or not found in your PATH.
    echo     Please ensure you have a full Python installation.
    pause
    exit /b
)

echo [+] Installing required Python packages from requirements.txt...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [!] ERROR: Failed to install dependencies.
    pause
    exit /b
)

echo.
echo [+] Dependencies are up to date.
echo [+] Launching the web server...
echo     You can access the web app at http://127.0.0.1:8080
echo     Press CTRL+C in this window to stop the server.
echo.

python src/web_app.py

echo.
echo Server stopped.
pause
