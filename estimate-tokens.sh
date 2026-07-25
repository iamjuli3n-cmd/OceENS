#!/bin/bash
# Convenience wrapper to run token estimation from project root

PROJECT_ROOT="$(dirname "$0")"
cd "$PROJECT_ROOT" || exit 1
python "llm-utils/token-counting/estimate_tokens_local.py" "$@"
