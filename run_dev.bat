@echo off
echo ========================================
echo  Scientific RAG - Dev Mode
echo ========================================
echo.

set "SETUP_REQUIRED=0"

if not exist "%~dp0backend\venv" (
    echo [INFO] Python virtual environment 'venv' not found.
    set "SETUP_REQUIRED=1"
)

if not exist "%~dp0frontend\react-app\node_modules" (
    echo [INFO] Frontend 'node_modules' not found.
    set "SETUP_REQUIRED=1"
)

if not exist "%~dp0backend\.env" (
    echo [INFO] Backend '.env' file not found.
    set "SETUP_REQUIRED=1"
)

if "%SETUP_REQUIRED%"=="1" (
    echo [INFO] First-time setup is required. Running setup.bat...
    echo.
    call "%~dp0setup.bat"
    if errorlevel 1 (
        echo ERROR: Setup failed. Cannot proceed.
        pause
        exit /b 1
    )
)

echo.
echo Checking Docker status...
docker info >nul 2>&1
if errorlevel 1 (
    echo.
    echo ========================================================
    echo  LOI: Docker Desktop chua duoc khoi dong!
    echo  Vui long bat Docker Desktop len truoc khi chay du an.
    echo ========================================================
    echo  ERROR: Docker Desktop is not running.
    echo  Please start Docker Desktop before running this script.
    echo ========================================================
    echo.
    pause
    exit /b 1
)

echo Khoi dong cac database containers (Qdrant ^& Neo4j)...
pushd "%~dp0backend\qdrant-server"
call docker compose up -d
if errorlevel 1 (
    echo ERROR: Khong the khoi dong Qdrant container.
    popd
    pause
    exit /b 1
)
popd

pushd "%~dp0backend\neo4j-server"
call docker compose up -d
if errorlevel 1 (
    echo ERROR: Khong the khoi dong Neo4j container.
    popd
    pause
    exit /b 1
)
popd
echo Database containers da san sang!

echo.
echo Starting FastAPI backend (port 8000)...
start "FastAPI Backend" cmd /k "cd /d %~dp0backend && venv\Scripts\activate && uvicorn main:app --reload --port 8000"
timeout /t 3 /nobreak > nul
echo Starting React dev server (port 5173)...
start "React Frontend" cmd /k "cd /d %~dp0frontend\react-app && npm run dev"
echo.
echo ----------------------------------------
echo  FastAPI: http://localhost:8000
echo  React:   http://localhost:5173
echo  Docs:    http://localhost:8000/docs
echo ----------------------------------------
