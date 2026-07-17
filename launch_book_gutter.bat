@echo off
setlocal EnableExtensions
set "PROJECT_DIR=%~dp0"
set "APP_PATH=%PROJECT_DIR%app.py"
set "VENV_PY=%PROJECT_DIR%.venv\Scripts\python.exe"

pushd "%PROJECT_DIR%" || (
  echo Failed to change directory to "%PROJECT_DIR%".
  pause
  exit /b 1
)

if not exist "%VENV_PY%" goto :setup_missing

"%VENV_PY%" -c "import fitz; import PySide6; import numpy"
if errorlevel 1 goto :deps_missing

"%VENV_PY%" "%APP_PATH%"
set "EXIT_CODE=%ERRORLEVEL%"
popd

if not "%EXIT_CODE%"=="0" (
  echo Book Gutter PDF exited with code %EXIT_CODE%.
  pause
  exit /b %EXIT_CODE%
)

exit /b 0

:setup_missing
echo Book Gutter PDF is not set up yet.
echo Please run setup_book_gutter.bat first.
pause
popd
exit /b 1

:deps_missing
echo Book Gutter PDF is set up, but dependencies are missing.
echo Please run setup_book_gutter.bat first.
pause
popd
exit /b 1
