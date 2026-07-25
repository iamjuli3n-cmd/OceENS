#!/usr/bin/env python3
"""
Token & Cost Estimator for OceENS Project (Local estimation)
Fast token estimation without requiring API key
"""

import sys
from pathlib import Path
from typing import List
from dataclasses import dataclass

# Pricing per 1M tokens
PRICING = {
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    "claude-sonnet-5": {"input": 3.00, "output": 15.00},
    "claude-opus-4-8": {"input": 5.00, "output": 25.00},
}

# Rough token estimation: ~4 chars = 1 token for code
CHARS_PER_TOKEN = 4

@dataclass
class TokenStats:
    file: str
    estimated_tokens: int

    def cost(self, model: str) -> float:
        """Calculate cost for this file."""
        prices = PRICING[model]
        return (self.estimated_tokens / 1_000_000) * prices["input"]

class TokenEstimator:
    def __init__(self, model: str = "claude-sonnet-5"):
        self.model = model
        self.stats: List[TokenStats] = []

    def estimate_file(self, file_path: str) -> int:
        """Estimate tokens in a single file."""
        try:
            content = Path(file_path).read_text(encoding='utf-8')
            # Rough estimation: ~4 chars per token
            tokens = len(content) // CHARS_PER_TOKEN
            return max(tokens, 10)  # Minimum 10 tokens per file
        except Exception as e:
            print(f"[!] Error reading {file_path}: {e}")
            return 0

    def scan_project(self, pattern: str = "*.py", exclude_dirs: List[str] = None) -> None:
        """Scan project and estimate tokens for all matching files."""
        if exclude_dirs is None:
            exclude_dirs = [".venv", "__pycache__", ".git", "node_modules"]

        print(f"[SCANNING] Files matching {pattern} (model: {self.model})...\n")

        for file_path in sorted(Path(".").glob(f"**/{pattern}")):
            # Skip excluded directories
            if any(excluded in str(file_path) for excluded in exclude_dirs):
                continue

            file_str = str(file_path)
            tokens = self.estimate_file(file_str)

            if tokens > 0:
                self.stats.append(TokenStats(file=file_str, estimated_tokens=tokens))
                print(f"  [OK] {file_str}: ~{tokens:,} tokens")

    def print_dashboard(self) -> None:
        """Print formatted token usage dashboard."""
        if not self.stats:
            print("[ERROR] No files found or counted.")
            return

        # Sort by tokens descending
        sorted_stats = sorted(self.stats, key=lambda x: x.estimated_tokens, reverse=True)
        total_tokens = sum(s.estimated_tokens for s in sorted_stats)

        print("\n" + "="*80)
        print("[TOKEN USAGE DASHBOARD - LOCAL ESTIMATION]")
        print("="*80)
        print("NOTE: Estimates based on content size (~4 chars per token)")
        print("For accurate counts, use the script with ANTHROPIC_API_KEY set\n")

        # Top files
        print("[TOP 10 FILES BY ESTIMATED TOKEN COUNT]")
        print("-" * 80)
        print(f"{'File':<50} {'Tokens':>12} {'Cost':>10}")
        print("-" * 80)

        for stat in sorted_stats[:10]:
            cost = stat.cost(self.model)
            print(f"{stat.file:<50} ~{stat.estimated_tokens:>11,} ${cost:>9.4f}")

        if len(sorted_stats) > 10:
            print(f"... and {len(sorted_stats) - 10} more files")

        # Summary
        print("\n" + "="*80)
        print("[PROJECT SUMMARY]")
        print("="*80)
        print(f"Total Files:           {len(sorted_stats)}")
        print(f"Total Estimated Tokens: ~{total_tokens:,}")

        # Cost breakdown by model
        print("\n[ESTIMATED COSTS (for full codebase)]")
        print("-" * 80)
        print(f"{'Model':<25} {'Input Tokens':>20} {'Cost':>15}")
        print("-" * 80)

        for model_name in PRICING.keys():
            prices = PRICING[model_name]
            cost = (total_tokens / 1_000_000) * prices["input"]
            print(f"{model_name:<25} ~{total_tokens:>19,} ${cost:>14.4f}")

        # Session estimates
        print("\n" + "="*80)
        print("[TYPICAL SESSION ESTIMATES]")
        print("="*80)

        session_types = {
            "Simple bugfix (1 file)": 2000,
            "Feature dev (3-5 files)": 8000,
            "Refactoring (10 files)": 20000,
            "Full code review": total_tokens,
        }

        print(f"\nFor {self.model}:")
        print("-" * 80)
        prices = PRICING[self.model]

        for session_type, tokens in session_types.items():
            cost = (tokens / 1_000_000) * prices["input"]
            print(f"  {session_type:<35} ~{tokens:>7,} tokens --> ${cost:>8.4f}")

        # Multi-turn estimate
        print("\n" + "="*80)
        print("[MULTI-TURN SESSION ESTIMATE (with responses)]")
        print("="*80)

        avg_input = 5000  # Average input per turn
        avg_output = 2000  # Average output per turn
        num_turns = 5

        input_cost = (avg_input * num_turns / 1_000_000) * prices["input"]
        output_cost = (avg_output * num_turns / 1_000_000) * prices["output"]
        total_cost = input_cost + output_cost

        print(f"\nAssuming 5-turn session:")
        print(f"  Input:   ~{avg_input * num_turns:,} tokens * ${prices['input']}/M = ${input_cost:.4f}")
        print(f"  Output:  ~{avg_output * num_turns:,} tokens * ${prices['output']}/M = ${output_cost:.4f}")
        print(f"  Total:   ${total_cost:.4f}")

        # Recommendations
        print("\n" + "="*80)
        print("[RECOMMENDATIONS]")
        print("="*80)
        haiku_turn = (5000/1_000_000)*PRICING['claude-haiku-4-5']['input']
        sonnet_turn = (5000/1_000_000)*PRICING['claude-sonnet-5']['input']
        opus_turn = (5000/1_000_000)*PRICING['claude-opus-4-8']['input']
        print(f"""
[OK] Use Haiku 4.5 for:     Simple bugfixes, quick iterations (~${haiku_turn:.4f}/turn)
[OK] Use Sonnet 5 for:      Most development work (~${sonnet_turn:.4f}/turn)
[OK] Use Opus 4.8 for:      Complex architecture work (~${opus_turn:.4f}/turn)

Tips to reduce costs:
  - Reuse context between turns (Claude keeps it cached)
  - Send files progressively, not all at once
  - Use token counting to estimate before big tasks
  - Consider Haiku for routine work

How to get ACCURATE token counts:
  1. Set your ANTHROPIC_API_KEY: export ANTHROPIC_API_KEY='sk-...'
  2. Run: python estimate_tokens.py [model]
  3. The API-based script will count actual tokens used
""")

        print("="*80)

def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        if sys.argv[1] == "--help" or sys.argv[1] == "-h":
            print("""
Usage: python estimate_tokens_local.py [model] [pattern]

Arguments:
  model      Claude model to use (default: claude-opus-4-8)
             Options: claude-haiku-4-5, claude-sonnet-5, claude-opus-4-8
  pattern    File pattern to scan (default: *.py)
             Examples: *.py, *.ts, *.tsx

IMPORTANT:
  This is a LOCAL estimation tool that does NOT require an API key.
  For accurate token counts, set ANTHROPIC_API_KEY and run: estimate_tokens.py

Examples:
  python estimate_tokens_local.py
  python estimate_tokens_local.py claude-sonnet-5
  python estimate_tokens_local.py claude-opus-4-8 "*.py"
""")
            return

        model = sys.argv[1] if sys.argv[1] in PRICING else "claude-opus-4-8"
        pattern = sys.argv[2] if len(sys.argv) > 2 else "*.py"
    else:
        model = "claude-sonnet-5"
        pattern = "*.py"

    # Check if model is valid
    if model not in PRICING:
        print(f"[ERROR] Unknown model: {model}")
        print(f"Available models: {', '.join(PRICING.keys())}")
        sys.exit(1)

    # Run estimation
    estimator = TokenEstimator(model=model)
    estimator.scan_project(pattern=pattern)
    estimator.print_dashboard()

if __name__ == "__main__":
    main()
