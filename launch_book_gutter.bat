@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
set "APP_PATH=%SCRIPT_DIR%app.py"
set "PYTHON_EXE="
set "PYTHON_CMD="

pushd "%SCRIPT_DIR%" || (
  echo Failed to change directory to "%SCRIPT_DIR%".
  pause
  exit /b 1
)

if exist "%SCRIPT_DIR%.venv\Scripts\python.exe" set "PYTHON_EXE=%SCRIPT_DIR%.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "C:\Users\drarv\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" set "PYTHON_EXE=C:\Users\drarv\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if not defined PYTHON_EXE (
  where py >nul 2>nul
  if not errorlevel 1 set "PYTHON_CMD=py -3"
)

if not defined PYTHON_EXE if not defined PYTHON_CMD (
  where python >nul 2>nul
  if not errorlevel 1 set "PYTHON_CMD=python"
)

if defined PYTHON_EXE (
  "%PYTHON_EXE%" "%APP_PATH%"
) else if defined PYTHON_CMD (
  %PYTHON_CMD% "%APP_PATH%"
) else (
  echo Could not find a Python interpreter.
  pause
  popd
  exit /b 1
)

set "EXIT_CODE=%ERRORLEVEL%"
popd

if not "%EXIT_CODE%"=="0" (
  echo Book Gutter PDF exited with code %EXIT_CODE%.
  pause
  exit /b %EXIT_CODE%
)

exit /b 0
