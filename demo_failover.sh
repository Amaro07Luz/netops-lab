#!/usr/bin/env bash

set -u


R1="clab-redundant-bgp-lab-r1"
HOST1="clab-redundant-bgp-lab-host1"

PRIMARY_INTERFACE="eth2"

PREFIX="10.20.1.0/24"
DESTINATION="10.20.1.10"

LINK_DOWN=false


cleanup() {

    if [[ "$LINK_DOWN" == "true" ]]; then

        echo
        echo "Safety cleanup: restoring R1 eth2..."

        docker exec \
            "$R1" \
            ip link set \
            "$PRIMARY_INTERFACE" up \
            2>/dev/null || true

    fi
}

trap cleanup EXIT INT TERM


echo "============================================================"
echo "                 NETOPS FAILOVER DEMO"
echo "============================================================"
echo


# =========================================================
# VERIFY LAB
# =========================================================

if ! docker inspect "$R1" >/dev/null 2>&1; then

    echo "ERROR: redundant BGP lab is not running."
    echo
    echo "Start the platform first with:"
    echo
    echo "    ./start_netops.sh"

    exit 1

fi


if ! docker inspect "$HOST1" >/dev/null 2>&1; then

    echo "ERROR: host1 container is not running."

    exit 1

fi


# =========================================================
# INITIAL STATE
# =========================================================

echo "Current route on R1:"
echo

docker exec \
    "$R1" \
    vtysh \
    -c "show ip route $PREFIX"


echo
echo "============================================================"
echo "                  FAILURE INJECTION"
echo "============================================================"
echo

echo "Taking R1 $PRIMARY_INTERFACE DOWN..."

docker exec \
    "$R1" \
    ip link set \
    "$PRIMARY_INTERFACE" down

LINK_DOWN=true


echo
echo "Waiting for BGP failover..."

sleep 3


# =========================================================
# FAILOVER STATE
# =========================================================

echo
echo "Route after primary failure:"
echo

docker exec \
    "$R1" \
    vtysh \
    -c "show ip route $PREFIX"


echo
echo "Testing protected host1 -> host2 traffic..."
echo

docker exec \
    "$HOST1" \
    ping \
    -c 4 \
    "$DESTINATION"


echo
echo "------------------------------------------------------------"
echo "Check the dashboard now."
echo
echo "Expected state:"
echo
echo "    FAILOVER ACTIVE"
echo "    R1 -> R3 -> R2"
echo "    Critical routes: DEGRADED"
echo "    Protected traffic: still reachable"
echo
echo "Press Enter when you are ready to restore the primary path."
echo "------------------------------------------------------------"

read -r


# =========================================================
# RESTORE PRIMARY
# =========================================================

echo
echo "============================================================"
echo "                       RECOVERY"
echo "============================================================"
echo

echo "Restoring R1 $PRIMARY_INTERFACE..."

docker exec \
    "$R1" \
    ip link set \
    "$PRIMARY_INTERFACE" up

LINK_DOWN=false


echo
echo "Waiting for BGP to reconverge..."

sleep 4


echo
echo "Route after recovery:"
echo

docker exec \
    "$R1" \
    vtysh \
    -c "show ip route $PREFIX"


echo
echo "============================================================"
echo "                   DEMO COMPLETE"
echo "============================================================"
echo
echo "The dashboard should return to:"
echo
echo "    PRIMARY PATH ACTIVE — R1 -> R2"
echo
