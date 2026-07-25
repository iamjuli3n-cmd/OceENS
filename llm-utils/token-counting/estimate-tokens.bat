@echo off
REM 📊 Token Cost Estimator for Windows
REM Usage: estimate-tokens.bat [model] [pattern]

setlocal enabledelayedexpansion

set MODEL=%1
set PATTERN=%2

if "%MODEL%"=="" set MODEL=claude-sonnet-5
if "%PATTERN%"=="" set PATTERN=*.py

echo 🔄 Estimating tokens for OceENS project...
echo.

python estimate_tokens.py "%MODEL%" "%PATTERN%"

pause
