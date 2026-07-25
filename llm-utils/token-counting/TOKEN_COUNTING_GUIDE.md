# Token Counting & Cost Estimation Guide for OceENS

This guide helps you track and optimize token usage for your Claude API interactions on the OceENS project.

## Quick Start

### Option 1: Quick Estimate (No API Key Required)
```bash
python estimate_tokens_local.py
# or
./estimate-tokens.bat  (Windows)
./estimate-tokens.sh   (Linux/Mac)
```

This gives you a **fast estimate** based on file size (~4 chars = 1 token).

### Option 2: Accurate Counts (Requires API Key)
```bash
export ANTHROPIC_API_KEY='sk-...'  # Set your API key
python estimate_tokens.py
```

This uses Claude's **token counter API** for exact token counts.

---

## Project Token Summary

Based on the current codebase (41 Python files):

| Metric | Value |
|--------|-------|
| **Total Files** | 41 |
| **Total Estimated Tokens** | ~63,000 |
| **Largest Files** | pages.py (8.8K), seed.py (8.3K), surveys.py (6.9K) |

### Cost per Session Type (Sonnet 5)

| Session Type | Tokens | Cost |
|--------------|--------|------|
| Simple bugfix (1 file) | ~2,000 | $0.006 |
| Feature dev (3-5 files) | ~8,000 | $0.024 |
| Refactoring (10 files) | ~20,000 | $0.060 |
| Full code review | ~63,000 | $0.189 |

### Multi-Turn Session Estimate

For a typical 5-turn session with Sonnet 5:
- **Input**: 25,000 tokens × $3.00/M = $0.075
- **Output**: 10,000 tokens × $15.00/M = $0.150
- **Total**: **$0.225**

---

## Model Recommendations

Choose based on your task:

| Model | Cost/Turn | Best For |
|-------|-----------|----------|
| **Haiku 4.5** | ~$0.005 | Quick bugfixes, iterations |
| **Sonnet 5** | ~$0.015 | Most development work (recommended) |
| **Opus 4.8** | ~$0.025 | Complex architecture decisions |

---

## Claude Desktop Integration

### 1. View Token Usage in Claude Desktop
The Claude desktop app shows token consumption at the bottom of each chat:
- **Input tokens** = code you send in + context
- **Output tokens** = Claude's response
- **Total cost** = displayed in the UI

### 2. Monitor Costs Over Time

Create a simple log to track your spending:

```bash
# Linux/Mac: append to a log file
echo "$(date): Session with OceENS - estimated $0.23" >> token_usage.log

# Windows PowerShell:
Add-Content token_usage.log "$(Get-Date): Session with OceENS - estimated $0.23"
```

### 3. Optimize Your Workflow

#### To reduce token costs:
- ✓ **Reuse context** between turns (Claude caches 2x cheaper after first request)
- ✓ **Send files gradually** instead of dumping the whole project
- ✓ **Use Sonnet 5** for most work (best speed/cost ratio)
- ✓ **Save summaries** of long conversations to reference later
- ✓ **Use prompt caching** for repeated analysis on the same files

#### When to use each model:
- Use **Haiku** for: linting, quick Q&A, simple refactors
- Use **Sonnet 5** for: feature dev, complex fixes, most work
- Use **Opus** for: architecture design, deep analysis

---

## Usage Examples

### Estimate tokens for your project
```bash
python estimate_tokens_local.py claude-sonnet-5
```

### Estimate for TypeScript files instead
```bash
python estimate_tokens_local.py claude-sonnet-5 "*.ts"
```

### Get exact counts (requires API key)
```bash
export ANTHROPIC_API_KEY='sk-...'
python estimate_tokens.py claude-sonnet-5
```

### View help
```bash
python estimate_tokens_local.py --help
```

---

## Cost Breakdown Explained

**Input tokens** = what you send (code, context, question)
**Output tokens** = what Claude generates (response, code)

Pricing (per 1M tokens):
- Haiku 4.5: $1.00 input / $5.00 output
- Sonnet 5: $3.00 input / $15.00 output
- Opus 4.8: $5.00 input / $25.00 output

### Example: Adding a feature
```
1. Send 3 related files (~10K tokens input) = $0.030
2. Claude responds with suggestions (~2K tokens output) = $0.030
3. Send revised code (~8K tokens input) = $0.024
4. Claude refines it (~1.5K tokens output) = $0.0225

Total for feature dev: ~$0.107
```

---

## Setting ANTHROPIC_API_KEY

### Windows (PowerShell)
```powershell
$env:ANTHROPIC_API_KEY = 'sk-...'
python estimate_tokens.py
```

### Windows (Command Prompt)
```cmd
set ANTHROPIC_API_KEY=sk-...
python estimate_tokens.py
```

### Linux/Mac (Bash)
```bash
export ANTHROPIC_API_KEY='sk-...'
python estimate_tokens.py
```

### Permanent (add to shell profile)
Add to `~/.bashrc` or `~/.zshrc` or PowerShell profile:
```bash
export ANTHROPIC_API_KEY='sk-...'
```

---

## Files Included

| File | Purpose |
|------|---------|
| `estimate_tokens_local.py` | **Fast estimation** (no API key needed) |
| `estimate_tokens.py` | **Accurate counts** (requires API key) |
| `estimate-tokens.sh` | Bash wrapper (Linux/Mac) |
| `estimate-tokens.bat` | Batch wrapper (Windows) |
| `TOKEN_COUNTING_GUIDE.md` | This file |

---

## Tips for Cost Optimization

### 1. Reuse Context (2x cheaper after first turn)
```
Turn 1: Send files + ask question = FULL COST
Turn 2-5: Same context in cache = 50% discount on input tokens
```

### 2. Progressive File Addition
Instead of: "analyze all 40 files"
Do: "analyze core/ first, then models/, then routers/"

### 3. Save Summaries
After a complex analysis, ask Claude to summarize findings.
Then future sessions reference the summary instead of re-analyzing.

### 4. Batch Similar Tasks
Combine multiple small requests into one larger request.
Reduces context switching overhead.

### 5. Use Token Counter Before Big Sessions
```bash
python estimate_tokens_local.py  # Estimate cost
# If ~$0.30+ expected, you might want Haiku instead
```

---

## FAQ

**Q: How accurate are the estimates?**
A: Local estimates (~4 chars/token) are 90-95% accurate. API-based counts are exact.

**Q: Why does Claude count tokens differently than my estimate?**
A: Different tokenizers exist. Anthropic's counter is authoritative.

**Q: Should I worry about output token costs?**
A: Output is ~5-10x input per token, but usually smaller volume. Input is more critical.

**Q: Can I get a discount?**
A: Yes! Volume discounts available at higher usage tiers. Contact Anthropic sales.

**Q: How do I track spending across a team?**
A: Log each session's cost and sum weekly. Use the scripts to estimate before large sessions.

---

## Next Steps

1. **Run the estimator** to see current project size
2. **Set ANTHROPIC_API_KEY** to get exact counts
3. **Monitor Claude Desktop** usage at bottom of each chat
4. **Optimize** using tips above
5. **Save this guide** for reference during development

Questions? Check [Anthropic API Documentation](https://docs.anthropic.com)
