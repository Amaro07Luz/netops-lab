import json
import subprocess


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


def main():
    (
        healthy,
        state,
        local_as,
        remote_as,
        prefixes_received,
        error
    ) = check_bgp_neighbor(
        "clab-bgp-lab-r1",
        "10.0.12.2"
    )

    print("BGP CHECK")
    print("=" * 50)

    print(
        f"Healthy:           {healthy}"
    )

    print(
        f"State:             {state}"
    )

    print(
        f"Local AS:          {local_as}"
    )

    print(
        f"Remote AS:         {remote_as}"
    )

    print(
        f"Prefixes Received: {prefixes_received}"
    )

    print(
        f"Error:             {error}"
    )


if __name__ == "__main__":
    main()