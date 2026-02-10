"""simulate_db.py — Génère des données simulées pour les tables Conducteurs,
Trajets et Mesures, puis les insère dans la base MariaDB.

Deux modes d'exécution :
  • python simulate_db.py live     — simulation temps‑réel 1 Hz (1 mesure/s),
                                      flush vers la DB toutes les 10 s.
  • python simulate_db.py batch    — génère un trajet complet d'un coup
                                      (rapide, pas de délai).
  • python simulate_db.py          — affiche l'aide.

Les variables d'environnement DB_HOST, DB_PORT, DB_USER, DB_PASSWORD et
DB_NAME doivent être définies (cf. .env.example).
"""

import math
import os
import random
import sys
import time
from datetime import date, datetime, timedelta

import mysql.connector
from mysql.connector import Error


# ---------------------------------------------------------------------------
# Connexion (reprise de test_db.py)
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
        print("❌ Erreur : DB_USER et DB_PASSWORD doivent être définies.")
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
        print(f"❌ Erreur de connexion : {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Création des tables (si elles n'existent pas)
# ---------------------------------------------------------------------------

CREATE_CONDUCTEURS = """
CREATE TABLE IF NOT EXISTS Conducteurs (
    id_conducteur INT AUTO_INCREMENT PRIMARY KEY,
    nom           VARCHAR(100) NOT NULL,
    prenom        VARCHAR(100),
    date_naissance DATE
);
"""

CREATE_TRAJETS = """
CREATE TABLE IF NOT EXISTS Trajets (
    id_trajet      INT AUTO_INCREMENT PRIMARY KEY,
    id_conducteur  INT NOT NULL,
    debut_log      DATETIME NOT NULL,
    fin_log        DATETIME,
    commentaire    TEXT,
    FOREIGN KEY (id_conducteur) REFERENCES Conducteurs(id_conducteur)
);
"""

CREATE_MESURES = """
CREATE TABLE IF NOT EXISTS Mesures (
    id_mesure         INT AUTO_INCREMENT PRIMARY KEY,
    id_trajet         INT NOT NULL,
    temps_ms          INT NOT NULL,
    ouverture_oeil    FLOAT NOT NULL,
    rythme_cardiaque  INT NOT NULL,
    alerte_visuelle   BOOLEAN NOT NULL DEFAULT 0,
    alerte_sonore     BOOLEAN NOT NULL DEFAULT 0,
    angle_volant      FLOAT,
    force_volant      FLOAT,
    FOREIGN KEY (id_trajet) REFERENCES Trajets(id_trajet)
);
"""

# Migration: add the two steering-wheel sensor columns if the table
# already exists but was created before these columns were defined.
ALTER_MESURES_ANGLE = (
    "ALTER TABLE Mesures ADD COLUMN angle_volant FLOAT AFTER alerte_sonore;"
)
ALTER_MESURES_FORCE = (
    "ALTER TABLE Mesures ADD COLUMN force_volant FLOAT AFTER angle_volant;"
)


def ensure_tables():
    """Create the three tables if they don't already exist.

    Also runs ALTER TABLE migrations to add steering-wheel sensor columns
    (angle_volant, force_volant) on databases created before this update.
    """
    connection = get_connection()
    try:
        cursor = connection.cursor()
        for ddl in (CREATE_CONDUCTEURS, CREATE_TRAJETS, CREATE_MESURES):
            cursor.execute(ddl)
        # Migration: add new columns if missing (idempotent).
        for alter in (ALTER_MESURES_ANGLE, ALTER_MESURES_FORCE):
            try:
                cursor.execute(alter)
            except Error as e:
                # MySQL/MariaDB error 1060 = "Duplicate column name"
                if e.errno == 1060:
                    pass  # column already exists — expected
                else:
                    raise
        connection.commit()
        cursor.close()
        print("✅ Tables vérifiées / créées.")
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Insertion helpers
# ---------------------------------------------------------------------------

def insert_conducteur(nom, prenom=None, date_naissance=None):
    """Insert a driver and return the new id_conducteur."""
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO Conducteurs (nom, prenom, date_naissance) "
            "VALUES (%s, %s, %s);",
            (nom, prenom, date_naissance),
        )
        connection.commit()
        cid = cursor.lastrowid
        cursor.close()
        return cid
    finally:
        connection.close()


def insert_trajet(id_conducteur, debut_log, fin_log=None, commentaire=None):
    """Insert a trip and return the new id_trajet."""
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO Trajets (id_conducteur, debut_log, fin_log, commentaire) "
            "VALUES (%s, %s, %s, %s);",
            (id_conducteur, debut_log, fin_log, commentaire),
        )
        connection.commit()
        tid = cursor.lastrowid
        cursor.close()
        return tid
    finally:
        connection.close()


def update_trajet_fin(id_trajet, fin_log, commentaire=None):
    """Set fin_log (and optional commentaire) on an existing trip."""
    connection = get_connection()
    try:
        cursor = connection.cursor()
        if commentaire is not None:
            cursor.execute(
                "UPDATE Trajets SET fin_log = %s, commentaire = %s "
                "WHERE id_trajet = %s;",
                (fin_log, commentaire, id_trajet),
            )
        else:
            cursor.execute(
                "UPDATE Trajets SET fin_log = %s WHERE id_trajet = %s;",
                (fin_log, id_trajet),
            )
        connection.commit()
        cursor.close()
    finally:
        connection.close()


def bulk_insert_mesures(rows):
    """Insert many measurement rows at once.

    *rows* is a list of tuples:
        (id_trajet, temps_ms, ouverture_oeil, rythme_cardiaque,
         alerte_visuelle, alerte_sonore, angle_volant, force_volant)
    """
    if not rows:
        return
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.executemany(
            "INSERT INTO Mesures "
            "(id_trajet, temps_ms, ouverture_oeil, rythme_cardiaque, "
            " alerte_visuelle, alerte_sonore, angle_volant, force_volant) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s);",
            rows,
        )
        connection.commit()
        cursor.close()
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Simulation de données réalistes
# ---------------------------------------------------------------------------

# Seuils cohérents avec CamLive.py
CLOSED_EYE_THRESHOLD = 15.0   # % en‑dessous = yeux fermés
ALERT_DURATION_S = 2           # secondes yeux fermés avant alerte


def generate_measurement(t_ms, state):
    """Return a single simulated measurement tuple and update *state* in‑place.

    *state* is a dict carrying inter‑sample state (drowsiness timer, etc.).

    Returns:
        (temps_ms, ouverture_oeil, rythme_cardiaque,
         alerte_visuelle, alerte_sonore, angle_volant, force_volant)
    """
    # --- Eye openness ---
    # Base: normal driving ≈ 70‑95 %
    # Occasionally simulate drowsiness episodes (eyes closing)
    if state.get("drowsy_remaining", 0) > 0:
        # During a drowsiness episode, eyes close progressively
        progress = state["drowsy_remaining"] / state["drowsy_total"]
        ouverture = max(0.0, 10.0 * progress + random.gauss(0, 2))
        state["drowsy_remaining"] -= 1
    else:
        # Normal: 70‑95 % with small noise
        ouverture = random.gauss(82, 6)
        ouverture = max(0.0, min(100.0, ouverture))

        # Random chance of starting a drowsiness episode
        if random.random() < 0.02:  # ~2 % chance per second
            duration = random.randint(2, 8)  # seconds
            state["drowsy_remaining"] = duration
            state["drowsy_total"] = duration

    ouverture = round(ouverture, 1)

    # --- Heart rate ---
    base_hr = state.get("base_hr", random.randint(65, 80))
    state["base_hr"] = base_hr
    # Slight sinusoidal variation + noise
    hr = base_hr + 5 * math.sin(t_ms / 30000.0) + random.gauss(0, 2)
    rythme_cardiaque = max(50, min(130, int(round(hr))))

    # --- Alerts ---
    if ouverture < CLOSED_EYE_THRESHOLD:
        state["closed_seconds"] = state.get("closed_seconds", 0) + 1
    else:
        state["closed_seconds"] = 0

    eyes_closed_long = state["closed_seconds"] >= ALERT_DURATION_S
    alerte_visuelle = 1 if eyes_closed_long else 0
    alerte_sonore = 1 if eyes_closed_long else 0

    # --- Steering wheel angle (potentiometer) ---
    # Simulates normal driving: smooth turns with slow sinusoidal drift
    # (-540 to +540 degree range for a real wheel, but typical driving
    # stays within +/-90 degrees).  Drowsiness -> drift increases.
    base_angle = 15.0 * math.sin(t_ms / 8000.0) + 8.0 * math.sin(t_ms / 20000.0)
    if state.get("drowsy_remaining", 0) > 0:
        # Drowsy: steering drifts more
        base_angle += random.gauss(0, 12)
    else:
        base_angle += random.gauss(0, 3)
    angle_volant = round(max(-540.0, min(540.0, base_angle)), 1)

    # --- Steering wheel grip force (strain gauge / Wheatstone bridge) ---
    # Expressed in Newtons.  Normal grip ≈ 10‑30 N.
    # Drowsiness → grip loosens (force drops).
    if state.get("drowsy_remaining", 0) > 0:
        force = random.gauss(5, 3)   # weak grip during drowsiness
    else:
        force = random.gauss(20, 4)  # normal grip
    force_volant = round(max(0.0, min(80.0, force)), 1)

    return (t_ms, ouverture, rythme_cardiaque, alerte_visuelle, alerte_sonore,
            angle_volant, force_volant)


# ---------------------------------------------------------------------------
# Mode batch — génère un trajet complet d'un coup
# ---------------------------------------------------------------------------

def _random_birth_date():
    """Return a random valid date between 1970 and 2000."""
    start = date(1970, 1, 1)
    end = date(2000, 12, 31)
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def run_batch(duration_s=120):
    """Generate a full simulated trip and insert everything at once."""
    ensure_tables()

    # Conducteur
    noms = ["Dupont", "Martin", "Bernard", "Durand", "Leroy"]
    prenoms = ["Jean", "Marie", "Pierre", "Sophie", "Luc"]
    nom = random.choice(noms)
    prenom = random.choice(prenoms)
    date_naiss = _random_birth_date()
    cid = insert_conducteur(nom, prenom, date_naiss)
    print(f"👤 Conducteur créé : {prenom} {nom} (id={cid})")

    # Trajet
    debut = datetime.now() - timedelta(seconds=duration_s)
    fin = datetime.now()
    tid = insert_trajet(cid, debut, fin, f"Trajet simulé ({duration_s}s)")
    print(f"🚗 Trajet créé : id={tid}  ({debut} → {fin})")

    # Mesures — 1 par seconde
    state = {}
    mesures = []
    for s in range(duration_s):
        t_ms = s * 1000
        row = generate_measurement(t_ms, state)
        mesures.append((tid, *row))

    bulk_insert_mesures(mesures)
    print(f"📊 {len(mesures)} mesures insérées (1 Hz, {duration_s}s).")

    _print_summary(mesures)


def _print_summary(mesures):
    """Print a short statistical summary of the generated measurements.

    Each element of *mesures* is a tuple:
        (id_trajet, temps_ms, ouverture_oeil, rythme_cardiaque,
         alerte_visuelle, alerte_sonore, angle_volant, force_volant)
    """
    ouvertures = [m[2] for m in mesures]  # index 2 = ouverture_oeil
    hrs = [m[3] for m in mesures]         # index 3 = rythme_cardiaque
    alertes = sum(1 for m in mesures if m[4])  # index 4 = alerte_visuelle
    angles = [m[6] for m in mesures]      # index 6 = angle_volant
    forces = [m[7] for m in mesures]      # index 7 = force_volant

    print(f"\n📈 Résumé :")
    print(f"   Ouverture yeux  — min: {min(ouvertures):.1f}%  "
          f"max: {max(ouvertures):.1f}%  moy: {sum(ouvertures)/len(ouvertures):.1f}%")
    print(f"   Rythme cardiaque — min: {min(hrs)} bpm  "
          f"max: {max(hrs)} bpm  moy: {sum(hrs)/len(hrs):.0f} bpm")
    print(f"   Angle volant    — min: {min(angles):.1f}°  "
          f"max: {max(angles):.1f}°  moy: {sum(angles)/len(angles):.1f}°")
    print(f"   Force volant    — min: {min(forces):.1f} N  "
          f"max: {max(forces):.1f} N  moy: {sum(forces)/len(forces):.1f} N")
    print(f"   Alertes déclenchées : {alertes} mesure(s)")


# ---------------------------------------------------------------------------
# Mode live — simulation temps‑réel 1 Hz avec flush toutes les 10 s
# ---------------------------------------------------------------------------

FLUSH_INTERVAL_S = 10  # enregistrement vers la DB distante toutes les 10 s


def run_live(duration_s=60):
    """Simulate measurements in real‑time at 1 Hz.

    Measurements are buffered locally and flushed to the database every
    FLUSH_INTERVAL_S seconds (10 s by default), as specified in the
    functional requirements (historical recording).
    """
    ensure_tables()

    # Conducteur
    noms = ["Dupont", "Martin", "Bernard", "Durand", "Leroy"]
    prenoms = ["Jean", "Marie", "Pierre", "Sophie", "Luc"]
    nom = random.choice(noms)
    prenom = random.choice(prenoms)
    date_naiss = _random_birth_date()
    cid = insert_conducteur(nom, prenom, date_naiss)
    print(f"👤 Conducteur : {prenom} {nom} (id={cid})")

    # Trajet (fin_log sera mis à jour à la fin)
    debut = datetime.now()
    tid = insert_trajet(cid, debut, commentaire="Trajet live en cours…")
    print(f"🚗 Trajet démarré : id={tid}  ({debut})")
    print(f"⏱️  Durée prévue : {duration_s}s  |  Fréquence : 1 Hz  "
          f"|  Flush DB : toutes les {FLUSH_INTERVAL_S}s")
    print(f"   (Ctrl+C pour arrêter)\n")

    state = {}
    buffer = []
    all_mesures = []
    total_inserted = 0

    try:
        for s in range(duration_s):
            t_ms = s * 1000
            row = generate_measurement(t_ms, state)
            buffer.append((tid, *row))
            all_mesures.append((tid, *row))

            # Terminal feedback
            _, _, ouv, hr, av, aso, ang, frc = (tid, *row)
            alert_flag = " 🚨 ALERTE" if av else ""
            print(f"   t={s:>4}s  |  👁️  {ouv:>5.1f}%  |  ❤️  {hr:>3} bpm  "
                  f"|  🔄 {ang:>6.1f}°  |  ✊ {frc:>4.1f} N{alert_flag}")

            # Flush every FLUSH_INTERVAL_S seconds
            if (s + 1) % FLUSH_INTERVAL_S == 0:
                bulk_insert_mesures(buffer)
                total_inserted += len(buffer)
                print(f"   ➡️  Flush : {len(buffer)} mesures envoyées "
                      f"(total: {total_inserted})")
                buffer = []

            time.sleep(1)

    except KeyboardInterrupt:
        print("\n⚠️  Interruption par l'utilisateur.")

    # Flush remaining buffer
    if buffer:
        bulk_insert_mesures(buffer)
        total_inserted += len(buffer)
        print(f"   ➡️  Flush final : {len(buffer)} mesures envoyées "
              f"(total: {total_inserted})")

    # Close the trip
    fin = datetime.now()
    update_trajet_fin(tid, fin, f"Trajet live terminé — {total_inserted} mesures")
    print(f"\n🏁 Trajet terminé : {debut} → {fin}")
    print(f"   {total_inserted} mesures insérées au total.")

    if all_mesures:
        _print_summary(all_mesures)


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("Utilisation :")
        print("  python simulate_db.py batch [durée_s]")
        print("  python simulate_db.py live  [durée_s]")
        return

    cmd = sys.argv[1]
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else None

    if cmd == "batch":
        run_batch(duration or 120)
    elif cmd == "live":
        run_live(duration or 60)
    else:
        print(f"Commande inconnue : {cmd}")
        print("Commandes : batch, live")


if __name__ == "__main__":
    main()
