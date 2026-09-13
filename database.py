import json
import sqlite3
from datetime import datetime


DATABASE_NAME = "network.db"


def initialize_database():
    with sqlite3.connect(DATABASE_NAME) as connection:
        cursor = connection.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS monitoring_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                hostname TEXT NOT NULL,
                ip TEXT NOT NULL,
                status TEXT NOT NULL,
                latency REAL,
                packet_loss REAL
            )
            """
        )
        
        cursor.execute("PRAGMA table_info(monitoring_results)")
        
        columns = [column[1] for column in cursor.fetchall()]
        
        if "packet_loss" not in columns:
            cursor.execute("ALTER TABLE monitoring_results ADD COLUMN packet_loss REAL")
            

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                hostname TEXT NOT NULL,
                ip TEXT NOT NULL,
                previous_status TEXT NOT NULL,
                new_status TEXT NOT NULL
            )
            """
        )
        
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS service_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                hostname TEXT NOT NULL,
                ip TEXT NOT NULL,
                service_name TEXT NOT NULL,
                port INTEGER NOT NULL,
                status TEXT NOT NULL,
                connect_time REAL,
                error TEXT
            )
            """
        )
        
        cursor.execute(
            """ 
            CREATE TABLE IF NOT EXISTS service_incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                hostname TEXT NOT NULL,
                ip TEXT NOT NULL,
                service_name TEXT NOT NULL,
                port INTEGER NOT NULL,
                previous_status TEXT NOT NULL,
                new_status TEXT NOT NULL
            )
            """
        )
        
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS http_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                hostname TEXT NOT NULL,
                ip TEXT NOT NULL,
                service_name TEXT NOT NULL,
                port INTEGER NOT NULL,
                path TEXT NOT NULL,
                expected_status INTEGER NOT NULL,
                actual_status INTEGER,
                status TEXT NOT NULL,
                response_time REAL,
                error TEXT
            )
            """
        )
        
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS bgp_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                hostname TEXT NOT NULL,
                container_name TEXT NOT NULL,
                neighbor_ip TEXT NOT NULL,
                local_as INTEGER,
                remote_as INTEGER,
                state TEXT NOT NULL,
                prefixes_received INTEGER,
                healthy INTEGER NOT NULL,
                error TEXT
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS bgp_incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                hostname TEXT NOT NULL,
                neighbor_ip TEXT NOT NULL,
                previous_state TEXT NOT NULL,
                new_state TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS route_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                hostname TEXT NOT NULL,
                container_name TEXT NOT NULL,
                prefix TEXT NOT NULL,
                expected_protocol TEXT,
                actual_protocol TEXT,
                expected_next_hop TEXT,
                actual_next_hop TEXT,
                interface_name TEXT,
                route_found INTEGER NOT NULL,
                installed INTEGER NOT NULL,
                selected INTEGER NOT NULL,
                healthy INTEGER NOT NULL,
                error TEXT
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS route_incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                hostname TEXT NOT NULL,
                prefix TEXT NOT NULL,
                previous_state TEXT NOT NULL,
                new_state TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS interface_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                hostname TEXT NOT NULL,
                container_name TEXT NOT NULL,
                interface_name TEXT NOT NULL,
                operstate TEXT NOT NULL,
                admin_up INTEGER NOT NULL,
                lower_up INTEGER NOT NULL,
                mtu INTEGER,
                mac_address TEXT,
                rx_packets INTEGER,
                tx_packets INTEGER,
                rx_errors INTEGER,
                tx_errors INTEGER,
                rx_dropped INTEGER,
                tx_dropped INTEGER,
                healthy INTEGER NOT NULL,
                error TEXT
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS interface_incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                hostname TEXT NOT NULL,
                interface_name TEXT NOT NULL,
                previous_state TEXT NOT NULL,
                new_state TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS correlated_incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                dependency_name TEXT NOT NULL,
                root_cause_type TEXT NOT NULL,
                root_cause_device TEXT NOT NULL,
                root_cause_component TEXT NOT NULL,
                state TEXT NOT NULL,
                summary TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS incident_lifecycle (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dependency_name TEXT NOT NULL,
                root_cause_type TEXT NOT NULL,
                root_cause_device TEXT NOT NULL,
                root_cause_component TEXT NOT NULL,
                opened_at TEXT NOT NULL,
                resolved_at TEXT,
                duration_seconds REAL,
                status TEXT NOT NULL,
                summary TEXT
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS monitor_state (
                monitor_type TEXT NOT NULL,
                tracker_key TEXT NOT NULL,
                tracker_value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (
                    monitor_type,
                    tracker_key
                )
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS convergence_tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                lab_name TEXT NOT NULL,
                prefix TEXT NOT NULL,
                primary_next_hop TEXT NOT NULL,
                backup_next_hop TEXT NOT NULL,
                failover_seconds REAL NOT NULL,
                failback_seconds REAL NOT NULL,
                packets_transmitted INTEGER,
                packets_received INTEGER,
                packets_lost INTEGER,
                packet_loss_percent REAL,
                max_reply_gap_seconds REAL
            )
            """
        )

        cursor.execute("PRAGMA table_info(http_results)")
        http_columns = cursor.fetchall()
        actual_status_column = next(
            column for column in http_columns
            if column[1] == "actual_status"
        )

        if actual_status_column[3]:
            cursor.execute("ALTER TABLE http_results RENAME TO http_results_old")
            cursor.execute(
                """
                CREATE TABLE http_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    hostname TEXT NOT NULL,
                    ip TEXT NOT NULL,
                    service_name TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    path TEXT NOT NULL,
                    expected_status INTEGER NOT NULL,
                    actual_status INTEGER,
                    status TEXT NOT NULL,
                    response_time REAL,
                    error TEXT
                )
                """
            )
            
            cursor.execute(
                """
                INSERT INTO http_results
                (id, timestamp, hostname, ip, service_name, port, path,
                expected_status, actual_status, status, response_time, error)
                SELECT id, timestamp, hostname, ip, service_name, port, path,
                expected_status, actual_status, status, response_time, error
                FROM http_results_old
                """
            )
            cursor.execute("DROP TABLE http_results_old")
            
            


def save_convergence_test(
    timestamp,
    lab_name,
    prefix,
    primary_next_hop,
    backup_next_hop,
    failover_seconds,
    failback_seconds,
    packets_transmitted,
    packets_received,
    packets_lost,
    packet_loss_percent,
    max_reply_gap_seconds
):
    with sqlite3.connect(DATABASE_NAME) as connection:
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO convergence_tests
            (
                timestamp,
                lab_name,
                prefix,
                primary_next_hop,
                backup_next_hop,
                failover_seconds,
                failback_seconds,
                packets_transmitted,
                packets_received,
                packets_lost,
                packet_loss_percent,
                max_reply_gap_seconds
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                lab_name,
                prefix,
                primary_next_hop,
                backup_next_hop,
                failover_seconds,
                failback_seconds,
                packets_transmitted,
                packets_received,
                packets_lost,
                packet_loss_percent,
                max_reply_gap_seconds
            )
        )

        connection.commit()


def save_tracker_collection(monitor_type, trackers):
    with sqlite3.connect(DATABASE_NAME) as connection:
        cursor = connection.cursor()

        for tracker_key, tracker_value in trackers.items():
            key_json = json.dumps(tracker_key)
            value_json = json.dumps(tracker_value)

            cursor.execute(
                """
                INSERT INTO monitor_state
                (
                    monitor_type,
                    tracker_key,
                    tracker_value,
                    updated_at
                )
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(monitor_type, tracker_key)
                DO UPDATE SET
                    tracker_value = excluded.tracker_value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (monitor_type, key_json, value_json)
            )

        connection.commit()


def load_tracker_collection(monitor_type):
    trackers = {}

    with sqlite3.connect(DATABASE_NAME) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT tracker_key, tracker_value
            FROM monitor_state
            WHERE monitor_type = ?
            """,
            (monitor_type,)
        )
        rows = cursor.fetchall()

    for key_json, value_json in rows:
        tracker_key = json.loads(key_json)
        tracker_value = json.loads(value_json)

        # JSON turns Python tuples into lists; restore tuple tracker keys.
        if isinstance(tracker_key, list):
            tracker_key = tuple(tracker_key)

        trackers[tracker_key] = tracker_value

    return trackers


def save_result(timestamp, hostname, ip, status, latency, packet_loss):
    with sqlite3.connect(DATABASE_NAME) as connection:
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO monitoring_results
            (timestamp, hostname, ip, status, latency, packet_loss)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (timestamp, hostname, ip, status, latency, packet_loss)
        )

        connection.commit()

def save_incident(timestamp, hostname, ip, previous_status, new_status):
    with sqlite3.connect(DATABASE_NAME) as connection:
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO incidents
            (timestamp, hostname, ip, previous_status, new_status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (timestamp, hostname, ip, previous_status, new_status)
        )

        connection.commit()

def save_service_result(timestamp, hostname, ip, service_name, port, status, connect_time, error):
    with sqlite3.connect(DATABASE_NAME) as connection:
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO service_results
            (timestamp, hostname, ip, service_name, port, status, connect_time, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (timestamp, hostname, ip, service_name, port, status, connect_time, error)
        )

        connection.commit()

def save_service_incident(timestamp, hostname, ip, service_name, port, previous_status, new_status):
    with sqlite3.connect(DATABASE_NAME) as connection:
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO service_incidents
            (timestamp, hostname, ip, service_name, port, previous_status, new_status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (timestamp, hostname, ip, service_name, port, previous_status, new_status)
        )

        connection.commit()

def save_http_result(timestamp, hostname, ip, service_name, port, path, expected_status, actual_status, status, response_time, error):
    with sqlite3.connect(DATABASE_NAME) as connection:
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO http_results
            (timestamp, hostname, ip, service_name, port, path, expected_status, actual_status, status, response_time, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (timestamp, hostname, ip, service_name, port, path, expected_status, actual_status, status, response_time, error)
        )
        connection.commit()
def save_bgp_result(
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
):
    with sqlite3.connect(
        DATABASE_NAME
    ) as connection:

        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO bgp_results
            (
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                hostname,
                container_name,
                neighbor_ip,
                local_as,
                remote_as,
                state,
                prefixes_received,
                int(healthy),
                error
            )
        )
        connection.commit()

def save_bgp_incident(
    timestamp,
    hostname,
    neighbor_ip,
    previous_state,
    new_state
):
    with sqlite3.connect(
        DATABASE_NAME
    ) as connection:

        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO bgp_incidents
            (
                timestamp,
                hostname,
                neighbor_ip,
                previous_state,
                new_state
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                hostname,
                neighbor_ip,
                previous_state,
                new_state
            )
        )

        connection.commit()


def save_route_result(
    timestamp,
    hostname,
    container_name,
    prefix,
    expected_protocol,
    actual_protocol,
    expected_next_hop,
    actual_next_hop,
    interface_name,
    route_found,
    installed,
    selected,
    healthy,
    error
):
    with sqlite3.connect(DATABASE_NAME) as connection:
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO route_results
            (
                timestamp,
                hostname,
                container_name,
                prefix,
                expected_protocol,
                actual_protocol,
                expected_next_hop,
                actual_next_hop,
                interface_name,
                route_found,
                installed,
                selected,
                healthy,
                error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                hostname,
                container_name,
                prefix,
                expected_protocol,
                actual_protocol,
                expected_next_hop,
                actual_next_hop,
                interface_name,
                int(route_found),
                int(installed),
                int(selected),
                int(healthy),
                error
            )
        )

        connection.commit()


def save_route_incident(
    timestamp,
    hostname,
    prefix,
    previous_state,
    new_state
):
    with sqlite3.connect(DATABASE_NAME) as connection:
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO route_incidents
            (
                timestamp,
                hostname,
                prefix,
                previous_state,
                new_state
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                hostname,
                prefix,
                previous_state,
                new_state
            )
        )

        connection.commit()


def save_interface_result(
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
):
    with sqlite3.connect(DATABASE_NAME) as connection:
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO interface_results
            (
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                hostname,
                container_name,
                interface_name,
                operstate,
                int(admin_up),
                int(lower_up),
                mtu,
                mac_address,
                rx_packets,
                tx_packets,
                rx_errors,
                tx_errors,
                rx_dropped,
                tx_dropped,
                int(healthy),
                error
            )
        )

        connection.commit()


def save_correlated_incident(
    timestamp,
    dependency_name,
    root_cause_type,
    root_cause_device,
    root_cause_component,
    state,
    summary
):
    with sqlite3.connect(DATABASE_NAME) as connection:
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO correlated_incidents
            (
                timestamp,
                dependency_name,
                root_cause_type,
                root_cause_device,
                root_cause_component,
                state,
                summary
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                dependency_name,
                root_cause_type,
                root_cause_device,
                root_cause_component,
                state,
                summary
            )
        )

        connection.commit()


def open_incident(
    dependency_name,
    root_cause_type,
    root_cause_device,
    root_cause_component,
    opened_at,
    summary
):
    with sqlite3.connect(DATABASE_NAME) as connection:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT id
            FROM incident_lifecycle
            WHERE dependency_name = ?
              AND status = 'OPEN'
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                dependency_name,
            )
        )

        existing_incident = cursor.fetchone()

        if existing_incident is not None:
            return existing_incident[0]

        cursor.execute(
            """
            INSERT INTO incident_lifecycle
            (
                dependency_name,
                root_cause_type,
                root_cause_device,
                root_cause_component,
                opened_at,
                resolved_at,
                duration_seconds,
                status,
                summary
            )
            VALUES (?, ?, ?, ?, ?, NULL, NULL, 'OPEN', ?)
            """,
            (
                dependency_name,
                root_cause_type,
                root_cause_device,
                root_cause_component,
                opened_at,
                summary
            )
        )

        connection.commit()

        return cursor.lastrowid


def resolve_incident(
    dependency_name,
    resolved_at,
    summary
):
    with sqlite3.connect(DATABASE_NAME) as connection:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                id,
                opened_at
            FROM incident_lifecycle
            WHERE dependency_name = ?
              AND status = 'OPEN'
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                dependency_name,
            )
        )

        incident = cursor.fetchone()

        if incident is None:
            return None

        incident_id = incident[0]
        opened_at = incident[1]

        opened_time = datetime.fromisoformat(
            opened_at
        )

        resolved_time = datetime.fromisoformat(
            resolved_at
        )

        duration_seconds = (
            resolved_time - opened_time
        ).total_seconds()

        cursor.execute(
            """
            UPDATE incident_lifecycle
            SET
                resolved_at = ?,
                duration_seconds = ?,
                status = 'RESOLVED',
                summary = ?
            WHERE id = ?
            """,
            (
                resolved_at,
                duration_seconds,
                summary,
                incident_id
            )
        )

        connection.commit()

        return duration_seconds


def save_interface_incident(
    timestamp,
    hostname,
    interface_name,
    previous_state,
    new_state
):
    with sqlite3.connect(DATABASE_NAME) as connection:
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO interface_incidents
            (
                timestamp,
                hostname,
                interface_name,
                previous_state,
                new_state
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                hostname,
                interface_name,
                previous_state,
                new_state
            )
        )

        connection.commit()
