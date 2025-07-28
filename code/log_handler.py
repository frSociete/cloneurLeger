import logging
import sys

# Chemin du fichier log
log_file = "/var/log/disk_erase.log"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger()
logger.setLevel(logging.INFO)

try:
    log_handler = logging.FileHandler(log_file)
    log_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(message)s')
    log_handler.setFormatter(formatter)
    logger.addHandler(log_handler)
except PermissionError:
    print("Erreur : Permission refusée. Merci de lancer le script avec sudo.", file=sys.stderr)
    sys.exit(1)

def log_info(message: str) -> None:
    logger.info(message)

def log_error(message: str) -> None:
    logger.error(message)

def log_warning(message: str) -> None:
    logger.warning(message)
