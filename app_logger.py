"""
app_logger.py
-------------
Configuration centralisee du logging pour tout le projet.

Format des lignes : HH:MM:SS NIVEAU [module] message
Sorties :
  - console (niveau configurable)
  - fichier de debug "debug.log" reecrase a chaque lancement (toujours en DEBUG)

Usage :
    from app_logger import setup_logging, get_logger
    setup_logging("INFO")          # a appeler une seule fois au demarrage
    log = get_logger(__name__)     # dans chaque module
    log.info("message")
"""

import logging
import os

_DATE_FORMAT = "%H:%M:%S"
_LINE_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"

# Fichier de log unique, reecrase a chaque lancement (debug).
LOG_FILE = os.path.join(os.path.dirname(__file__), "debug.log")

_configured = False


def setup_logging(level: str = "INFO") -> None:
    """Configure le logger racine (console + fichier). Idempotent.

    level : "DEBUG", "INFO", "WARNING", "ERROR" (insensible a la casse).

    La console respecte `level`. Le fichier `debug.log` capture TOUJOURS en
    DEBUG et est reecrase a chaque lancement (mode 'w').
    """
    global _configured

    numeric_level = getattr(logging, str(level).upper(), logging.INFO)

    root = logging.getLogger()
    # Le root doit laisser passer le niveau le plus bas (DEBUG) pour que le
    # fichier puisse tout enregistrer, meme si la console est en INFO.
    root.setLevel(logging.DEBUG)

    # Evite d'empiler plusieurs handlers si appele plusieurs fois.
    for handler in list(root.handlers):
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    formatter = logging.Formatter(_LINE_FORMAT, datefmt=_DATE_FORMAT)

    # Console : niveau configurable.
    console = logging.StreamHandler()
    console.setLevel(numeric_level)
    console.setFormatter(formatter)
    root.addHandler(console)

    # Fichier de debug : reecrase a chaque lancement, toujours en DEBUG.
    try:
        file_handler = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except Exception as e:
        root.warning("Impossible de creer le fichier de log %s : %s", LOG_FILE, e)

    _configured = True



def get_logger(name: str) -> logging.Logger:
    """Retourne un logger nomme. Le nom est generalement __name__.

    On raccourcit "__main__" en "main" pour un affichage plus propre.
    """
    if name == "__main__":
        name = "main"
    return logging.getLogger(name)
