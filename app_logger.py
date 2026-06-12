"""
app_logger.py
-------------
Configuration centralisee du logging pour tout le projet.

Format des lignes : HH:MM:SS NIVEAU [module] message
Sortie : console uniquement.

Usage :
    from app_logger import setup_logging, get_logger
    setup_logging("INFO")          # a appeler une seule fois au demarrage
    log = get_logger(__name__)     # dans chaque module
    log.info("message")
"""

import logging

_DATE_FORMAT = "%H:%M:%S"
_LINE_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"

_configured = False


def setup_logging(level: str = "INFO") -> None:
    """Configure le logger racine (console). Idempotent.

    level : "DEBUG", "INFO", "WARNING", "ERROR" (insensible a la casse).
    """
    global _configured

    numeric_level = getattr(logging, str(level).upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Evite d'empiler plusieurs handlers si appele plusieurs fois.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler()
    handler.setLevel(numeric_level)
    handler.setFormatter(logging.Formatter(_LINE_FORMAT, datefmt=_DATE_FORMAT))
    root.addHandler(handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Retourne un logger nomme. Le nom est generalement __name__.

    On raccourcit "__main__" en "main" pour un affichage plus propre.
    """
    if name == "__main__":
        name = "main"
    return logging.getLogger(name)
