@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if not exist "app.py" (
  echo [ERROR] app.py was not found next to this file.
  echo If you opened this from inside a ZIP file, extract the ZIP first ^(right-click - Extract All^),
  echo then double-click run_windows.bat in the extracted folder.
  goto :fail
)

set "PY="
where py >nul 2>nul && py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=python"
if not defined PY (
  echo [ERROR] Python 3.10 or newer was not found.
  echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH" during setup.
  echo The Microsoft Store shortcut "python" does not count as an installed Python.
  goto :fail
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating a private Python environment in .venv ...
  %PY% -m venv .venv
  if errorlevel 1 goto :fail
)

rem Install packages on the first run, and again whenever requirements.txt changes.
fc /b "requirements.txt" ".venv\requirements.installed" >nul 2>nul
if errorlevel 1 (
  echo Installing packages. This is needed only once and can take a few minutes ...
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
  if errorlevel 1 (
    echo [ERROR] Package installation failed. Check the internet connection or the institution's proxy settings.
    goto :fail
  )
  copy /y "requirements.txt" ".venv\requirements.installed" >nul
)

".venv\Scripts\python.exe" launcher.py
if errorlevel 1 goto :fail
exit /b 0

:fail
echo.
echo The app could not start. Please send a screenshot of this window.
pause
exit /b 1
