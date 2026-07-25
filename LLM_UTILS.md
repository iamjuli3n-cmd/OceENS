# LLM Utilities & Token Tracking

Quick access to LLM tools for the OceENS project.

## Token Counting (Quick Start)

**Estimate your Claude API costs:**

```bash
# From project root
./estimate-tokens.sh          # Unix/Mac/Linux
estimate-tokens.bat           # Windows

# Or with Python directly
python llm-utils/token-counting/estimate_tokens_local.py
```

**Your Project Cost Overview (Sonnet 5):**
- Full codebase: ~68K tokens → **$0.20**
- Typical session (5 turns): **$0.23**
- Simple bugfix: ~$0.006
- Feature development: ~$0.024

## Features

### `llm-utils/token-counting/`
- **`estimate_tokens_local.py`** — Fast estimation (works offline)
- **`estimate_tokens.py`** — Exact API counts (requires `ANTHROPIC_API_KEY`)
- **Full guides** — TOKEN_COUNTING_GUIDE.md, README_TOKENS.md
- **Wrappers** — estimate-tokens.sh/.bat for quick access from root

## Tips to Reduce Costs

1. **Reuse context** — 2x cheaper after first turn (Claude caches input)
2. **Send files progressively** — Not all at once
3. **Use Sonnet 5** — Best speed/cost ratio (your default)
4. **Monitor in Claude Desktop** — Token usage shown at bottom of chat

## Setting Up

```bash
# Set your API key (optional, for exact counts)
export ANTHROPIC_API_KEY='sk-...'

# Then run
python llm-utils/token-counting/estimate_tokens.py
```

## Full Documentation

See `llm-utils/token-counting/TOKEN_COUNTING_GUIDE.md` for:
- Claude Desktop integration
- Cost optimization strategies
- Detailed pricing breakdown
- Multi-model recommendations

---

**All token tools are in `feat/llm-providers` branch** — a dedicated space for LLM provider integrations.

Current branch tools are ready to use!
