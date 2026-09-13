#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")"
    pwd
)"

PROJECT_DIR="$SCRIPT_DIR"

LAB_DIR="$PROJECT_DIR/containerlab/redundant-bgp-lab"

TOPOLOGY_FILE="$LAB_DIR/redundant-bgp-lab.clab.yml"


echo "============================================================"
echo "                  NETOPS LAB SHUTDOWN"
echo "============================================================"
echo


if ! command -v containerlab >/dev/null 2>&1; then
    echo "ERROR: containerlab command was not found."
    exit 1
fi


if [[ ! -f "$TOPOLOGY_FILE" ]]; then
    echo "ERROR: topology file was not found:"
    echo "$TOPOLOGY_FILE"
    exit 1
fi


echo "Destroying redundant BGP topology..."

cd "$LAB_DIR" || exit 1

containerlab destroy \
    -t "$TOPOLOGY_FILE"


echo
echo "NetOps lab topology destroyed."
