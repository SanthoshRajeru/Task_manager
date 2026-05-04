@echo off
setlocal

set "PROJECT_DIR=C:\Users\C9J2GX\.cursor\task_manager_web"
set "ENV_ACTIVATE=C:\Users\C9J2GX\.cursor\fastapi-env\Scripts\activate.bat"

if not exist "%ENV_ACTIVATE%" (
    echo FastAPI environment not found at:
    echo %ENV_ACTIVATE%
    pause
    exit /b 1
)

if not exist "%PROJECT_DIR%\main.py" (
    echo main.py not found at:
    echo %PROJECT_DIR%\main.py
    pause
    exit /b 1
)

set "PORT_PID="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8010" ^| findstr "LISTENING"') do (
    set "PORT_PID=%%P"
)

if defined PORT_PID (
    echo Server is already running on http://127.0.0.1:8010 - PID %PORT_PID%.
    start "" "http://127.0.0.1:8010"
    exit /b 0
)

call "%ENV_ACTIVATE%"
cd /d "%PROJECT_DIR%"
python main.py
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Server exited with error code %EXIT_CODE%.
    echo If you see "address already in use", another server is already running on port 8010.
    pause
)

endlocal
