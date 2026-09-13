import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from monitor import (
    check_bgp_neighbor,
    check_bgp_route,
    check_interface
)


class TestBgpMonitoring(unittest.TestCase):

    @patch("monitor.subprocess.run")
    def test_bgp_established_is_healthy(
        self,
        mock_run
    ):
        bgp_output = {
            "ipv4Unicast": {
                "as": 65001,
                "peers": {
                    "10.0.12.2": {
                        "remoteAs": 65002,
                        "state": "Established",
                        "pfxRcd": 1
                    }
                }
            }
        }

        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(bgp_output),
            stderr=""
        )

        (
            healthy,
            state,
            local_as,
            remote_as,
            prefixes_received,
            error
        ) = check_bgp_neighbor(
            "test-router",
            "10.0.12.2"
        )

        self.assertTrue(healthy)
        self.assertEqual(
            state,
            "Established"
        )
        self.assertEqual(
            local_as,
            65001
        )
        self.assertEqual(
            remote_as,
            65002
        )
        self.assertEqual(
            prefixes_received,
            1
        )
        self.assertIsNone(error)


    @patch("monitor.subprocess.run")
    def test_bgp_active_is_unhealthy(
        self,
        mock_run
    ):
        bgp_output = {
            "ipv4Unicast": {
                "as": 65001,
                "peers": {
                    "10.0.12.2": {
                        "remoteAs": 65002,
                        "state": "Active",
                        "pfxRcd": 0
                    }
                }
            }
        }

        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(bgp_output),
            stderr=""
        )

        result = check_bgp_neighbor(
            "test-router",
            "10.0.12.2"
        )

        healthy = result[0]
        state = result[1]
        prefixes_received = result[4]

        self.assertFalse(healthy)
        self.assertEqual(
            state,
            "Active"
        )
        self.assertEqual(
            prefixes_received,
            0
        )


class TestRouteMonitoring(unittest.TestCase):

    @patch("monitor.subprocess.run")
    def test_installed_bgp_route(
        self,
        mock_run
    ):
        route_output = {
            "10.20.1.0/24": [
                {
                    "protocol": "bgp",
                    "selected": True,
                    "installed": True,
                    "nexthops": [
                        {
                            "ip": "10.0.12.2",
                            "interfaceName": "eth2",
                            "active": True,
                            "fib": True
                        }
                    ]
                }
            ]
        }

        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(route_output),
            stderr=""
        )

        (
            healthy,
            route_found,
            protocol,
            installed,
            selected,
            next_hop,
            interface_name,
            error
        ) = check_bgp_route(
            "test-router",
            "10.20.1.0/24",
            "bgp"
        )

        self.assertTrue(healthy)
        self.assertTrue(route_found)

        self.assertEqual(
            protocol,
            "bgp"
        )

        self.assertTrue(installed)
        self.assertTrue(selected)

        self.assertEqual(
            next_hop,
            "10.0.12.2"
        )

        self.assertEqual(
            interface_name,
            "eth2"
        )

        self.assertIsNone(error)


    @patch("monitor.subprocess.run")
    def test_missing_route_is_unhealthy(
        self,
        mock_run
    ):
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout="{}",
            stderr=""
        )

        result = check_bgp_route(
            "test-router",
            "10.20.1.0/24",
            "bgp"
        )

        healthy = result[0]
        route_found = result[1]
        error = result[7]

        self.assertFalse(healthy)
        self.assertFalse(route_found)

        self.assertIn(
            "not found",
            error
        )


class TestInterfaceMonitoring(unittest.TestCase):

    @patch("monitor.subprocess.run")
    def test_interface_up(
        self,
        mock_run
    ):
        interface_output = [
            {
                "ifname": "eth2",
                "flags": [
                    "BROADCAST",
                    "MULTICAST",
                    "UP",
                    "LOWER_UP"
                ],
                "mtu": 9500,
                "operstate": "UP",
                "address": "aa:bb:cc:dd:ee:ff",
                "stats64": {
                    "rx": {
                        "packets": 100,
                        "errors": 0,
                        "dropped": 0
                    },
                    "tx": {
                        "packets": 120,
                        "errors": 0,
                        "dropped": 0
                    }
                }
            }
        ]

        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                interface_output
            ),
            stderr=""
        )

        result = check_interface(
            "test-router",
            "eth2"
        )

        self.assertTrue(
            result[0]
        )

        self.assertEqual(
            result[1],
            "UP"
        )

        self.assertTrue(
            result[2]
        )

        self.assertTrue(
            result[3]
        )


    @patch("monitor.subprocess.run")
    def test_interface_down(
        self,
        mock_run
    ):
        interface_output = [
            {
                "ifname": "eth2",
                "flags": [
                    "BROADCAST",
                    "MULTICAST"
                ],
                "mtu": 9500,
                "operstate": "DOWN",
                "address": "aa:bb:cc:dd:ee:ff",
                "stats64": {
                    "rx": {
                        "packets": 100,
                        "errors": 0,
                        "dropped": 0
                    },
                    "tx": {
                        "packets": 120,
                        "errors": 0,
                        "dropped": 0
                    }
                }
            }
        ]

        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                interface_output
            ),
            stderr=""
        )

        result = check_interface(
            "test-router",
            "eth2"
        )

        self.assertFalse(
            result[0]
        )

        self.assertEqual(
            result[1],
            "DOWN"
        )

        self.assertFalse(
            result[2]
        )

        self.assertFalse(
            result[3]
        )


if __name__ == "__main__":
    unittest.main()
