# LLM Utilities for OceENS

Utilities for working with LLM providers (Claude, etc.) in the OceENS project.

## Folders

### `token-counting/`
Token estimation and cost tracking tools for Claude API usage.

**Contents:**
- `estimate_tokens_local.py` — Quick token estimation (no API key needed)
- `estimate_tokens.py` — Exact token counts (requires API key)
- `estimate-tokens.sh` — Bash wrapper for Unix/Linux/Mac
- `estimate-tokens.bat` — Batch wrapper for Windows
- `TOKEN_COUNTING_GUIDE.md` — Full documentation and tips
- `README_TOKENS.md` — Quick reference guide

**Quick start:**
```bash
cd token-counting
python estimate_tokens_local.py
```

See `token-counting/README_TOKENS.md` for details.

---

## Future LLM Utilities

This folder is organized to hold other LLM-related tools:
- Prompt management
- LLM evaluation tools
- Provider integration helpers
- Model switching utilities
