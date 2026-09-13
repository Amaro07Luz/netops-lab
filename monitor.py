import platform
import subprocess
import yaml
import re
import shutil
import time
import socket
import http.client
import json
import sqlite3
import sys
from datetime import datetime, timezone

from database import (
    initialize_database,
    save_result,
    save_incident,
    save_service_incident,
    save_service_result,
    save_http_result,
    save_bgp_result,
    save_bgp_incident,
    save_route_result,
    save_route_incident,
    save_interface_result,
    save_interface_incident,
    save_correlated_incident,
    save_tracker_collection,
    load_tracker_collection,
    open_incident,
    resolve_incident
)


CHECK_INTERVAL_SECONDS = 10

FAILURE_THRESHOLD = 3  # Number of consecutive failures before marking as DOWN
RECOVERY_THRESHOLD = 3  # Number of consecutive successes before marking as UP


def separator(character):
    return character * shutil.get_terminal_size(
        fallback=(80, 24)
    ).columns

def load_config(filename):
    with open(filename, "r") as file:
        data = yaml.safe_load(file)

    return data

def get_availability(status):
    if status == "DOWN":
        return "DOWN"

    if status in ["UP", "DEGRADED"]:
        return "UP"

    return "UNKNOWN"

def check_bgp_neighbor(
    container_name,
    neighbor_ip
):
    command = [
        "docker",
        "exec",
        container_name,
        "vtysh",
        "-c",
        "show bgp summary json"
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5
        )

    except subprocess.TimeoutExpired:
        return (
            False,
            "UNKNOWN",
            None,
            None,
            None,
            "BGP command timed out"
        )

    except OSError as error:
        return (
            False,
            "UNKNOWN",
            None,
            None,
            None,
            str(error)
        )

    if result.returncode != 0:
        return (
            False,
            "UNKNOWN",
            None,
            None,
            None,
            result.stderr.strip()
        )

    try:
        data = json.loads(
            result.stdout
        )

    except json.JSONDecodeError as error:
        return (
            False,
            "UNKNOWN",
            None,
            None,
            None,
            f"Invalid JSON: {error}"
        )

    ipv4_data = data.get(
        "ipv4Unicast",
        {}
    )

    local_as = ipv4_data.get(
        "as"
    )

    peers = ipv4_data.get(
        "peers",
        {}
    )

    peer = peers.get(
        neighbor_ip
    )

    if peer is None:
        return (
            False,
            "NOT_FOUND",
            local_as,
            None,
            None,
            f"Neighbor {neighbor_ip} not found"
        )

    state = peer.get(
        "state",
        "UNKNOWN"
    )

    remote_as = peer.get(
        "remoteAs"
    )

    prefixes_received = peer.get(
        "pfxRcd"
    )

    healthy = (
        state == "Established"
    )

    return (
        healthy,
        state,
        local_as,
        remote_as,
        prefixes_received,
        None
    )

def monitor_bgp(
    bgp_routers,
    bgp_trackers
):
    print()
    print("BGP STATUS")
    print(separator("="))

    previous_hostname = None

    for router in bgp_routers:
        hostname = router["hostname"]
        container_name = router["container"]

        if previous_hostname is not None:
            print()

        previous_hostname = hostname

        neighbors = router.get(
            "neighbors",
            []
        )

        for neighbor in neighbors:
            neighbor_ip = neighbor[
                "neighbor_ip"
            ]

            expected_remote_as = neighbor.get(
                "expected_remote_as"
            )

            (
                healthy,
                state,
                local_as,
                remote_as,
                prefixes_received,
                error
            ) = check_bgp_neighbor(
                container_name,
                neighbor_ip
            )

            timestamp = datetime.now(
                timezone.utc
            ).isoformat()

            save_bgp_result(
                timestamp,
                hostname,
                container_name,
                neighbor_ip,
                local_as,
                remote_as,
                state,
                prefixes_received,
                healthy,
                error
            )

            if prefixes_received is None:
                prefixes_display = "---"
            else:
                prefixes_display = str(
                    prefixes_received
                )

            error_display = (
                error
                if error is not None
                else ""
            )

            print(
                f"Router: {hostname:<8} "
                f"Neighbor: {neighbor_ip:<15} "
                f"State: {state:<12} "
                f"Local AS: {str(local_as):<8} "
                f"Remote AS: {str(remote_as):<8} "
                f"Prefixes: {prefixes_display:<5} "
                f"{error_display}"
            )

            # ------------------------------------
            # Validate expected remote AS
            # ------------------------------------

            if (
                expected_remote_as is not None
                and
                remote_as is not None
                and
                remote_as != expected_remote_as
            ):
                print(
                    f"    WARNING: expected remote AS "
                    f"{expected_remote_as}, "
                    f"got {remote_as}"
                )

            # ====================================
            # BGP INCIDENT THRESHOLD LOGIC
            # ====================================

            observed_status = (
                "UP"
                if healthy
                else "DOWN"
            )

            tracker_key = (
                hostname,
                neighbor_ip
            )

            if tracker_key not in bgp_trackers:
                bgp_trackers[
                    tracker_key
                ] = {
                    "confirmed_state":
                        observed_status,

                    "failure_count": 0,
                    "success_count": 0
                }

            tracker = bgp_trackers[
                tracker_key
            ]

            # ------------------------------------
            # BGP currently DOWN
            # ------------------------------------

            if observed_status == "DOWN":
                tracker[
                    "failure_count"
                ] += 1

                tracker[
                    "success_count"
                ] = 0

                if (
                    tracker[
                        "confirmed_state"
                    ] != "DOWN"

                    and

                    tracker[
                        "failure_count"
                    ] >= FAILURE_THRESHOLD
                ):
                    previous_state = tracker[
                        "confirmed_state"
                    ]

                    tracker[
                        "confirmed_state"
                    ] = "DOWN"

                    print(
                        f"    BGP INCIDENT CONFIRMED: "
                        f"{hostname} -> {neighbor_ip} "
                        f"{previous_state} -> DOWN "
                        f"(FRR state: {state})"
                    )

                    save_bgp_incident(
                        timestamp,
                        hostname,
                        neighbor_ip,
                        previous_state,
                        "DOWN"
                    )

                elif (
                    tracker[
                        "confirmed_state"
                    ] != "DOWN"
                ):
                    print(
                        f"    BGP pending failure: "
                        f"{tracker['failure_count']}/"
                        f"{FAILURE_THRESHOLD}"
                    )

            # ------------------------------------
            # BGP currently UP
            # ------------------------------------

            else:
                tracker[
                    "success_count"
                ] += 1

                tracker[
                    "failure_count"
                ] = 0

                if (
                    tracker[
                        "confirmed_state"
                    ] == "DOWN"

                    and

                    tracker[
                        "success_count"
                    ] >= RECOVERY_THRESHOLD
                ):
                    tracker[
                        "confirmed_state"
                    ] = "UP"

                    print(
                        f"    BGP RECOVERY CONFIRMED: "
                        f"{hostname} -> {neighbor_ip} "
                        f"DOWN -> UP"
                    )

                    save_bgp_incident(
                        timestamp,
                        hostname,
                        neighbor_ip,
                        "DOWN",
                        "UP"
                    )

                elif (
                    tracker[
                        "confirmed_state"
                    ] == "DOWN"
                ):
                    print(
                        f"    BGP pending recovery: "
                        f"{tracker['success_count']}/"
                        f"{RECOVERY_THRESHOLD}"
                    )

    print(separator("="))

def ping_device(ip):
    operating_system = platform.system()

    if operating_system == "Windows":
        command = [
            "ping",
            "-n",
            "4",
            "-w",
            "1000",
            ip
        ]

    else:
        command = [
            "ping",
            "-c",
            "4",
            "-W",
            "1",
            ip
        ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    output = result.stdout

    if operating_system == "Windows":
        loss_match = re.search(
            r"\((\d+)%\s*loss\)",
            output,
            re.IGNORECASE
        )

        latency_match = re.search(
            r"Average = (\d+)ms",
            output,
            re.IGNORECASE
        )

    else:
        loss_match = re.search(
            r"(\d+(?:\.\d+)?)%\s*packet loss",
            output,
            re.IGNORECASE
        )

        latency_match = re.search(
            r"=\s*[\d.]+/([\d.]+)/",
            output
        )

    if loss_match:
        packet_loss = float(
            loss_match.group(1)
        )

    else:
        packet_loss = None

    if latency_match:
        latency = float(
            latency_match.group(1)
        )

    else:
        latency = None

    if packet_loss == 100:
        reachable = False

    else:
        reachable = True

    return reachable, latency, packet_loss

def check_tcp_port(ip, port, timeout=1.5):
    
    start_time = time.perf_counter()

    try:
        with socket.create_connection(
            (ip, port),
            timeout=timeout
        ):
            end_time = time.perf_counter()

            connect_time_ms = (
                end_time - start_time
            ) * 1000

            return True, connect_time_ms, None

    except ConnectionRefusedError:
        return False, None, "Connection refused"

    except socket.timeout:
        return False, None, "Timeout"

    except OSError as error:
        return False, None, str(error)

def check_http_service(ip, port, path="/", expected_status=200, timeout=2.0):
    start_time = time.perf_counter()
    
    connection = http.client.HTTPConnection(
        ip,
        port,
        timeout=timeout
    )
    
    try:
        connection.request(
            "GET",
            path
        )
        
        response = connection.getresponse()
        end_time = time.perf_counter()
        
        response_time_ms = (
            end_time - start_time
        ) * 1000
        
        actual_status = response.status
        
        if actual_status == expected_status:
            healthy = True
            error = None
        else:
            healthy = False
            error = (f"EXPECTED_{expected_status}"
                    f"_GOT_{actual_status}")
        return (
            healthy,
            actual_status,
            response_time_ms,
            error
        )
        
    except socket.timeout:
        return False, None, None, "Timeout"
    
    except OSError as error:
        return False, None, None, str(error)
    
    finally:
        connection.close()

def check_bgp_route(
    container_name,
    prefix,
    expected_protocol
):
    command = [
        "docker",
        "exec",
        container_name,
        "vtysh",
        "-c",
        f"show ip route {prefix} json"
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5
        )

    except subprocess.TimeoutExpired:
        return (
            False,
            False,
            None,
            False,
            False,
            None,
            None,
            "Route command timed out"
        )

    except OSError as error:
        return (
            False,
            False,
            None,
            False,
            False,
            None,
            None,
            str(error)
        )

    if result.returncode != 0:
        return (
            False,
            False,
            None,
            False,
            False,
            None,
            None,
            result.stderr.strip()
        )

    try:
        data = json.loads(
            result.stdout
        )

    except json.JSONDecodeError as error:
        return (
            False,
            False,
            None,
            False,
            False,
            None,
            None,
            f"Invalid JSON: {error}"
        )

    route_entries = data.get(
        prefix
    )

    if not route_entries:
        return (
            False,
            False,
            None,
            False,
            False,
            None,
            None,
            f"Route {prefix} not found"
        )

    selected_route = None

    for route in route_entries:

        if (
            route.get("selected", False)
            and
            route.get("installed", False)
        ):
            selected_route = route
            break

    if selected_route is None:
        selected_route = route_entries[0]

    actual_protocol = selected_route.get(
        "protocol"
    )

    installed = selected_route.get(
        "installed",
        False
    )

    selected = selected_route.get(
        "selected",
        False
    )

    nexthops = selected_route.get(
        "nexthops",
        []
    )

    actual_next_hop = None
    interface_name = None

    for nexthop in nexthops:

        if (
            nexthop.get("active", False)
            and
            nexthop.get("fib", False)
        ):
            actual_next_hop = nexthop.get(
                "ip"
            )

            interface_name = nexthop.get(
                "interfaceName"
            )

            break

    base_healthy = (
        actual_protocol == expected_protocol
        and installed
        and selected
        and actual_next_hop is not None
    )

    return (
        base_healthy,
        True,
        actual_protocol,
        installed,
        selected,
        actual_next_hop,
        interface_name,
        None
    )

def check_interface(
    container_name,
    interface_name
):
    command = [
        "docker",
        "exec",
        container_name,
        "ip",
        "-j",
        "-s",
        "link",
        "show",
        "dev",
        interface_name
    ]


    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5
        )


    except subprocess.TimeoutExpired:
        return (
            False,
            "UNKNOWN",
            False,
            False,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            "Interface command timed out"
        )


    except OSError as error:
        return (
            False,
            "UNKNOWN",
            False,
            False,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            str(error)
        )


    if result.returncode != 0:
        return (
            False,
            "UNKNOWN",
            False,
            False,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            result.stderr.strip()
        )


    try:
        data = json.loads(
            result.stdout
        )


    except json.JSONDecodeError as error:
        return (
            False,
            "UNKNOWN",
            False,
            False,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            f"Invalid JSON: {error}"
        )


    if not data:
        return (
            False,
            "NOT_FOUND",
            False,
            False,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            f"Interface {interface_name} not found"
        )


    interface = data[0]


    operstate = interface.get(
        "operstate",
        "UNKNOWN"
    )


    flags = interface.get(
        "flags",
        []
    )


    admin_up = (
        "UP" in flags
    )


    lower_up = (
        "LOWER_UP" in flags
    )


    mtu = interface.get(
        "mtu"
    )


    mac_address = interface.get(
        "address"
    )


    stats = interface.get(
        "stats64",
        {}
    )


    rx = stats.get(
        "rx",
        {}
    )


    tx = stats.get(
        "tx",
        {}
    )


    rx_packets = rx.get(
        "packets"
    )


    tx_packets = tx.get(
        "packets"
    )


    rx_errors = rx.get(
        "errors"
    )


    tx_errors = tx.get(
        "errors"
    )


    rx_dropped = rx.get(
        "dropped"
    )


    tx_dropped = tx.get(
        "dropped"
    )


    healthy = (
        operstate == "UP"
        and admin_up
        and lower_up
    )


    return (
        healthy,
        operstate,
        admin_up,
        lower_up,
        mtu,
        mac_address,
        rx_packets,
        tx_packets,
        rx_errors,
        tx_errors,
        rx_dropped,
        tx_dropped,
        flags,
        None
    )

def correlate_incidents(
    dependencies,
    interface_states,
    bgp_states,
    route_states,
    correlation_trackers
):
    print()
    print("INCIDENT CORRELATION")
    print(separator("="))

    anything_detected = False

    for dependency in dependencies:

        dependency_name = dependency[
            "name"
        ]

        root_cause = dependency[
            "root_cause"
        ]

        root_type = root_cause[
            "type"
        ]

        root_hostname = root_cause[
            "hostname"
        ]

        root_component = "UNKNOWN"
        root_state = "UNKNOWN"

        if root_type == "interface":

            root_component = root_cause[
                "interface"
            ]

            root_state = interface_states.get(
                (
                    root_hostname,
                    root_component
                ),
                "UNKNOWN"
            )

        # --------------------------------
        # BGP dependencies
        # --------------------------------

        failed_bgp = []

        for bgp_dependency in dependency.get(
            "affected_bgp",
            []
        ):

            hostname = bgp_dependency[
                "hostname"
            ]

            neighbor_ip = bgp_dependency[
                "neighbor_ip"
            ]

            state = bgp_states.get(
                (
                    hostname,
                    neighbor_ip
                ),
                "UNKNOWN"
            )

            if state == "DOWN":

                failed_bgp.append(
                    (
                        hostname,
                        neighbor_ip
                    )
                )

        # --------------------------------
        # Route dependencies
        # --------------------------------

        route_details = []

        for route_dependency in dependency.get(
            "affected_routes",
            []
        ):

            hostname = route_dependency[
                "hostname"
            ]

            prefix = route_dependency[
                "prefix"
            ]

            state = route_states.get(
                (
                    hostname,
                    prefix
                ),
                "UNKNOWN"
            )

            route_details.append(
                (
                    hostname,
                    prefix,
                    state
                )
            )

        any_route_down = any(
            state == "DOWN"
            for _, _, state
            in route_details
        )

        any_route_degraded = any(
            state == "DEGRADED"
            for _, _, state
            in route_details
        )

        # ====================================
        # CORRELATED HEALTH
        # ====================================

        if (
            root_state == "DOWN"
            and
            any_route_down
        ):

            correlated_state = "DOWN"

        elif (
            root_state == "DOWN"
            and
            failed_bgp
            and
            any_route_degraded
        ):

            correlated_state = "DEGRADED"

        else:

            correlated_state = "UP"

        if dependency_name not in correlation_trackers:

            correlation_trackers[
                dependency_name
            ] = correlated_state

        previous_state = correlation_trackers[
            dependency_name
        ]

        # ====================================
        # FAILOVER ACTIVE
        # ====================================

        if correlated_state == "DEGRADED":

            anything_detected = True

            print(
                f"FAILOVER ACTIVE: "
                f"{dependency_name}"
            )

            print(
                f"    Primary component "
                f"{root_hostname}:"
                f"{root_component} is DOWN"
            )

            if failed_bgp:

                print(
                    "    Failed primary BGP:"
                )

                for (
                    hostname,
                    neighbor_ip
                ) in failed_bgp:

                    print(
                        f"        "
                        f"{hostname} -> "
                        f"{neighbor_ip}"
                    )

            print(
                "    Protected routes:"
            )

            for (
                hostname,
                prefix,
                state
            ) in route_details:

                print(
                    f"        "
                    f"{hostname}: "
                    f"{prefix} "
                    f"[{state}]"
                )

            print(
                "    Diagnosis: primary path "
                "failed, but alternate BGP "
                "path is maintaining routing."
            )

            if previous_state != "DEGRADED":

                timestamp = datetime.now(
                    timezone.utc
                ).isoformat()

                summary = (
                    f"Primary path "
                    f"{root_hostname}:"
                    f"{root_component} failed; "
                    f"backup routing active"
                )

                save_correlated_incident(
                    timestamp,
                    dependency_name,
                    root_type,
                    root_hostname,
                    root_component,
                    "DEGRADED",
                    summary
                )

                if previous_state == "UP":

                    incident_id = open_incident(
                        dependency_name,
                        root_type,
                        root_hostname,
                        root_component,
                        timestamp,
                        summary
                    )

                    print(
                        f"    Incident "
                        f"#{incident_id} opened"
                    )

                correlation_trackers[
                    dependency_name
                ] = "DEGRADED"

        # ====================================
        # COMPLETE OUTAGE
        # ====================================

        elif correlated_state == "DOWN":

            anything_detected = True

            print(
                f"NETWORK OUTAGE: "
                f"{dependency_name}"
            )

            print(
                f"    Root component "
                f"{root_hostname}:"
                f"{root_component} is DOWN"
            )

            print(
                "    One or more protected "
                "routes are unavailable."
            )

            if previous_state != "DOWN":

                timestamp = datetime.now(
                    timezone.utc
                ).isoformat()

                summary = (
                    f"{root_hostname}:"
                    f"{root_component} down; "
                    f"redundancy insufficient; "
                    f"protected route lost"
                )

                save_correlated_incident(
                    timestamp,
                    dependency_name,
                    root_type,
                    root_hostname,
                    root_component,
                    "DOWN",
                    summary
                )

                if previous_state == "UP":

                    open_incident(
                        dependency_name,
                        root_type,
                        root_hostname,
                        root_component,
                        timestamp,
                        summary
                    )

                correlation_trackers[
                    dependency_name
                ] = "DOWN"

        # ====================================
        # HEALTHY / RECOVERED
        # ====================================

        else:

            if previous_state in (
                "DOWN",
                "DEGRADED"
            ):

                anything_detected = True

                timestamp = datetime.now(
                    timezone.utc
                ).isoformat()

                summary = (
                    f"{dependency_name} "
                    f"returned to primary "
                    f"healthy state"
                )

                save_correlated_incident(
                    timestamp,
                    dependency_name,
                    root_type,
                    root_hostname,
                    root_component,
                    "UP",
                    summary
                )

                duration_seconds = resolve_incident(
                    dependency_name,
                    timestamp,
                    summary
                )

                print(
                    f"PRIMARY PATH RESTORED: "
                    f"{dependency_name}"
                )

                if duration_seconds is not None:

                    print(
                        f"    Degraded/outage "
                        f"duration: "
                        f"{duration_seconds:.1f} "
                        f"seconds"
                    )

            correlation_trackers[
                dependency_name
            ] = "UP"

    if not anything_detected:

        print(
            "No correlated infrastructure "
            "incident detected."
        )

    print(separator("="))

def monitor_devices(
    devices,
    host_trackers,
    service_trackers
):
    print()
    print("NETWORK STATUS")
    print(separator("="))

    print(
        f"{'DEVICE':<15} "
        f"{'IP':<15} "
        f"{'STATUS':<12} "
        f"{'LATENCY':<12} "
        f"{'PACKET LOSS'}"
    )

    print(separator("-"))

    for device_index, device in enumerate(devices):
        hostname = device["hostname"]
        ip = device["ip"]

        reachable, latency, packet_loss = ping_device(ip)

        # ------------------------------------
        # Determine current host health
        # ------------------------------------

        if packet_loss is None:
            status = "UNKNOWN"

        elif packet_loss == 100:
            status = "DOWN"

        elif packet_loss > 0:
            status = "DEGRADED"

        else:
            status = "UP"

        timestamp = datetime.now(
            timezone.utc
        ).isoformat()

        # Save every measurement, even if it
        # does not become a confirmed incident.
        save_result(
            timestamp,
            hostname,
            ip,
            status,
            latency,
            packet_loss
        )

        # ------------------------------------
        # Display values
        # ------------------------------------

        if latency is not None:
            latency_display = f"{latency:.1f} ms"

        else:
            latency_display = "---"

        if packet_loss is not None:
            packet_loss_display = (
                f"{packet_loss:.0f}%"
            )

        else:
            packet_loss_display = "N/A"

        print(
            f"{hostname:<15} "
            f"{ip:<15} "
            f"{status:<12} "
            f"{latency_display:<12} "
            f"{packet_loss_display}"
        )

        # ====================================
        # HOST INCIDENT THRESHOLD LOGIC
        # ====================================

        availability = get_availability(
            status
        )

        # First time this host is seen,
        # create its tracker.
        if hostname not in host_trackers:
            host_trackers[hostname] = {
                "confirmed_state": availability,
                "failure_count": 0,
                "success_count": 0
            }

        tracker = host_trackers[hostname]

        # ------------------------------------
        # Current observation is DOWN
        # ------------------------------------

        if availability == "DOWN":
            tracker["failure_count"] += 1
            tracker["success_count"] = 0

            # Only confirm an outage after
            # enough consecutive failures.
            if (
                tracker["confirmed_state"] != "DOWN"
                and
                tracker["failure_count"]
                >= FAILURE_THRESHOLD
            ):
                previous_confirmed_state = (
                    tracker["confirmed_state"]
                )

                tracker[
                    "confirmed_state"
                ] = "DOWN"

                print(
                    f"    INCIDENT CONFIRMED: "
                    f"{hostname} "
                    f"{previous_confirmed_state} "
                    f"-> DOWN"
                )

                save_incident(
                    timestamp,
                    hostname,
                    ip,
                    previous_confirmed_state,
                    "DOWN"
                )

            elif (
                tracker["confirmed_state"]
                != "DOWN"
            ):
                print(
                    f"    Pending failure: "
                    f"{tracker['failure_count']}/"
                    f"{FAILURE_THRESHOLD}"
                )

        # ------------------------------------
        # Current observation is available
        # ------------------------------------

        elif availability == "UP":
            tracker["success_count"] += 1
            tracker["failure_count"] = 0

            # If we previously confirmed DOWN,
            # require several successful checks
            # before confirming recovery.
            if (
                tracker["confirmed_state"]
                == "DOWN"
                and
                tracker["success_count"]
                >= RECOVERY_THRESHOLD
            ):
                tracker[
                    "confirmed_state"
                ] = "UP"

                print(
                    f"    RECOVERY CONFIRMED: "
                    f"{hostname} "
                    f"DOWN -> UP"
                )

                save_incident(
                    timestamp,
                    hostname,
                    ip,
                    "DOWN",
                    "UP"
                )

            elif (
                tracker["confirmed_state"]
                == "DOWN"
            ):
                print(
                    f"    Pending recovery: "
                    f"{tracker['success_count']}/"
                    f"{RECOVERY_THRESHOLD}"
                )

            elif (
                tracker["confirmed_state"]
                == "UNKNOWN"
            ):
                tracker[
                    "confirmed_state"
                ] = "UP"

        # ------------------------------------
        # UNKNOWN does not count as success
        # or failure
        # ------------------------------------

        else:
            tracker["failure_count"] = 0
            tracker["success_count"] = 0

        # ====================================
        # SERVICE MONITORING
        # ====================================

        services = device.get(
            "services",
            []
        )

        for service in services:
            service_name = service["name"]
            port = service["port"]

            check_type = service.get(
                "check",
                "tcp"
            )

            # These only apply to HTTP checks.
            actual_status = None
            path = None
            expected_status = None

            # ------------------------------------
            # Perform the configured check
            # ------------------------------------

            if check_type == "http":
                path = service.get(
                    "path",
                    "/"
                )

                expected_status = service.get(
                    "expected_status",
                    200
                )

                (
                    service_up,
                    actual_status,
                    check_time,
                    error
                ) = check_http_service(
                    ip,
                    port,
                    path,
                    expected_status
                )

            else:
                (
                    service_up,
                    check_time,
                    error
                ) = check_tcp_port(
                    ip,
                    port
                )

            # ------------------------------------
            # Determine service status
            # ------------------------------------

            if service_up:
                service_status = "UP"
                error_display = ""

            else:
                service_status = "DOWN"
                error_display = error

            if check_time is not None:
                time_display = (
                    f"{check_time:.1f} ms"
                )

            else:
                time_display = "---"

            # Every service check needs its own
            # timestamp.
            service_timestamp = datetime.now(
                timezone.utc
            ).isoformat()

            # ------------------------------------
            # Save the measurement
            # ------------------------------------

            if check_type == "http":

                save_http_result(
                    service_timestamp,
                    hostname,
                    ip,
                    service_name,
                    port,
                    path,
                    expected_status,
                    actual_status,
                    service_status,
                    check_time,
                    error
                )

            else:

                save_service_result(
                    service_timestamp,
                    hostname,
                    ip,
                    service_name,
                    port,
                    service_status,
                    check_time,
                    error
                )

            # ------------------------------------
            # Print service information
            # ------------------------------------

            if check_type == "http":

                status_code_display = (
                    str(actual_status)
                    if actual_status is not None
                    else "---"
                )

                print(
                    f"Service: {service_name:<15} "
                    f"Port: {port:<6} "
                    f"Status: {service_status:<6}"
                )

                print(
                    f"      HTTP "
                    f"GET {path:<10} "
                    f"HTTP Code: {status_code_display:<4} "
                    f"Response Time: {time_display:<12} "
                    f"{error_display}"
                )

            else:

                print(
                    f"Service: {service_name:<15} "
                    f"Port: {port:<6} "
                    f"Status: {service_status:<6} "
                    f"Connect Time: {time_display:<12} "
                    f"{error_display}"
                )

            # ====================================
            # SERVICE INCIDENT THRESHOLD LOGIC
            # ====================================

            service_key = (
                hostname,
                service_name,
                port
            )

            # First time this particular service
            # is seen, create its tracker.
            if (
                service_key
                not in service_trackers
            ):
                service_trackers[
                    service_key
                ] = {
                    "confirmed_state":
                        service_status,

                    "failure_count": 0,
                    "success_count": 0
                }

            service_tracker = (
                service_trackers[
                    service_key
                ]
            )

            # ------------------------------------
            # Service currently DOWN
            # ------------------------------------

            if service_status == "DOWN":
                service_tracker[
                    "failure_count"
                ] += 1

                service_tracker[
                    "success_count"
                ] = 0

                if (
                    service_tracker[
                        "confirmed_state"
                    ] != "DOWN"

                    and

                    service_tracker[
                        "failure_count"
                    ] >= FAILURE_THRESHOLD
                ):
                    previous_confirmed_state = (
                        service_tracker[
                            "confirmed_state"
                        ]
                    )

                    service_tracker[
                        "confirmed_state"
                    ] = "DOWN"

                    print(
                        f"    SERVICE INCIDENT "
                        f"CONFIRMED: "
                        f"{hostname} service "
                        f"{service_name} "
                        f"on port {port} "
                        f"{previous_confirmed_state} "
                        f"-> DOWN"
                    )

                    save_service_incident(
                        service_timestamp,
                        hostname,
                        ip,
                        service_name,
                        port,
                        previous_confirmed_state,
                        "DOWN"
                    )

                elif (
                    service_tracker[
                        "confirmed_state"
                    ] != "DOWN"
                ):
                    print(
                        f"    Service pending "
                        f"failure: "
                        f"{service_tracker['failure_count']}/"
                        f"{FAILURE_THRESHOLD}"
                    )

            # ------------------------------------
            # Service currently UP
            # ------------------------------------

            elif service_status == "UP":
                service_tracker[
                    "success_count"
                ] += 1

                service_tracker[
                    "failure_count"
                ] = 0

                if (
                    service_tracker[
                        "confirmed_state"
                    ] == "DOWN"

                    and

                    service_tracker[
                        "success_count"
                    ] >= RECOVERY_THRESHOLD
                ):
                    service_tracker[
                        "confirmed_state"
                    ] = "UP"

                    print(
                        f"    SERVICE RECOVERY "
                        f"CONFIRMED: "
                        f"{hostname} service "
                        f"{service_name} "
                        f"on port {port} "
                        f"DOWN -> UP"
                    )

                    save_service_incident(
                        service_timestamp,
                        hostname,
                        ip,
                        service_name,
                        port,
                        "DOWN",
                        "UP"
                    )

                elif (
                    service_tracker[
                        "confirmed_state"
                    ] == "DOWN"
                ):
                    print(
                        f"    Service pending "
                        f"recovery: "
                        f"{service_tracker['success_count']}/"
                        f"{RECOVERY_THRESHOLD}"
                    )

        if device_index < len(devices) - 1:
            print(separator(""))

    print(separator("="))
    
def monitor_routes(
    critical_routes,
    route_trackers
):
    route_states = {}

    print()
    print("CRITICAL ROUTES")
    print(separator("="))

    for route_config in critical_routes:

        hostname = route_config[
            "hostname"
        ]

        container_name = route_config[
            "container"
        ]

        prefix = route_config[
            "prefix"
        ]

        expected_protocol = route_config.get(
            "expected_protocol",
            "bgp"
        )

        # Backward compatibility with
        # your original devices.yaml.
        primary_next_hop = route_config.get(
            "primary_next_hop",
            route_config.get(
                "expected_next_hop"
            )
        )

        backup_next_hops = route_config.get(
            "backup_next_hops",
            []
        )

        (
            base_healthy,
            route_found,
            actual_protocol,
            installed,
            selected,
            actual_next_hop,
            interface_name,
            error
        ) = check_bgp_route(
            container_name,
            prefix,
            expected_protocol
        )

        # ====================================
        # DETERMINE ROUTE STATE
        # ====================================

        if not base_healthy:

            route_status = "DOWN"

        elif actual_next_hop == primary_next_hop:

            route_status = "UP"

        elif actual_next_hop in backup_next_hops:

            route_status = "DEGRADED"

        else:

            route_status = "DOWN"

            if error is None:
                error = (
                    f"Unexpected next hop "
                    f"{actual_next_hop}"
                )

        route_states[
            (
                hostname,
                prefix
            )
        ] = route_status

        timestamp = datetime.now(
            timezone.utc
        ).isoformat()

        # DEGRADED is still forwarding,
        # so availability is healthy.
        availability_healthy = (
            route_status != "DOWN"
        )

        save_route_result(
            timestamp,
            hostname,
            container_name,
            prefix,
            expected_protocol,
            actual_protocol,
            primary_next_hop,
            actual_next_hop,
            interface_name,
            route_found,
            installed,
            selected,
            availability_healthy,
            error
        )

        protocol_display = (
            actual_protocol
            if actual_protocol is not None
            else "---"
        )

        next_hop_display = (
            actual_next_hop
            if actual_next_hop is not None
            else "---"
        )

        interface_display = (
            interface_name
            if interface_name is not None
            else "---"
        )

        print(
            f"Router: {hostname:<8} "
            f"Prefix: {prefix:<18} "
            f"Status: {route_status:<9} "
            f"Protocol: {protocol_display:<5} "
            f"Next Hop: {next_hop_display:<15} "
            f"Interface: {interface_display}"
        )

        if route_status == "DEGRADED":
            print(
                f"    FAILOVER ACTIVE: "
                f"primary next hop "
                f"{primary_next_hop} unavailable; "
                f"using backup "
                f"{actual_next_hop}"
            )

        if error is not None:
            print(
                f"    Error: {error}"
            )

        # ====================================
        # AVAILABILITY INCIDENT TRACKER
        # ====================================

        # A backup route is still an available
        # route. Only DOWN is an outage.
        availability_status = (
            "DOWN"
            if route_status == "DOWN"
            else "UP"
        )

        tracker_key = (
            hostname,
            prefix
        )

        if tracker_key not in route_trackers:

            route_trackers[
                tracker_key
            ] = {
                "confirmed_state":
                    availability_status,

                "failure_count": 0,
                "success_count": 0
            }

        tracker = route_trackers[
            tracker_key
        ]

        if availability_status == "DOWN":

            tracker[
                "failure_count"
            ] += 1

            tracker[
                "success_count"
            ] = 0

            if (
                tracker[
                    "confirmed_state"
                ] != "DOWN"
                and
                tracker[
                    "failure_count"
                ] >= FAILURE_THRESHOLD
            ):

                previous_state = tracker[
                    "confirmed_state"
                ]

                tracker[
                    "confirmed_state"
                ] = "DOWN"

                print(
                    f"    ROUTE INCIDENT CONFIRMED: "
                    f"{hostname} {prefix} "
                    f"{previous_state} -> DOWN"
                )

                save_route_incident(
                    timestamp,
                    hostname,
                    prefix,
                    previous_state,
                    "DOWN"
                )

            elif (
                tracker[
                    "confirmed_state"
                ] != "DOWN"
            ):

                print(
                    f"    Route pending failure: "
                    f"{tracker['failure_count']}/"
                    f"{FAILURE_THRESHOLD}"
                )

        else:

            tracker[
                "success_count"
            ] += 1

            tracker[
                "failure_count"
            ] = 0

            if (
                tracker[
                    "confirmed_state"
                ] == "DOWN"
                and
                tracker[
                    "success_count"
                ] >= RECOVERY_THRESHOLD
            ):

                tracker[
                    "confirmed_state"
                ] = "UP"

                print(
                    f"    ROUTE RECOVERY CONFIRMED: "
                    f"{hostname} {prefix} "
                    f"DOWN -> UP"
                )

                save_route_incident(
                    timestamp,
                    hostname,
                    prefix,
                    "DOWN",
                    "UP"
                )

            elif (
                tracker[
                    "confirmed_state"
                ] == "DOWN"
            ):

                print(
                    f"    Route pending recovery: "
                    f"{tracker['success_count']}/"
                    f"{RECOVERY_THRESHOLD}"
                )

    print(separator("="))

    return route_states

def monitor_bgp(
    bgp_routers,
    bgp_trackers
):
    bgp_states = {}

    print()
    print("BGP STATUS")
    print(separator("="))

    for router in bgp_routers:
        hostname = router["hostname"]
        container_name = router["container"]

        neighbors = router.get(
            "neighbors",
            []
        )

        for neighbor in neighbors:
            neighbor_ip = neighbor[
                "neighbor_ip"
            ]

            expected_remote_as = neighbor.get(
                "expected_remote_as"
            )

            (
                healthy,
                state,
                local_as,
                remote_as,
                prefixes_received,
                error
            ) = check_bgp_neighbor(
                container_name,
                neighbor_ip
            )

            timestamp = datetime.now(
                timezone.utc
            ).isoformat()

            save_bgp_result(
                timestamp,
                hostname,
                container_name,
                neighbor_ip,
                local_as,
                remote_as,
                state,
                prefixes_received,
                healthy,
                error
            )

            # ------------------------------------
            # Convert raw BGP state to UP/DOWN
            # ------------------------------------

            observed_status = (
                "UP"
                if healthy
                else "DOWN"
            )

            # Save current state for correlation
            bgp_states[
                (
                    hostname,
                    neighbor_ip
                )
            ] = observed_status

            # ------------------------------------
            # Display formatting
            # ------------------------------------

            if prefixes_received is None:
                prefixes_display = "---"
            else:
                prefixes_display = str(
                    prefixes_received
                )

            error_display = (
                error
                if error is not None
                else ""
            )

            print(
                f"Router: {hostname:<8} "
                f"Neighbor: {neighbor_ip:<15} "
                f"State: {state:<12} "
                f"Local AS: {str(local_as):<8} "
                f"Remote AS: {str(remote_as):<8} "
                f"Prefixes: {prefixes_display:<5} "
                f"{error_display}"
            )

            # ------------------------------------
            # Validate expected remote AS
            # ------------------------------------

            if (
                expected_remote_as is not None
                and
                remote_as is not None
                and
                remote_as != expected_remote_as
            ):
                print(
                    f"    WARNING: expected remote AS "
                    f"{expected_remote_as}, "
                    f"got {remote_as}"
                )

            # ====================================
            # BGP INCIDENT TRACKER
            # ====================================

            tracker_key = (
                hostname,
                neighbor_ip
            )

            if tracker_key not in bgp_trackers:
                bgp_trackers[
                    tracker_key
                ] = {
                    "confirmed_state":
                        observed_status,

                    "failure_count": 0,
                    "success_count": 0
                }

            tracker = bgp_trackers[
                tracker_key
            ]

            # ====================================
            # BGP CURRENTLY DOWN
            # ====================================

            if observed_status == "DOWN":

                tracker[
                    "failure_count"
                ] += 1

                tracker[
                    "success_count"
                ] = 0

                if (
                    tracker[
                        "confirmed_state"
                    ] != "DOWN"
                    and
                    tracker[
                        "failure_count"
                    ] >= FAILURE_THRESHOLD
                ):
                    previous_state = tracker[
                        "confirmed_state"
                    ]

                    tracker[
                        "confirmed_state"
                    ] = "DOWN"

                    print(
                        f"    BGP INCIDENT CONFIRMED: "
                        f"{hostname} -> {neighbor_ip} "
                        f"{previous_state} -> DOWN "
                        f"(FRR state: {state})"
                    )

                    save_bgp_incident(
                        timestamp,
                        hostname,
                        neighbor_ip,
                        previous_state,
                        "DOWN"
                    )

                elif (
                    tracker[
                        "confirmed_state"
                    ] != "DOWN"
                ):
                    print(
                        f"    BGP pending failure: "
                        f"{tracker['failure_count']}/"
                        f"{FAILURE_THRESHOLD}"
                    )

            # ====================================
            # BGP CURRENTLY UP
            # ====================================

            else:

                tracker[
                    "success_count"
                ] += 1

                tracker[
                    "failure_count"
                ] = 0

                if (
                    tracker[
                        "confirmed_state"
                    ] == "DOWN"
                    and
                    tracker[
                        "success_count"
                    ] >= RECOVERY_THRESHOLD
                ):
                    tracker[
                        "confirmed_state"
                    ] = "UP"

                    print(
                        f"    BGP RECOVERY CONFIRMED: "
                        f"{hostname} -> {neighbor_ip} "
                        f"DOWN -> UP"
                    )

                    save_bgp_incident(
                        timestamp,
                        hostname,
                        neighbor_ip,
                        "DOWN",
                        "UP"
                    )

                elif (
                    tracker[
                        "confirmed_state"
                    ] == "DOWN"
                ):
                    print(
                        f"    BGP pending recovery: "
                        f"{tracker['success_count']}/"
                        f"{RECOVERY_THRESHOLD}"
                    )

    print(separator("="))

    return bgp_states

def monitor_interfaces(
    interfaces,
    interface_trackers
):
    
    interface_states = {}
    
    print()
    print("INTERFACE STATUS")
    print(separator("="))

    previous_hostname = None

    for interface_config in interfaces:

        hostname = interface_config[
            "hostname"
        ]

        if previous_hostname is not None and hostname != previous_hostname:
            print()

        previous_hostname = hostname

        container_name = interface_config[
            "container"
        ]

        interface_name = interface_config[
            "interface"
        ]

        (
            healthy,
            operstate,
            admin_up,
            lower_up,
            mtu,
            mac_address,
            rx_packets,
            tx_packets,
            rx_errors,
            tx_errors,
            rx_dropped,
            tx_dropped,
            flags,
            error
        ) = check_interface(
            container_name,
            interface_name
        )

        timestamp = datetime.now(
            timezone.utc
        ).isoformat()

        save_interface_result(
            timestamp,
            hostname,
            container_name,
            interface_name,
            operstate,
            admin_up,
            lower_up,
            mtu,
            mac_address,
            rx_packets,
            tx_packets,
            rx_errors,
            tx_errors,
            rx_dropped,
            tx_dropped,
            healthy,
            error
        )

        status = (
            "UP"
            if healthy
            else "DOWN"
        )
        interface_states[
            (
                hostname,
                interface_name
            )
        ] = status

        print(
            f"Router: {hostname:<8} "
            f"Interface: {interface_name:<8} "
            f"Status: {status:<5} "
            f"Oper: {operstate:<8} "
            f"Admin: {str(admin_up):<5} "
            f"Carrier: {str(lower_up):<5} "
            f"RX: {str(rx_packets):<8} "
            f"TX: {str(tx_packets):<8} "
            f"Drops RX/TX: "
            f"{rx_dropped}/{tx_dropped}"
        )

        if error is not None:
            print(
                f"    Error: {error}"
            )

        tracker_key = (
            hostname,
            interface_name
        )

        if tracker_key not in interface_trackers:
            interface_trackers[
                tracker_key
            ] = {
                "confirmed_state": status,
                "failure_count": 0,
                "success_count": 0
            }

        tracker = interface_trackers[
            tracker_key
        ]

        # ================================
        # INTERFACE FAILURE
        # ================================

        if status == "DOWN":

            tracker[
                "failure_count"
            ] += 1

            tracker[
                "success_count"
            ] = 0

            if (
                tracker["confirmed_state"] != "DOWN"
                and
                tracker["failure_count"]
                >= FAILURE_THRESHOLD
            ):
                previous_state = tracker[
                    "confirmed_state"
                ]

                tracker[
                    "confirmed_state"
                ] = "DOWN"

                print(
                    f"    INTERFACE INCIDENT CONFIRMED: "
                    f"{hostname} {interface_name} "
                    f"{previous_state} -> DOWN"
                )

                save_interface_incident(
                    timestamp,
                    hostname,
                    interface_name,
                    previous_state,
                    "DOWN"
                )

            elif (
                tracker["confirmed_state"]
                != "DOWN"
            ):
                print(
                    f"    Interface pending failure: "
                    f"{tracker['failure_count']}/"
                    f"{FAILURE_THRESHOLD}"
                )

        # ================================
        # INTERFACE HEALTHY
        # ================================

        else:

            tracker[
                "success_count"
            ] += 1

            tracker[
                "failure_count"
            ] = 0

            if (
                tracker["confirmed_state"] == "DOWN"
                and
                tracker["success_count"]
                >= RECOVERY_THRESHOLD
            ):
                tracker[
                    "confirmed_state"
                ] = "UP"

                print(
                    f"    INTERFACE RECOVERY CONFIRMED: "
                    f"{hostname} {interface_name} "
                    f"DOWN -> UP"
                )

                save_interface_incident(
                    timestamp,
                    hostname,
                    interface_name,
                    "DOWN",
                    "UP"
                )

            elif (
                tracker["confirmed_state"]
                == "DOWN"
            ):
                print(
                    f"    Interface pending recovery: "
                    f"{tracker['success_count']}/"
                    f"{RECOVERY_THRESHOLD}"
                )

    print(separator("="))
    
    return interface_states

def main():
    initialize_database()

    config_file = (
    sys.argv[1]
    if len(sys.argv) > 1
    else "devices.yaml"
    )

    print(
        f"Configuration: {config_file}"
    )

    config = load_config(
        config_file
    )
    
    monitor_namespace = config.get(
        "monitor_namespace",
        "default"
    )

    devices = config.get(
        "devices",
        []
    )

    interfaces = config.get(
        "interfaces",
        []
    )

    bgp_routers = config.get(
        "bgp_routers",
        []
    )

    critical_routes = config.get(
        "critical_routes",
        []
    )
    
    dependencies = config.get(
        "dependencies",
        []
    )
    
    host_trackers = load_tracker_collection(
        f"{monitor_namespace}:host"
    )

    service_trackers = load_tracker_collection(
        f"{monitor_namespace}:service"
    )

    interface_trackers = load_tracker_collection(
        f"{monitor_namespace}:interface"
    )

    bgp_trackers = load_tracker_collection(
        f"{monitor_namespace}:bgp"
    )

    route_trackers = load_tracker_collection(
        f"{monitor_namespace}:route"
    )

    correlation_trackers = load_tracker_collection(
        f"{monitor_namespace}:correlation"
    )

    print(
        "Starting network monitoring..."
    )

    print(
        f"Check interval: "
        f"{CHECK_INTERVAL_SECONDS} seconds"
    )

    print(
        f"Failure threshold: "
        f"{FAILURE_THRESHOLD} checks"
    )

    print(
        f"Recovery threshold: "
        f"{RECOVERY_THRESHOLD} checks"
    )

    try:
        while True:

            monitor_devices(
                devices,
                host_trackers,
                service_trackers
            )
            
            interface_states = monitor_interfaces(
                interfaces,
                interface_trackers
            )

            bgp_states = monitor_bgp(
                bgp_routers,
                bgp_trackers
            )

            route_states = monitor_routes(
                critical_routes,
                route_trackers
            )
            
            correlate_incidents(
                dependencies,
                interface_states,
                bgp_states,
                route_states,
                correlation_trackers
            )
            
            save_tracker_collection(
                f"{monitor_namespace}:host",
                host_trackers
            )

            save_tracker_collection(
                f"{monitor_namespace}:service",
                service_trackers
            )

            save_tracker_collection(
                f"{monitor_namespace}:interface",
                interface_trackers
            )

            save_tracker_collection(
                f"{monitor_namespace}:bgp",
                bgp_trackers
            )

            save_tracker_collection(
                f"{monitor_namespace}:route",
                route_trackers
            )

            save_tracker_collection(
                f"{monitor_namespace}:correlation",
                correlation_trackers
            )

            print(
                f"\nNext check in "
                f"{CHECK_INTERVAL_SECONDS} "
                f"seconds..."
            )

            time.sleep(
                CHECK_INTERVAL_SECONDS
            )

    except KeyboardInterrupt:
        print(
            "\nMonitoring stopped by user."
        )


if __name__ == "__main__":
    main()