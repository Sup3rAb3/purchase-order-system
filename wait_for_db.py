import time
import psycopg2
import os

db = os.environ.get("DB_NAME")
user = os.environ.get("DB_USER")
password = os.environ.get("DB_PASSWORD")
host = os.environ.get("DB_HOST")
port = os.environ.get("DB_PORT", 5432)

for i in range(30):
    try:
        conn = psycopg2.connect(
            dbname=db, user=user, password=password, host=host, port=port
        )
        conn.close()
        print("Database is ready!")
        break
    except psycopg2.OperationalError:
        print(f"Database not ready, retrying {i+1}/30...")
        time.sleep(3)
else:
    raise Exception("Database not available after 90 seconds")
# This script checks for the availability of the PostgreSQL database before starting the application.