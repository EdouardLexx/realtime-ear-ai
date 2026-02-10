import os
import re
import sys

import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


# ---------------------------------------------------------------------------
# Connexion
# ---------------------------------------------------------------------------

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
    database = os.environ.get("DB_NAME")

    if not user or not password:
        print("❌ Erreur : les variables d'environnement DB_USER et DB_PASSWORD doivent être définies.")
        sys.exit(1)

    try:
        connection = mysql.connector.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
        )
        return connection
    except Error as e:
        print(f"❌ Erreur de connexion à MariaDB : {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Validation des identifiants SQL
# ---------------------------------------------------------------------------

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_identifier(name):
    """Raise ValueError if *name* is not a safe SQL identifier."""
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(f"Identifiant SQL invalide : {name!r}")


def _validate_table(table_name):
    """Validate that *table_name* exists in the current database."""
    _validate_identifier(table_name)
    tables = list_tables()
    if table_name not in tables:
        raise ValueError(f"Table inconnue : {table_name!r}  (tables existantes : {tables})")


def _validate_columns(table_name, column_names):
    """Validate that every name in *column_names* is a column of *table_name*."""
    valid_cols = {row[0] for row in show_headers(table_name)}
    for col in column_names:
        _validate_identifier(col)
        if col not in valid_cols:
            raise ValueError(f"Colonne inconnue '{col}' dans la table '{table_name}'")


# ---------------------------------------------------------------------------
# Test de connexion
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Lister les tables
# ---------------------------------------------------------------------------

def list_tables():
    """List all tables in the current database."""
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("SHOW TABLES;")
        tables = [row[0] for row in cursor.fetchall()]
        cursor.close()
        return tables
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Afficher les en-têtes (noms de colonnes) d'une table
# ---------------------------------------------------------------------------

def show_headers(table_name):
    """Display column names for a given table."""
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_KEY "
            "FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s "
            "ORDER BY ORDINAL_POSITION;",
            (table_name,),
        )
        columns = cursor.fetchall()
        cursor.close()
        return columns
    finally:
        connection.close()


def show_all_headers():
    """Display column headers for every table in the database."""
    tables = list_tables()
    if not tables:
        print("⚠️  Aucune table trouvée dans la base de données.")
        return

    for table in tables:
        columns = show_headers(table)
        print(f"\n📋 Table : {table}")
        print(f"   {'Colonne':<30} {'Type':<15} {'Nullable':<10} {'Clé':<5}")
        print(f"   {'-'*30} {'-'*15} {'-'*10} {'-'*5}")
        for col_name, data_type, nullable, key in columns:
            print(f"   {col_name:<30} {data_type:<15} {nullable:<10} {key or '':<5}")


# ---------------------------------------------------------------------------
# Afficher toutes les données de toutes les tables
# ---------------------------------------------------------------------------

def show_all_data():
    """Display all rows from every table in the database (formatted)."""
    tables = list_tables()
    if not tables:
        print("⚠️  Aucune table trouvée dans la base de données.")
        return

    connection = get_connection()
    try:
        cursor = connection.cursor()
        for table in tables:
            _validate_identifier(table)
            cursor.execute(f"SELECT * FROM `{table}`;")
            rows = cursor.fetchall()
            col_names = [desc[0] for desc in cursor.description]

            print(f"\n{'='*60}")
            print(f"📊 Table : {table}  ({len(rows)} ligne(s))")
            print(f"{'='*60}")

            if not rows:
                print("   (vide)")
                continue

            # Calculate column widths
            widths = [len(str(name)) for name in col_names]
            for row in rows:
                for i, val in enumerate(row):
                    widths[i] = max(widths[i], len(str(val)))

            # Header
            header = " | ".join(str(name).ljust(widths[i]) for i, name in enumerate(col_names))
            separator = "-+-".join("-" * widths[i] for i in range(len(col_names)))
            print(f"   {header}")
            print(f"   {separator}")

            # Rows
            for row in rows:
                line = " | ".join(str(val).ljust(widths[i]) for i, val in enumerate(row))
                print(f"   {line}")

        cursor.close()
    finally:
        connection.close()
        print(f"\n🔒 Connexion fermée.")


# ---------------------------------------------------------------------------
# Fonctions CRUD
# ---------------------------------------------------------------------------

def insert_row(table_name, data):
    """Insert a row into a table.

    Args:
        table_name: Name of the table.
        data: dict mapping column names to values, e.g. {"name": "Alice", "age": 30}.
    Returns:
        The lastrowid of the inserted row.
    """
    _validate_table(table_name)
    _validate_columns(table_name, data.keys())
    connection = get_connection()
    try:
        cursor = connection.cursor()
        columns = ", ".join(f"`{col}`" for col in data.keys())
        placeholders = ", ".join(["%s"] * len(data))
        sql = f"INSERT INTO `{table_name}` ({columns}) VALUES ({placeholders});"
        cursor.execute(sql, list(data.values()))
        connection.commit()
        row_id = cursor.lastrowid
        print(f"✅ Ligne insérée dans {table_name} (id={row_id})")
        cursor.close()
        return row_id
    except Error as e:
        print(f"❌ Erreur INSERT : {e}")
        return None
    finally:
        connection.close()


def read_rows(table_name, where_clause=None, params=None):
    """Read rows from a table.

    Args:
        table_name: Name of the table.
        where_clause: Optional WHERE clause without the WHERE keyword,
                      e.g. "id = %s".  Only column identifiers and
                      ``%s`` placeholders are allowed.
        params: Tuple of parameters for the where_clause.
    Returns:
        A tuple (column_names, rows).
    """
    _validate_table(table_name)
    connection = get_connection()
    try:
        cursor = connection.cursor()
        sql = f"SELECT * FROM `{table_name}`"
        if where_clause:
            sql += f" WHERE {where_clause}"
        cursor.execute(sql, params or ())
        rows = cursor.fetchall()
        col_names = [desc[0] for desc in cursor.description]
        cursor.close()
        return col_names, rows
    finally:
        connection.close()


def update_row(table_name, data, where_clause, params):
    """Update rows in a table.

    Args:
        table_name: Name of the table.
        data: dict of columns to update, e.g. {"name": "Bob"}.
        where_clause: WHERE clause without the WHERE keyword, e.g. "id = %s".
        params: Tuple of parameters for the where_clause.
    Returns:
        Number of rows affected.
    """
    _validate_table(table_name)
    _validate_columns(table_name, data.keys())
    connection = get_connection()
    try:
        cursor = connection.cursor()
        set_clause = ", ".join(f"`{col}` = %s" for col in data.keys())
        sql = f"UPDATE `{table_name}` SET {set_clause} WHERE {where_clause};"
        cursor.execute(sql, list(data.values()) + list(params))
        connection.commit()
        affected = cursor.rowcount
        print(f"✅ {affected} ligne(s) mise(s) à jour dans {table_name}")
        cursor.close()
        return affected
    except Error as e:
        print(f"❌ Erreur UPDATE : {e}")
        return 0
    finally:
        connection.close()


def delete_row(table_name, where_clause, params):
    """Delete rows from a table.

    Args:
        table_name: Name of the table.
        where_clause: WHERE clause without the WHERE keyword, e.g. "id = %s".
        params: Tuple of parameters for the where_clause.
    Returns:
        Number of rows affected.
    """
    _validate_table(table_name)
    connection = get_connection()
    try:
        cursor = connection.cursor()
        sql = f"DELETE FROM `{table_name}` WHERE {where_clause};"
        cursor.execute(sql, list(params))
        connection.commit()
        affected = cursor.rowcount
        print(f"✅ {affected} ligne(s) supprimée(s) dans {table_name}")
        cursor.close()
        return affected
    except Error as e:
        print(f"❌ Erreur DELETE : {e}")
        return 0
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Menu interactif
# ---------------------------------------------------------------------------

def interactive_menu():
    """Simple interactive menu to exercise all functions."""
    actions = {
        "1": ("Tester la connexion", test_connection),
        "2": ("Lister les tables", lambda: print(list_tables())),
        "3": ("Afficher les en-têtes de toutes les tables", show_all_headers),
        "4": ("Afficher toutes les données", show_all_data),
        "5": ("Lire les lignes d'une table", _menu_read),
        "6": ("Insérer une ligne", _menu_insert),
        "7": ("Modifier une ligne", _menu_update),
        "8": ("Supprimer une ligne", _menu_delete),
        "0": ("Quitter", None),
    }

    while True:
        print("\n" + "=" * 40)
        print("       MENU — Base de données MariaDB")
        print("=" * 40)
        for key, (label, _) in actions.items():
            print(f"  {key}. {label}")
        choice = input("\nChoix : ").strip()

        if choice == "0":
            print("👋 Au revoir !")
            break
        elif choice in actions:
            actions[choice][1]()
        else:
            print("❌ Choix invalide.")


def _menu_read():
    table = input("Nom de la table : ").strip()
    col_names, rows = read_rows(table)
    if not rows:
        print("   (aucune donnée)")
        return
    widths = [len(str(n)) for n in col_names]
    for row in rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(str(val)))
    header = " | ".join(str(n).ljust(widths[i]) for i, n in enumerate(col_names))
    sep = "-+-".join("-" * widths[i] for i in range(len(col_names)))
    print(f"   {header}")
    print(f"   {sep}")
    for row in rows:
        print("   " + " | ".join(str(v).ljust(widths[i]) for i, v in enumerate(row)))


def _menu_insert():
    table = input("Nom de la table : ").strip()
    columns = show_headers(table)
    data = {}
    print("Entrez les valeurs (laisser vide pour ignorer) :")
    for col_name, data_type, _, _ in columns:
        val = input(f"  {col_name} ({data_type}) : ").strip()
        if val:
            data[col_name] = val
    if data:
        insert_row(table, data)
    else:
        print("⚠️  Aucune donnée saisie, insertion annulée.")


def _menu_update():
    table = input("Nom de la table : ").strip()
    where = input("Condition WHERE (ex: id = %s) : ").strip()
    param = input("Valeur du paramètre WHERE : ").strip()
    columns = show_headers(table)
    data = {}
    print("Nouvelles valeurs (laisser vide pour ne pas modifier) :")
    for col_name, data_type, _, _ in columns:
        val = input(f"  {col_name} ({data_type}) : ").strip()
        if val:
            data[col_name] = val
    if data:
        update_row(table, data, where, (param,))
    else:
        print("⚠️  Aucune donnée saisie, mise à jour annulée.")


def _menu_delete():
    table = input("Nom de la table : ").strip()
    where = input("Condition WHERE (ex: id = %s) : ").strip()
    param = input("Valeur du paramètre WHERE : ").strip()
    delete_row(table, where, (param,))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "test":
            test_connection()
        elif cmd == "tables":
            tables = list_tables()
            print("Tables :", tables)
        elif cmd == "headers":
            show_all_headers()
        elif cmd == "data":
            show_all_data()
        else:
            print(f"Commande inconnue : {cmd}")
            print("Commandes : test, tables, headers, data  (ou sans argument pour le menu)")
    else:
        interactive_menu()
