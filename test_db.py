import os
import sys

import mysql.connector
from mysql.connector import Error


def get_connection():
    """Create and return a MariaDB connection using environment variables."""
    host = os.environ.get("DB_HOST", "localhost")
    try:
        port = int(os.environ.get("DB_PORT", 3306))
    except ValueError:
        print("❌ Erreur : DB_PORT doit être un entier valide.")
        sys.exit(1)
    user = os.environ.get("DB_USER")
    password = os.environ.get("DB_PASSWORD")

    if not user or not password:
        print("❌ Erreur : les variables d'environnement DB_USER et DB_PASSWORD doivent être définies.")
        sys.exit(1)

    try:
        connection = mysql.connector.connect(
            host=host,
            port=port,
            user=user,
            password=password,
        )
        return connection
    except Error as e:
        print(f"❌ Erreur de connexion à MariaDB : {e}")
        sys.exit(1)


def test_connection():
    """Test the database connection and print server information."""
    connection = get_connection()
    try:
        if connection.is_connected():
            info = connection.get_server_info()
            print(f"✅ Connecté à MariaDB (version {info})")

            cursor = connection.cursor()
            cursor.execute("SELECT DATABASE();")
            current_db = cursor.fetchone()
            print(f"   Base de données courante : {current_db[0]}")

            cursor.execute("SHOW DATABASES;")
            databases = cursor.fetchall()
            print("   Bases de données disponibles :")
            for (db_name,) in databases:
                print(f"     - {db_name}")

            cursor.close()
    finally:
        connection.close()
        print("🔒 Connexion fermée.")


if __name__ == "__main__":
    test_connection()
