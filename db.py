import mysql.connector
from mysql.connector import Error, errorcode
from config_loader import Config


# ─────────────────────────────────────────────
# Connexion
# ─────────────────────────────────────────────

def get_connection(cfg: Config):
    try:
        conn = mysql.connector.connect(
            host               = cfg.db_host,
            port               = cfg.db_port,
            user               = cfg.db_user,
            password           = cfg.db_password,
            database           = cfg.db_name,
            connection_timeout = 5,
        )
        return conn
    except Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            raise SystemExit("Erreur d'authentification. Vérifie user/password dans config.xml.") from err
        if err.errno == errorcode.ER_BAD_DB_ERROR:
            raise SystemExit(f"La base '{cfg.db_name}' n'existe pas. Vérifie db_name dans config.xml.") from err
        raise SystemExit(f"Connexion échouée : {err}") from err


# ─────────────────────────────────────────────
# Trajets
# ─────────────────────────────────────────────

def start_trajet(cfg: Config) -> int:
    conn   = get_connection(cfg)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO trajets (id_conducteur, debut_log) VALUES (%s, NOW())",
            (cfg.id_conducteur,)
        )
        conn.commit()
        trajet_id = cursor.lastrowid
    finally:
        cursor.close()
        conn.close()
    print(f"🚗 Trajet démarré (id_trajet = {trajet_id})")
    return trajet_id


def end_trajet(cfg: Config, id_trajet: int) -> None:
    conn   = get_connection(cfg)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE trajets SET fin_log = NOW() WHERE id_trajet = %s",
            (id_trajet,)
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    print(f"🏁 Trajet {id_trajet} terminé !")


# ─────────────────────────────────────────────
# Mesures
# ─────────────────────────────────────────────

def insert_mesure(
    cfg:              Config,
    id_trajet:        int,
    temps_ms:         int,
    ouverture_oeil:   float,
    alerte_visuelle:  int,
    rythme_cardiaque: int = 0,
    alerte_sonore:    int = 0,
    angle_volant:     float = 0.0,
) -> None:
    conn   = get_connection(cfg)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO mesures
                (id_trajet, temps_ms, ouverture_oeil,
                 rythme_cardiaque, alerte_visuelle, alerte_sonore, angle_volant)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                id_trajet,
                int(temps_ms),
                float(ouverture_oeil),
                int(rythme_cardiaque),
                int(alerte_visuelle),
                int(alerte_sonore),
                float(angle_volant),
            ),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()
