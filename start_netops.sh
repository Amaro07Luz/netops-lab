#!/usr/bin/env bash

set -u


SCRIPT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")"
    pwd
)"

PROJECT_DIR="$SCRIPT_DIR"

LAB_DIR="$PROJECT_DIR/containerlab/redundant-bgp-lab"

TOPOLOGY_FILE="$LAB_DIR/redundant-bgp-lab.clab.yml"

PYTHON="$PROJECT_DIR/.venv-wsl/bin/python"

CONFIG_FILE="$PROJECT_DIR/devices-redundant.yaml"

LOG_DIR="$PROJECT_DIR/logs"

MONITOR_LOG="$LOG_DIR/monitor.log"

API_LOG="$LOG_DIR/api.log"


# =========================================================
# EXPECTED CONTAINERS
# =========================================================

EXPECTED_CONTAINERS=(
    "clab-redundant-bgp-lab-r1"
    "clab-redundant-bgp-lab-r2"
    "clab-redundant-bgp-lab-r3"
    "clab-redundant-bgp-lab-host1"
    "clab-redundant-bgp-lab-host2"
)


# =========================================================
# CLEANUP
# =========================================================

cleanup() {
    echo
    echo "Stopping NetOps application processes..."

    if [[ -n "${MONITOR_PID:-}" ]]; then
        kill "$MONITOR_PID" 2>/dev/null || true
    fi

    if [[ -n "${API_PID:-}" ]]; then
        kill "$API_PID" 2>/dev/null || true
    fi

    wait 2>/dev/null || true

    echo "Monitor and API stopped."
    echo
    echo "Containerlab topology was left running."
    echo "Use ./stop_netops.sh if you want to destroy it."
}

trap cleanup EXIT INT TERM


# =========================================================
# HEADER
# =========================================================

clear

echo "============================================================"
echo "                  NETOPS LAB STARTUP"
echo "============================================================"
echo


# =========================================================
# VALIDATION
# =========================================================

echo "[1/6] Checking environment..."


if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: docker command was not found."
    exit 1
fi


if ! docker info >/dev/null 2>&1; then
    echo "ERROR: Docker engine is not available."
    exit 1
fi


if ! command -v containerlab >/dev/null 2>&1; then
    echo "ERROR: containerlab command was not found."
    exit 1
fi


if [[ ! -x "$PYTHON" ]]; then
    echo "ERROR: WSL virtual environment was not found:"
    echo "$PYTHON"
    exit 1
fi


if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "ERROR: monitor configuration was not found:"
    echo "$CONFIG_FILE"
    exit 1
fi


if [[ ! -f "$TOPOLOGY_FILE" ]]; then
    echo "ERROR: Containerlab topology was not found:"
    echo "$TOPOLOGY_FILE"
    exit 1
fi


mkdir -p "$LOG_DIR"

echo "Environment OK."


# =========================================================
# CHECK LAB
# =========================================================

echo
echo "[2/6] Checking redundant BGP lab..."

LAB_READY=true

for container in "${EXPECTED_CONTAINERS[@]}"; do

    running="$(
        docker inspect \
            -f '{{.State.Running}}' \
            "$container" \
            2>/dev/null \
            || echo "false"
    )"

    if [[ "$running" != "true" ]]; then
        LAB_READY=false
        break
    fi

done


if [[ "$LAB_READY" == "true" ]]; then

    echo "Redundant BGP lab is already running."

else

    echo "Lab is not fully running."
    echo "Deploying topology..."

    cd "$LAB_DIR" || exit 1

    containerlab deploy \
        -t "$TOPOLOGY_FILE"

    if [[ $? -ne 0 ]]; then
        echo "ERROR: Containerlab deployment failed."
        exit 1
    fi

fi


# =========================================================
# VERIFY LAB
# =========================================================

echo
echo "[3/6] Verifying containers..."

sleep 2

for container in "${EXPECTED_CONTAINERS[@]}"; do

    running="$(
        docker inspect \
            -f '{{.State.Running}}' \
            "$container" \
            2>/dev/null \
            || echo "false"
    )"

    if [[ "$running" != "true" ]]; then
        echo "ERROR: $container is not running."
        exit 1
    fi

    echo "  UP  $container"

done


# =========================================================
# START MONITOR
# =========================================================

echo
echo "[4/6] Starting monitoring engine..."

cd "$PROJECT_DIR" || exit 1

"$PYTHON" \
    monitor.py \
    devices-redundant.yaml \
    > "$MONITOR_LOG" \
    2>&1 &

MONITOR_PID=$!

sleep 1


if ! kill -0 "$MONITOR_PID" 2>/dev/null; then
    echo "ERROR: monitor.py stopped unexpectedly."
    echo
    tail -n 30 "$MONITOR_LOG"
    exit 1
fi

echo "Monitor PID: $MONITOR_PID"
echo "Log: $MONITOR_LOG"


# =========================================================
# START API
# =========================================================

echo
echo "[5/6] Starting API and dashboard..."

"$PYTHON" \
    -m uvicorn \
    api:app \
    --host 0.0.0.0 \
    --port 8001 \
    > "$API_LOG" \
    2>&1 &

API_PID=$!

echo "Waiting for API health check..."

API_READY=false

for attempt in {1..10}; do

    # Make sure Uvicorn itself has not crashed
    if ! kill -0 "$API_PID" 2>/dev/null; then

        echo "ERROR: FastAPI stopped unexpectedly."
        echo
        tail -n 30 "$API_LOG"

        exit 1
    fi

    # Test the actual API endpoint
    if curl \
        --silent \
        --fail \
        --max-time 2 \
        http://127.0.0.1:8001/api/health \
        >/dev/null 2>&1; then

        API_READY=true
        break
    fi

    echo "  Waiting for API... attempt $attempt/10"
    sleep 1

done


if [[ "$API_READY" != "true" ]]; then

    echo "ERROR: API health check failed."
    echo
    echo "API log:"
    tail -n 30 "$API_LOG"

    exit 1

fi


echo "API health check passed."
echo "API PID: $API_PID"
echo "Log: $API_LOG"


# =========================================================
# READY
# =========================================================

echo
echo "[6/6] Startup complete."
echo
echo "============================================================"
echo "                    NETOPS LAB READY"
echo "============================================================"
echo
echo "Dashboard:"
echo "    http://localhost:8001"
echo
echo "FastAPI documentation:"
echo "    http://localhost:8001/docs"
echo
echo "Monitor log:"
echo "    $MONITOR_LOG"
echo
echo "API log:"
echo "    $API_LOG"
echo
echo "Press Ctrl+C to stop the monitor and API."
echo "The Containerlab topology will remain running."
echo
echo "============================================================"


# =========================================================
# PROCESS SUPERVISION
# =========================================================

while true; do

    if ! kill -0 "$MONITOR_PID" 2>/dev/null; then
        echo
        echo "ERROR: Monitoring engine stopped unexpectedly."
        echo
        tail -n 30 "$MONITOR_LOG"
        exit 1
    fi

    if ! kill -0 "$API_PID" 2>/dev/null; then
        echo
        echo "ERROR: API stopped unexpectedly."
        echo
        tail -n 30 "$API_LOG"
        exit 1
    fi

    sleep 5

done
