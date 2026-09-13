import json
import subprocess


def check_bgp_route(
    container_name,
    prefix,
    expected_next_hop
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
            None,
            None,
            f"Invalid JSON: {error}"
        )

    # -----------------------------------------
    # Does the requested prefix exist?
    # -----------------------------------------

    route_entries = data.get(
        prefix
    )

    if not route_entries:
        return (
            False,
            False,
            None,
            False,
            None,
            None,
            f"Route {prefix} not found"
        )

    # FRR returns a list of route entries.
    # For this lab, we expect one selected route.
    route = route_entries[0]

    protocol = route.get(
        "protocol"
    )

    installed = route.get(
        "installed",
        False
    )

    selected = route.get(
        "selected",
        False
    )

    nexthops = route.get(
        "nexthops",
        []
    )

    actual_next_hop = None
    interface_name = None
    next_hop_active = False

    for nexthop in nexthops:

        if nexthop.get("ip") == expected_next_hop:

            actual_next_hop = nexthop.get(
                "ip"
            )

            interface_name = nexthop.get(
                "interfaceName"
            )

            next_hop_active = nexthop.get(
                "active",
                False
            )

            break

    healthy = (
        protocol == "bgp"
        and installed
        and selected
        and actual_next_hop == expected_next_hop
        and next_hop_active
    )

    return (
        healthy,
        True,
        protocol,
        installed,
        actual_next_hop,
        interface_name,
        None
    )


def main():

    (
        healthy,
        route_found,
        protocol,
        installed,
        next_hop,
        interface_name,
        error
    ) = check_bgp_route(
        "clab-bgp-lab-r1",
        "10.20.1.0/24",
        "10.0.12.2"
    )

    print("CRITICAL ROUTE CHECK")
    print("=" * 60)

    print(
        f"Healthy:       {healthy}"
    )

    print(
        f"Route Found:   {route_found}"
    )

    print(
        f"Protocol:      {protocol}"
    )

    print(
        f"Installed:     {installed}"
    )

    print(
        f"Next Hop:      {next_hop}"
    )

    print(
        f"Interface:     {interface_name}"
    )

    print(
        f"Error:         {error}"
    )


if __name__ == "__main__":
    main()