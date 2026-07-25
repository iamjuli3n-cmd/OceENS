# Token Estimation Tools

Quick token & cost estimation scripts for your OceENS project.

## Quick Usage

### Fast Estimate (No API Key)
```bash
python estimate_tokens_local.py
```

### Accurate Counts (With API Key)
```bash
export ANTHROPIC_API_KEY='sk-...'
python estimate_tokens.py
```

## Your Project Stats

- **Files**: 41 Python files
- **Total Tokens**: ~63,000
- **Full Review Cost**: ~$0.19 (Sonnet 5)
- **Average Session**: $0.22 (5-turn, 5K tokens/turn)

## Model Pricing (per turn, ~5K tokens)

| Model | Cost |
|-------|------|
| Haiku 4.5 | $0.005 |
| Sonnet 5 (recommended) | $0.015 |
| Opus 4.8 | $0.025 |

## Files

- `estimate_tokens_local.py` - Fast local estimation
- `estimate_tokens.py` - Exact counts (needs API key)
- `estimate-tokens.sh` - Bash wrapper
- `estimate-tokens.bat` - Windows batch wrapper
- `TOKEN_COUNTING_GUIDE.md` - Full guide

## Examples

```bash
# Estimate with Sonnet 5 (default)
python estimate_tokens_local.py

# Estimate specific pattern
python estimate_tokens_local.py claude-haiku-4-5 "*.ts"

# Get help
python estimate_tokens_local.py --help
```

## Cost Tips

1. **Reuse context** - 2x cheaper after first turn
2. **Send files gradually** - not all at once
3. **Use Sonnet 5** - best speed/cost ratio
4. **Monitor in Claude Desktop** - shows live token usage

See `TOKEN_COUNTING_GUIDE.md` for full details.
