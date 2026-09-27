#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status
set -e

# Working directory should be the root of the project
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# 1. Load environment variables from .env
ENV_FILE="$SCRIPT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    # Fallback to core/.env
    ENV_FILE="$SCRIPT_DIR/core/.env"
fi

if [ -f "$ENV_FILE" ]; then
    echo "Loading environment variables from $ENV_FILE..."
    set -a
    source "$ENV_FILE"
    set +a
else
    echo "WARNING: No .env file found at root or core/. Please copy core/.env.example to .env and configure your keys."
fi

# Map APP_* variables to their standard names if not set
export NVIDIA_API_KEY="${NVIDIA_API_KEY:-$APP_NVIDIA_API_KEY}"
export H2OGPTE_API_KEY="${H2OGPTE_API_KEY:-$APP_H2OGPTE_API_KEY}"
export H2OGPTE_URL="${H2OGPTE_URL:-$APP_H2OGPTE_URL}"
export H2OGPTE_MODEL="${H2OGPTE_MODEL:-$APP_H2OGPTE_MODEL}"

# The Far North live assessment/forecast service is file-backed and does not
# require PostgreSQL/PostGIS.  Default to that working local profile: an
# unavailable database must never prevent live environmental providers from
# serving Blangoua or the other covered localities.  Set APP_SKIP_DB_INIT=0
# only when PostgreSQL/PostGIS is intentionally running and required.
export APP_SKIP_DB_INIT="${APP_SKIP_DB_INIT:-1}"

# Check required API key
if [ -z "$NVIDIA_API_KEY" ]; then
    echo "ERROR: NVIDIA_API_KEY is not set. Please set it in your .env file."
    exit 1
fi

# Redis supports background jobs only.  The live environmental assessment and
# forecast routes do not depend on it, so a missing local Redis must not stop
# the application from starting.
echo "Checking Redis status..."
REDIS_AVAILABLE=0
if ! redis-cli ping >/dev/null 2>&1; then
    echo "WARNING: Redis is not available; starting the live assessment API without the optional background worker."
else
    REDIS_AVAILABLE=1
    echo "Redis is running."
fi

# Create trap to kill background processes on script exit
cleanup() {
    echo ""
    echo "Stopping background processes..."
    if [ -n "${SERVER_PID:-}" ]; then
        kill "$SERVER_PID" 2>/dev/null || true
    fi
    if [ -n "${MCP_PID:-}" ]; then
        kill "$MCP_PID" 2>/dev/null || true
    fi
    if [ -n "${WORKER_PID:-}" ]; then
        kill "$WORKER_PID" 2>/dev/null || true
    fi
    exit 0
}
trap cleanup EXIT INT TERM

# Avoid starting a second copy of the stack. This is intentionally a
# non-destructive check: an existing listener may be the user's working app.
port_owner() {
    local port="$1"
    if command -v fuser >/dev/null 2>&1; then
        fuser -n tcp "$port" 2>/dev/null || true
    else
        ss -ltnp "( sport = :$port )" 2>/dev/null | sed -n '2p' || true
    fi
}

for port in 8000 8001; do
    owner="$(port_owner "$port")"
    if [ -n "$owner" ]; then
        echo "Port $port is already in use (owner: $owner)."
        echo "The application may already be running; use http://localhost:3000 and the existing backend."
        echo "Stop the existing stack first if a clean restart is required."
        exit 0
    fi
done

# We must run the backend and worker from the core directory
cd "$SCRIPT_DIR/core"

# Check if virtual environments exist
if [ ! -d "venv" ] || [ ! -d "venv-mcp" ]; then
    echo "ERROR: Virtual environments not found. Please run the setup checklist first!"
    exit 1
fi

# 2. Start MCP server in background
echo "Starting MCP Server..."
./venv-mcp/bin/python3 -m flood_prediction.agents.mcp_unified_flood_server &
MCP_PID=$!
echo "MCP Server started with PID: $MCP_PID"

# 3. Start Redis Worker in background only when Redis is available.
if [ "$REDIS_AVAILABLE" -eq 1 ]; then
    echo "Starting RQ background worker..."
    export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
    ./venv/bin/rq worker > worker_native.log 2>&1 &
    WORKER_PID=$!
    echo "RQ worker started with PID: $WORKER_PID (logs in core/worker_native.log)"
fi

# Give MCP and Worker a moment to initialize
sleep 2

# 4. Start FastAPI server in foreground
echo "Starting Uvicorn web server..."
./venv/bin/uvicorn flood_prediction.server:app --reload --host 0.0.0.0 --port 8000 &
SERVER_PID=$!
wait "$SERVER_PID"
