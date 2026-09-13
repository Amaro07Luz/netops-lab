import json
import subprocess


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


def main():

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
        "clab-bgp-lab-r1",
        "eth2"
    )

    print("INTERFACE CHECK")
    print("=" * 60)

    print(
        f"Healthy:       {healthy}"
    )

    print(
        f"Oper State:    {operstate}"
    )

    print(
        f"Admin Up:      {admin_up}"
    )

    print(
        f"Lower Up:      {lower_up}"
    )

    print(
        f"MTU:           {mtu}"
    )

    print(
        f"MAC Address:   {mac_address}"
    )

    print(
        f"RX Packets:    {rx_packets}"
    )

    print(
        f"TX Packets:    {tx_packets}"
    )

    print(
        f"RX Errors:     {rx_errors}"
    )

    print(
        f"TX Errors:     {tx_errors}"
    )

    print(
        f"RX Dropped:    {rx_dropped}"
    )

    print(
        f"TX Dropped:    {tx_dropped}"
    )

    print(
        f"Flags:         {flags}"
    )

    print(
        f"Error:         {error}"
    )


if __name__ == "__main__":
    main()