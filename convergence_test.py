import json
import re
import subprocess
import time
from datetime import datetime, timezone

from database import (
    initialize_database,
    save_convergence_test
)


R1_CONTAINER = "clab-redundant-bgp-lab-r1"
HOST1_CONTAINER = "clab-redundant-bgp-lab-host1"

PRIMARY_INTERFACE = "eth2"

DESTINATION_IP = "10.20.1.10"
PREFIX = "10.20.1.0/24"

PRIMARY_NEXT_HOP = "10.0.12.2"
BACKUP_NEXT_HOP = "10.0.13.2"

POLL_INTERVAL = 0.05
FAILOVER_TIMEOUT = 10
FAILBACK_TIMEOUT = 20


def set_interface(state):
    result = subprocess.run(
        [
            "docker",
            "exec",
            R1_CONTAINER,
            "ip",
            "link",
            "set",
            PRIMARY_INTERFACE,
            state
        ],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
        )


def get_selected_next_hop():
    result = subprocess.run(
        [
            "docker",
            "exec",
            R1_CONTAINER,
            "vtysh",
            "-c",
            f"show ip route {PREFIX} json"
        ],
        capture_output=True,
        text=True,
        timeout=3
    )

    if result.returncode != 0:
        return None

    try:
        data = json.loads(
            result.stdout
        )
    except json.JSONDecodeError:
        return None

    routes = data.get(
        PREFIX,
        []
    )

    for route in routes:

        if not (
            route.get("selected", False)
            and
            route.get("installed", False)
        ):
            continue

        for nexthop in route.get(
            "nexthops",
            []
        ):

            if (
                nexthop.get("active", False)
                and
                nexthop.get("fib", False)
            ):
                return nexthop.get(
                    "ip"
                )

    return None


def wait_for_next_hop(
    expected_next_hop,
    timeout
):
    start = time.perf_counter()

    while True:

        actual_next_hop = (
            get_selected_next_hop()
        )

        if (
            actual_next_hop
            == expected_next_hop
        ):
            return (
                time.perf_counter()
                - start
            )

        if (
            time.perf_counter()
            - start
            >= timeout
        ):
            raise TimeoutError(
                f"Timed out waiting for "
                f"{expected_next_hop}. "
                f"Current next hop: "
                f"{actual_next_hop}"
            )

        time.sleep(
            POLL_INTERVAL
        )


def analyze_ping_output(output):
    summary_pattern = re.compile(
        r"(\d+)\s+packets transmitted,"
        r"\s+(\d+)\s+received,"
        r".*?([\d.]+)% packet loss"
    )

    summary_match = summary_pattern.search(
        output
    )

    transmitted = None
    received = None
    packet_loss = None

    if summary_match:

        transmitted = int(
            summary_match.group(1)
        )

        received = int(
            summary_match.group(2)
        )

        packet_loss = float(
            summary_match.group(3)
        )

    timestamp_pattern = re.compile(
        r"^\[(\d+\.\d+)\].*icmp_seq=(\d+)",
        re.MULTILINE
    )

    replies = []

    for match in timestamp_pattern.finditer(
        output
    ):

        timestamp = float(
            match.group(1)
        )

        sequence = int(
            match.group(2)
        )

        replies.append(
            (
                timestamp,
                sequence
            )
        )

    maximum_reply_gap = None

    if len(replies) >= 2:

        reply_gaps = []

        for index in range(
            1,
            len(replies)
        ):

            previous_time = replies[
                index - 1
            ][0]

            current_time = replies[
                index
            ][0]

            reply_gaps.append(
                current_time
                - previous_time
            )

        maximum_reply_gap = max(
            reply_gaps
        )

    return (
        transmitted,
        received,
        packet_loss,
        maximum_reply_gap
    )


def main():
    
    initialize_database()
    
    print()
    print("NETOPS BGP CONVERGENCE TEST")
    print("=" * 60)

    # ----------------------------------
    # Verify healthy starting condition
    # ----------------------------------

    starting_next_hop = (
        get_selected_next_hop()
    )

    print(
        f"Starting next hop: "
        f"{starting_next_hop}"
    )

    if (
        starting_next_hop
        != PRIMARY_NEXT_HOP
    ):
        print(
            "ERROR: primary route is not "
            "currently active."
        )

        return

    # ----------------------------------
    # Start continuous traffic
    # ----------------------------------

    print(
        "Starting continuous ICMP traffic..."
    )

    ping_process = subprocess.Popen(
        [
            "docker",
            "exec",
            HOST1_CONTAINER,
            "ping",
            "-D",
            "-i",
            "0.1",
            "-W",
            "1",
            "-c",
            "100",
            DESTINATION_IP
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    # Give ping some healthy baseline time.
    time.sleep(2)

    link_restored = False

    try:

        # ==============================
        # PRIMARY FAILURE
        # ==============================

        print()
        print(
            "Taking primary R1-R2 "
            "link DOWN..."
        )

        failure_time = (
            time.perf_counter()
        )

        set_interface(
            "down"
        )

        failover_seconds = (
            wait_for_next_hop(
                BACKUP_NEXT_HOP,
                FAILOVER_TIMEOUT
            )
        )

        actual_failover_time = (
            time.perf_counter()
            - failure_time
        )

        print(
            f"Backup next hop active: "
            f"{BACKUP_NEXT_HOP}"
        )

        print(
            f"Control-plane failover: "
            f"{actual_failover_time:.3f} "
            f"seconds"
        )

        # Keep the network on the
        # backup path for a few seconds.
        time.sleep(3)

        # ==============================
        # PRIMARY RESTORATION
        # ==============================

        print()
        print(
            "Restoring primary R1-R2 "
            "link..."
        )

        recovery_time = (
            time.perf_counter()
        )

        set_interface(
            "up"
        )

        link_restored = True

        failback_seconds = (
            wait_for_next_hop(
                PRIMARY_NEXT_HOP,
                FAILBACK_TIMEOUT
            )
        )

        actual_failback_time = (
            time.perf_counter()
            - recovery_time
        )

        print(
            f"Primary next hop active: "
            f"{PRIMARY_NEXT_HOP}"
        )

        print(
            f"Control-plane failback: "
            f"{actual_failback_time:.3f} "
            f"seconds"
        )

    finally:

        # Never leave the lab broken if
        # the experiment throws an error.
        if not link_restored:

            print()
            print(
                "Safety cleanup: "
                "restoring eth2..."
            )

            try:
                set_interface(
                    "up"
                )
            except Exception as error:
                print(
                    f"Cleanup error: {error}"
                )

    # ----------------------------------
    # Wait for continuous ping to finish
    # ----------------------------------

    try:

        ping_output, _ = (
            ping_process.communicate(
                timeout=15
            )
        )

    except subprocess.TimeoutExpired:

        ping_process.terminate()

        ping_output, _ = (
            ping_process.communicate()
        )

    (
        transmitted,
        received,
        packet_loss,
        maximum_reply_gap
    ) = analyze_ping_output(
        ping_output
    )

    print()
    print("DATA-PLANE RESULTS")
    print("=" * 60)

    if transmitted is None:

        print(
            "Could not parse ping summary."
        )

    else:

        lost = (
            transmitted
            - received
        )

        print(
            f"Packets transmitted: "
            f"{transmitted}"
        )

        print(
            f"Packets received:    "
            f"{received}"
        )

        print(
            f"Packets lost:        "
            f"{lost}"
        )

        print(
            f"Packet loss:         "
            f"{packet_loss:.1f}%"
        )

    if maximum_reply_gap is not None:

        print(
            f"Maximum reply gap:   "
            f"{maximum_reply_gap:.3f} "
            f"seconds"
        )
    if transmitted is not None:
        packets_lost = (
            transmitted - received
        )

        timestamp = datetime.now(
            timezone.utc
        ).isoformat()

        save_convergence_test(
            timestamp,
            "redundant-bgp-lab",
            PREFIX,
            PRIMARY_NEXT_HOP,
            BACKUP_NEXT_HOP,
            actual_failover_time,
            actual_failback_time,
            transmitted,
            received,
            packets_lost,
            packet_loss,
            maximum_reply_gap
        )

        print()
    
        print(
            "Convergence test saved "
            "to network.db"
        )

    print()
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
