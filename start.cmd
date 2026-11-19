@echo off
setlocal
if exist "%~dp0.venv\Scripts\python.exe" goto use_venv
where py >nul 2>nul
if not errorlevel 1 goto use_py
where python >nul 2>nul
if errorlevel 1 (
    echo Python 3.10 or newer is required. Install Python and run start.cmd again. 1>&2
    exit /b 1
)
python "%~dp0src\vera\utils\windows_bash.py" %*
exit /b %errorlevel%

:use_venv
"%~dp0.venv\Scripts\python.exe" "%~dp0src\vera\utils\windows_bash.py" %*
exit /b %errorlevel%

:use_py
py -3 "%~dp0src\vera\utils\windows_bash.py" %*
exit /b %errorlevel%
