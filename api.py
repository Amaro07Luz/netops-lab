import sqlite3
from pathlib import Path
from fastapi.responses import HTMLResponse
from fastapi import FastAPI, Query


BASE_DIR = Path(__file__).resolve().parent
DATABASE_NAME = BASE_DIR / "network.db"
DASHBOARD_FILE = (
    BASE_DIR / "dashboard.html"
)

app = FastAPI(
    title="NetOps Lab API",
    description=(
        "REST API for network monitoring, "
        "BGP, routing, incidents, and "
        "convergence telemetry."
    ),
    version="1.0.0"
)
@app.get(
    "/",
    response_class=HTMLResponse
)
def dashboard():
    return DASHBOARD_FILE.read_text(
        encoding="utf-8"
    )

# =========================================================
# DATABASE HELPERS
# =========================================================

def get_connection():
    connection = sqlite3.connect(
        DATABASE_NAME
    )

    connection.row_factory = sqlite3.Row

    return connection


def rows_to_dicts(rows):
    return [
        dict(row)
        for row in rows
    ]


# =========================================================
# HEALTH
# =========================================================

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "database": DATABASE_NAME.name
    }


# =========================================================
# DEVICES
# =========================================================

@app.get("/api/devices")
def get_devices():

    with get_connection() as connection:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT m.*
            FROM monitoring_results AS m

            INNER JOIN
            (
                SELECT
                    hostname,
                    MAX(id) AS max_id
                FROM monitoring_results
                GROUP BY hostname
            ) AS latest

            ON m.id = latest.max_id

            ORDER BY m.hostname
            """
        )

        rows = cursor.fetchall()

    return rows_to_dicts(rows)


# =========================================================
# INTERFACES
# =========================================================

@app.get("/api/interfaces")
def get_interfaces():

    with get_connection() as connection:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT i.*
            FROM interface_results AS i

            INNER JOIN
            (
                SELECT
                    hostname,
                    interface_name,
                    MAX(id) AS max_id
                FROM interface_results
                GROUP BY
                    hostname,
                    interface_name
            ) AS latest

            ON i.id = latest.max_id

            ORDER BY
                i.hostname,
                i.interface_name
            """
        )

        rows = cursor.fetchall()

    return rows_to_dicts(rows)


# =========================================================
# BGP
# =========================================================

@app.get("/api/bgp")
def get_bgp():

    with get_connection() as connection:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT b.*
            FROM bgp_results AS b

            INNER JOIN
            (
                SELECT
                    hostname,
                    neighbor_ip,
                    MAX(id) AS max_id
                FROM bgp_results
                GROUP BY
                    hostname,
                    neighbor_ip
            ) AS latest

            ON b.id = latest.max_id

            ORDER BY
                b.hostname,
                b.neighbor_ip
            """
        )

        rows = cursor.fetchall()

    return rows_to_dicts(rows)


# =========================================================
# CRITICAL ROUTES
# =========================================================

@app.get("/api/routes")
def get_routes():

    with get_connection() as connection:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT r.*
            FROM route_results AS r

            INNER JOIN
            (
                SELECT
                    hostname,
                    prefix,
                    MAX(id) AS max_id
                FROM route_results
                GROUP BY
                    hostname,
                    prefix
            ) AS latest

            ON r.id = latest.max_id

            ORDER BY
                r.hostname,
                r.prefix
            """
        )

        rows = cursor.fetchall()

    results = []

    for row in rows:
        route = dict(row)

        healthy = bool(
            route["healthy"]
        )

        expected_next_hop = route[
            "expected_next_hop"
        ]

        actual_next_hop = route[
            "actual_next_hop"
        ]

        if not healthy:
            route["status"] = "DOWN"

        elif (
            actual_next_hop
            == expected_next_hop
        ):
            route["status"] = "UP"

        else:
            route["status"] = "DEGRADED"

        results.append(
            route
        )

    return results


# =========================================================
# CORRELATED INCIDENT EVENTS
# =========================================================

@app.get("/api/correlated-incidents")
def get_correlated_incidents(
    limit: int = Query(
        default=20,
        ge=1,
        le=200
    )
):

    with get_connection() as connection:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM correlated_incidents
            ORDER BY id DESC
            LIMIT ?
            """,
            (
                limit,
            )
        )

        rows = cursor.fetchall()

    return rows_to_dicts(rows)


# =========================================================
# INCIDENT LIFECYCLE
# =========================================================

@app.get("/api/incidents")
def get_incidents(
    limit: int = Query(
        default=20,
        ge=1,
        le=200
    )
):

    with get_connection() as connection:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM incident_lifecycle
            ORDER BY id DESC
            LIMIT ?
            """,
            (
                limit,
            )
        )

        rows = cursor.fetchall()

    return rows_to_dicts(rows)


# =========================================================
# CONVERGENCE TESTS
# =========================================================

@app.get("/api/convergence")
def get_convergence_tests(
    limit: int = Query(
        default=20,
        ge=1,
        le=200
    )
):

    with get_connection() as connection:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM convergence_tests
            ORDER BY id DESC
            LIMIT ?
            """,
            (
                limit,
            )
        )

        rows = cursor.fetchall()

    return rows_to_dicts(rows)


# =========================================================
# DASHBOARD SUMMARY
# =========================================================

@app.get("/api/summary")
def get_summary():

    interfaces = get_interfaces()
    bgp_neighbors = get_bgp()
    routes = get_routes()

    interface_up = sum(
        1
        for interface in interfaces
        if interface["healthy"] == 1
    )

    interface_down = (
        len(interfaces)
        - interface_up
    )

    bgp_up = sum(
        1
        for neighbor in bgp_neighbors
        if neighbor["healthy"] == 1
    )

    bgp_down = (
        len(bgp_neighbors)
        - bgp_up
    )

    route_up = sum(
        1
        for route in routes
        if route["status"] == "UP"
    )

    route_degraded = sum(
        1
        for route in routes
        if route["status"] == "DEGRADED"
    )

    route_down = sum(
        1
        for route in routes
        if route["status"] == "DOWN"
    )

    with get_connection() as connection:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM incident_lifecycle
            WHERE status = 'OPEN'
            """
        )

        open_incidents = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT AVG(duration_seconds)
            FROM incident_lifecycle
            WHERE status = 'RESOLVED'
            """
        )

        average_recovery = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT
                failover_seconds,
                failback_seconds,
                packet_loss_percent,
                max_reply_gap_seconds
            FROM convergence_tests
            ORDER BY id DESC
            LIMIT 1
            """
        )

        latest_convergence = cursor.fetchone()

    if latest_convergence is None:

        convergence = None

    else:

        convergence = dict(
            latest_convergence
        )

    return {
        "interfaces": {
            "total": len(interfaces),
            "up": interface_up,
            "down": interface_down
        },

        "bgp": {
            "total": len(bgp_neighbors),
            "up": bgp_up,
            "down": bgp_down
        },

        "routes": {
            "total": len(routes),
            "up": route_up,
            "degraded": route_degraded,
            "down": route_down
        },

        "incidents": {
            "open": open_incidents,
            "average_recovery_seconds":
                average_recovery
        },

        "latest_convergence":
            convergence
    }
