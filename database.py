import os
import mysql.connector

def get_db_connection():
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", "Charitha@18"),
        database=os.environ.get("DB_NAME", "home_budget"),
        port=int(os.environ.get("DB_PORT", "3306"))
    )
