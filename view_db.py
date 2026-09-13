import sqlite3


connection = sqlite3.connect("network.db")
cursor = connection.cursor()

print("\nMonitoring Results: ")
print("-" * 90)

cursor.execute("""
    SELECT id, timestamp, hostname, ip, status, latency, packet_loss
    FROM monitoring_results
    ORDER BY id DESC
    LIMIT 20
""")

rows = cursor.fetchall()

for row in rows:
    print(row)
    
print("\nIncidents: ")
print("-" * 90)

cursor.execute("""
    SELECT id, timestamp, hostname, ip, previous_status, new_status
    FROM incidents
    ORDER BY id DESC
""")

incidents = cursor.fetchall()

for incident in incidents:
    print(incident)

print("\nService Results: ")
print("-" * 90)

cursor.execute("""
    SELECT id, timestamp, hostname, ip, service_name, port, status, connect_time, error
    FROM service_results
    ORDER BY id DESC
    LIMIT 20
""")

for row in cursor.fetchall():
    print(row)

print("\nService Incidents: ")
print("-" * 90)

cursor.execute("""
    SELECT id, timestamp, hostname, ip, service_name, port, previous_status, new_status
    FROM service_incidents
    ORDER BY id DESC
""")

for row in cursor.fetchall():
    print(row)

print("\nHTTP Results: ")
print("-" * 90)

cursor.execute("""
    SELECT id, timestamp, hostname, ip, service_name, port, path, expected_status, actual_status, status, response_time, error
    FROM http_results
    ORDER BY id DESC
    LIMIT 20
""")

for row in cursor.fetchall():
    print(row)

print("\nBGP Results: ")
print("-" * 90)

cursor.execute(
    """
    SELECT
        id,
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
    FROM bgp_results
    ORDER BY id DESC
    LIMIT 20
    """
)

for row in cursor.fetchall():
    print(row)


print("\nBGP Incidents: ")
print("-" * 90)

cursor.execute(
    """
    SELECT
        id,
        timestamp,
        hostname,
        neighbor_ip,
        previous_state,
        new_state
    FROM bgp_incidents
    ORDER BY id DESC
    LIMIT 20
    """
)

for row in cursor.fetchall():
    print(row)

connection.close()