@echo off
echo ================================================
echo  Scientific RAG - Setup (First Time)
echo ================================================
echo.

echo [1/5] Installing npm packages for React frontend...
cd /d %~dp0frontend\react-app
call npm install --legacy-peer-deps
if errorlevel 1 (
    echo ERROR: npm install failed. Make sure Node.js is installed.
    pause
    exit /b 1
)
echo Done!
echo.

echo [2/5] Setting up Python Virtual Environment (venv)...
cd /d %~dp0backend
if not exist venv (
    echo Virtual environment 'venv' not found. Creating it...
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment. Make sure Python 3.10+ is installed and in your PATH.
        pause
        exit /b 1
    )
)
call venv\Scripts\activate
echo Upgrading pip...
python -m pip install --upgrade pip
echo.

echo [3/5] Installing Python packages from requirements.txt...
call pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install Python dependencies.
    pause
    exit /b 1
)
echo Done!
echo.

echo [4/5] Copying environment variables template...
if not exist .env (
    echo Copying .env.example to .env...
    copy ..\.env.example .env
) else (
    echo .env file already exists. Skipping copy.
)
echo.

echo [5/5] Verifying imports...
python -c "import fastapi, uvicorn, docling, qdrant_client, neo4j, sentence_transformers, torch, umap; print('[OK] Core packages verified successfully!')"
echo.

echo ================================================
echo  Setup complete! Run run_dev.bat to start.
echo ================================================
pause
