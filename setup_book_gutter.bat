@echo off
setlocal EnableExtensions

set "PROJECT_DIR=%~dp0"
set "VENV_PY=%PROJECT_DIR%.venv\Scripts\python.exe"
set "PYTHON_EXE="
set "PYTHON_ARGS="

pushd "%PROJECT_DIR%" || (
  echo Failed to change directory to "%PROJECT_DIR%".
  pause
  exit /b 1
)

where py >nul 2>nul
if not errorlevel 1 (
  set "PYTHON_EXE=py"
  set "PYTHON_ARGS=-3"
) else (
  where python >nul 2>nul
  if not errorlevel 1 set "PYTHON_EXE=python"
)

if not defined PYTHON_EXE (
  echo Could not find Python 3.
  echo Install Python, then run setup_book_gutter.bat again.
  pause
  popd
  exit /b 1
)

if not exist "%VENV_PY%" (
  echo Creating .venv...
  %PYTHON_EXE% %PYTHON_ARGS% -m venv .venv
  if errorlevel 1 (
    echo Failed to create .venv.
    pause
    popd
    exit /b 1
  )
)

echo Upgrading pip...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 (
  echo Failed to upgrade pip.
  pause
  popd
  exit /b 1
)

echo Installing project dependencies...
"%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Failed to install project dependencies.
  pause
  popd
  exit /b 1
)

echo Verifying PyMuPDF, PySide6, and NumPy...
"%VENV_PY%" -c "import fitz; import PySide6; import numpy; print('Dependency check passed.')"
if errorlevel 1 (
  echo Dependency verification failed.
  pause
  popd
  exit /b 1
)

echo.
echo Setup complete.
echo Launch the app with:
echo Book Gutter PDF.bat
popd
exit /b 0
