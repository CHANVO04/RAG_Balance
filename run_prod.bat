@echo off
echo ========================================
echo  Scientific RAG - Production Build
echo ========================================
echo.
echo Building React app for production...
cd /d %~dp0frontend\react-app
call npm run build
cd /d %~dp0
echo.
echo Starting FastAPI (production mode)...
cd /d %~dp0backend
call venv\Scripts\activate
uvicorn main:app --port 8000 --workers 1
echo.
echo Open: http://localhost:8000
