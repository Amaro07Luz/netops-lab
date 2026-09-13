import sqlite3


DATABASE_NAME = "network.db"


def main():
    with sqlite3.connect(
        DATABASE_NAME
    ) as connection:

        cursor = connection.cursor()

        print()
        print("NETOPS INCIDENT REPORT")
        print("=" * 70)

        # --------------------------------
        # Total incidents
        # --------------------------------

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM incident_lifecycle
            """
        )

        total_incidents = cursor.fetchone()[0]

        # --------------------------------
        # Currently open incidents
        # --------------------------------

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM incident_lifecycle
            WHERE status = 'OPEN'
            """
        )

        open_incidents = cursor.fetchone()[0]

        # --------------------------------
        # Resolved incidents
        # --------------------------------

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM incident_lifecycle
            WHERE status = 'RESOLVED'
            """
        )

        resolved_incidents = cursor.fetchone()[0]

        # --------------------------------
        # Average recovery time
        # --------------------------------

        cursor.execute(
            """
            SELECT AVG(duration_seconds)
            FROM incident_lifecycle
            WHERE status = 'RESOLVED'
            """
        )

        average_duration = cursor.fetchone()[0]

        # --------------------------------
        # Longest outage
        # --------------------------------

        cursor.execute(
            """
            SELECT MAX(duration_seconds)
            FROM incident_lifecycle
            WHERE status = 'RESOLVED'
            """
        )

        longest_duration = cursor.fetchone()[0]

        # --------------------------------
        # Total downtime
        # --------------------------------

        cursor.execute(
            """
            SELECT SUM(duration_seconds)
            FROM incident_lifecycle
            WHERE status = 'RESOLVED'
            """
        )

        total_downtime = cursor.fetchone()[0]

        print(
            f"Total incidents:      "
            f"{total_incidents}"
        )

        print(
            f"Open incidents:       "
            f"{open_incidents}"
        )

        print(
            f"Resolved incidents:   "
            f"{resolved_incidents}"
        )

        if average_duration is None:
            print(
                "Average recovery time: ---"
            )
        else:
            print(
                f"Average recovery time: "
                f"{average_duration:.1f} seconds"
            )

        if longest_duration is None:
            print(
                "Longest outage:        ---"
            )
        else:
            print(
                f"Longest outage:        "
                f"{longest_duration:.1f} seconds"
            )

        if total_downtime is None:
            print(
                "Total downtime:        ---"
            )
        else:
            print(
                f"Total downtime:        "
                f"{total_downtime:.1f} seconds"
            )

        print()
        print("RECENT INCIDENTS")
        print("-" * 70)

        cursor.execute(
            """
            SELECT
                id,
                dependency_name,
                root_cause_device,
                root_cause_component,
                status,
                duration_seconds
            FROM incident_lifecycle
            ORDER BY id DESC
            LIMIT 10
            """
        )

        for row in cursor.fetchall():
            (
                incident_id,
                dependency_name,
                device,
                component,
                status,
                duration
            ) = row

            if duration is None:
                duration_display = "---"
            else:
                duration_display = (
                    f"{duration:.1f}s"
                )

            print(
                f"#{incident_id:<3} "
                f"{dependency_name:<24} "
                f"root={device}:{component:<8} "
                f"status={status:<8} "
                f"duration={duration_display}"
            )

        print("=" * 70)


if __name__ == "__main__":
    main()