#!/bin/bash
# 📊 Token Cost Estimator Wrapper
# Usage: ./estimate-tokens.sh [model] [pattern]

MODEL=${1:-claude-sonnet-5}
PATTERN=${2:-"*.py"}

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔄 Estimating tokens for OceENS project...${NC}"
echo ""

python3 estimate_tokens.py "$MODEL" "$PATTERN"
