@echo off
echo ========================================
echo  Scientific RAG - Dev Mode
echo ========================================
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
