@echo off
:: TAP.bat — Trading Automation Process launcher (Double-click to run)
::
:: Double-click this file to start the backend and frontend in separate windows
:: and open the dashboard in your default web browser.

:: Set the current directory to the directory where this batch file is located
cd /d "%~dp0"

echo Starting Backend...
:: Starts backend.main in a separate window, activating the Python virtual environment first
start "TAP - Backend" cmd /k "call venv\Scripts\activate.bat && python -m backend.main"

:: Wait 5 seconds for backend to initialize
timeout /t 5 /nobreak >nul

echo Starting Frontend...
:: Starts npm run dev in a separate window under the frontend directory
start "TAP - Frontend" cmd /k "cd frontend && npm run dev"

:: Wait 3 seconds for Vite to start up
timeout /t 3 /nobreak >nul

echo Opening dashboard in default browser...
:: Opens the frontend URL in the system's default browser
start http://localhost:5173

echo Startup sequence completed!
echo You can close the separate terminal windows when you want to stop the app.
