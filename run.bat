@echo off
REM Load .env file and run the application
setlocal enabledelayedexpansion

REM Read .env and set environment variables
for /f "tokens=* delims=" %%i in (.env) do (
    set "line=%%i"
    for /f "tokens=1,2 delims==" %%a in ("!line!") do (
        if defined %%b (
            set "%%a=!%%b!"
        ) else (
            set "%%a="
        )
    )
)

REM Run the application
.venv\Scripts\uvicorn app:app --reload %*