@echo off
REM Convenience wrapper to run token estimation from project root

cd /d "%~dp0"
python "llm-utils\token-counting\estimate_tokens_local.py" %*
