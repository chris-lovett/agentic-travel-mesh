#!/usr/bin/env bash
# ==============================================================================
# CAMP Travel Showcase Automated Test Runner
# ==============================================================================
# Usage:
#   ./run_tests.sh              # Runs full test suite
#   ./run_tests.sh -k test_act1 # Passes additional arguments to pytest
#   ./run_tests.sh --tier 1     # Runs specific tier tests
# ==============================================================================

set -euo pipefail

# ANSI color codes for terminal output
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    NC='\033[0m' # No Color
else
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    CYAN=''
    BOLD=''
    NC=''
fi

# Locate repository root and switch to it
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${SCRIPT_DIR}"
cd "${REPO_ROOT}"

echo -e "${BLUE}${BOLD}==================================================================${NC}"
echo -e "${CYAN}${BOLD}       CAMP Travel Showcase — Automated Test Runner               ${NC}"
echo -e "${BLUE}${BOLD}==================================================================${NC}"

# Detect Python interpreter
PYTHON_BIN=""
if [ -n "${VIRTUAL_ENV:-}" ] && [ -x "${VIRTUAL_ENV}/bin/python" ]; then
    PYTHON_BIN="${VIRTUAL_ENV}/bin/python"
    echo -e "${BLUE}▶ Environment:${NC} Active virtual environment detected (${PYTHON_BIN})"
elif [ -x "${REPO_ROOT}/.venv/bin/python" ]; then
    PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
    echo -e "${BLUE}▶ Environment:${NC} Local .venv detected (${PYTHON_BIN})"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
    echo -e "${BLUE}▶ Environment:${NC} System python3 (${PYTHON_BIN})"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
    echo -e "${BLUE}▶ Environment:${NC} System python (${PYTHON_BIN})"
else
    echo -e "${RED}${BOLD}Error:${NC} No Python interpreter found. Please install Python 3.9+." >&2
    exit 1
fi

PY_VERSION="$("${PYTHON_BIN}" --version 2>&1)"
echo -e "${BLUE}▶ Python version:${NC} ${PY_VERSION}"

# Verify pytest availability
if ! "${PYTHON_BIN}" -m pytest --version >/dev/null 2>&1; then
    USER_BASE="$("${PYTHON_BIN}" -m site --user-base 2>/dev/null || true)"
    if [ -n "${USER_BASE}" ] && [ -x "${USER_BASE}/bin/pytest" ]; then
        export PATH="${USER_BASE}/bin:${PATH}"
    fi
fi

if ! "${PYTHON_BIN}" -m pytest --version >/dev/null 2>&1 && ! command -v pytest >/dev/null 2>&1; then
    echo -e "${RED}${BOLD}Error:${NC} pytest is not installed in ${PYTHON_BIN}." >&2
    echo -e "${YELLOW}Install required test dependencies with:${NC}" >&2
    echo -e "    ${PYTHON_BIN} -m pip install -r requirements.txt" >&2
    exit 1
fi

PYTEST_VERSION="$("${PYTHON_BIN}" -m pytest --version 2>&1 | head -n 1)"
echo -e "${BLUE}▶ Pytest version:${NC} ${PYTEST_VERSION}"

# Configure PYTHONPATH so all internal packages (agents, mcp_tools, etc.) resolve cleanly
export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"
echo -e "${BLUE}▶ PYTHONPATH:${NC} ${PYTHONPATH}"
echo -e "${BLUE}${BOLD}------------------------------------------------------------------${NC}"

# Parse command line arguments and support --tier / -m flags
TEST_ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)
            echo "Usage: ./run_tests.sh [OPTIONS] [PYTEST_ARGS...]"
            echo ""
            echo "Options:"
            echo "  --tier <1-4>   Run tests with marker tier<N>"
            echo "  --tier1        Run tier1 tests"
            echo "  --tier2        Run tier2 tests"
            echo "  --tier3        Run tier3 tests"
            echo "  --tier4        Run tier4 tests"
            echo "  --governance   Run governance tests"
            echo "  -k <pattern>   Filter tests by keyword expression"
            echo "  -v, --verbose  Verbose pytest output"
            exit 0
            ;;
        --tier)
            if [[ $# -gt 1 ]]; then
                TEST_ARGS+=("-m" "tier$2")
                shift 2
            else
                echo -e "${RED}Error: --tier requires an argument (1, 2, 3, or 4)${NC}" >&2
                exit 1
            fi
            ;;
        --tier1)
            TEST_ARGS+=("-m" "tier1")
            shift
            ;;
        --tier2)
            TEST_ARGS+=("-m" "tier2")
            shift
            ;;
        --tier3)
            TEST_ARGS+=("-m" "tier3")
            shift
            ;;
        --tier4)
            TEST_ARGS+=("-m" "tier4")
            shift
            ;;
        --governance)
            TEST_ARGS+=("-m" "governance")
            shift
            ;;
        --fast)
            TEST_ARGS+=("-q")
            shift
            ;;
        *)
            TEST_ARGS+=("$1")
            shift
            ;;
    esac
done

# If no arguments provided, default to tests/ directory
if [ ${#TEST_ARGS[@]} -eq 0 ]; then
    TEST_ARGS=("tests/")
fi

echo -e "${CYAN}Executing: ${PYTHON_BIN} -m pytest ${TEST_ARGS[*]}${NC}"
echo -e "${BLUE}${BOLD}------------------------------------------------------------------${NC}"

# Execute tests and capture exit code
set +e
"${PYTHON_BIN}" -m pytest "${TEST_ARGS[@]}"
EXIT_CODE=$?
set -e

echo -e "${BLUE}${BOLD}==================================================================${NC}"
if [ ${EXIT_CODE} -eq 0 ]; then
    echo -e "${GREEN}${BOLD}✓ TEST RUN SUCCESSFUL: All CAMP Travel Showcase tests passed!${NC}"
    echo -e "${GREEN}Exit code: 0${NC}"
else
    echo -e "${RED}${BOLD}✗ TEST RUN FAILED: Test suite encountered failures or errors.${NC}"
    echo -e "${RED}Exit code: ${EXIT_CODE}${NC}"
fi
echo -e "${BLUE}${BOLD}==================================================================${NC}"

exit ${EXIT_CODE}
