import subprocess
import sys
import re
import time
from log_handler import log_error, log_info, log_warning
from pathlib import Path

def run_command(command_list: list[str], raise_on_error: bool = True) -> str:
    try:
        result = subprocess.run(command_list, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.stdout.decode('utf-8').strip()
    except FileNotFoundError:
        log_error(f"Erreur : Commande introuvable : {' '.join(command_list)}")
        if raise_on_error:
            sys.exit(2)
        else:
            raise
    except subprocess.CalledProcessError:
        log_error(f"Erreur : L’exécution de la commande a échoué : {' '.join(command_list)}")
        if raise_on_error:
            sys.exit(1)
        else:
            raise
    except KeyboardInterrupt:
        log_error("Opération interrompue par l’utilisateur (Ctrl+C)")
        print("\nOpération interrompue par l’utilisateur (Ctrl+C)")
        sys.exit(130)

def run_command_with_progress(command_list: list[str], progress_callback=None, stop_flag=None) -> str:
    """Exécute une commande avec suivi de la progression et possibilité d'annulation"""
    try:
        process = subprocess.Popen(command_list, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        while process.poll() is None:
            if stop_flag and stop_flag():
                process.terminate()
                process.wait()
                raise KeyboardInterrupt("Opération annulée par l’utilisateur")
            if progress_callback:
                progress_callback()
            time.sleep(1)
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, command_list, stdout, stderr)
        return stdout.strip()
    except FileNotFoundError:
        log_error(f"Erreur : Commande introuvable : {' '.join(command_list)}")
        raise
    except subprocess.CalledProcessError as e:
        log_error(f"Erreur : L’exécution de la commande a échoué : {' '.join(command_list)}")
        if e.stderr:
            log_error(f"Sortie d’erreur : {e.stderr}")
        raise
    except KeyboardInterrupt:
        log_error("Opération interrompue par l’utilisateur")
        raise

def get_disk_list() -> list[dict]:
    """Retourne une liste des disques disponibles sous forme de dictionnaire."""
    try:
        output = run_command(["lsblk", "-d", "-o", "NAME,SIZE,TYPE,MODEL", "-n"])
        if not output:
            output = run_command(["lsblk", "-d", "-o", "NAME", "-n"])
        if not output:
            log_info("Aucun disque détecté. Vérifiez que le programme est lancé avec les droits appropriés.")
            return []
        disks = []
        for line in output.strip().split('\n'):
            if not line.strip():
                continue
            parts = line.strip().split(maxsplit=3)
            device = parts[0]
            if len(parts) >= 2:
                size = parts[1]
                model = parts[3] if len(parts) > 3 else "Inconnu"
                disks.append({
                    "device": f"/dev/{device}",
                    "size": size,
                    "model": model
                })
        return disks
    except FileNotFoundError as e:
        log_error(f"Erreur : Commande introuvable : {str(e)}")
        return []
    except subprocess.CalledProcessError as e:
        log_error(f"Erreur lors de l’exécution de la commande : {str(e)}")
        return []
    except (IndexError, ValueError) as e:
        log_error(f"Erreur lors de l’analyse des informations du disque : {str(e)}")
        return []
    except KeyboardInterrupt:
        log_error("Liste des disques interrompue par l’utilisateur")
        return []

def get_base_disk(device_name: str) -> str:
    """Extrait le nom de base du disque à partir d'un nom de périphérique."""
    try:
        if 'nvme' in device_name:
            match = re.match(r'(nvme\d+n\d+)', device_name)
            if match:
                return match.group(1)
        match = re.match(r'([a-zA-Z/]+[a-zA-Z])', device_name)
        if match:
            return match.group(1)
        return device_name
    except (re.error, AttributeError) as e:
        log_error(f"Erreur regex sur le nom du périphérique '{device_name}': {str(e)}")
        return device_name
    except TypeError:
        log_error(f"Type de nom de périphérique invalide : chaîne attendue, obtenu {type(device_name)}")
        return str(device_name) if device_name is not None else ""

def get_active_disk():
    """Détecte le(s) disque(s) actif(s) accueillant la racine système."""
    try:
        devices = set()
        live_boot_found = False
        with open('/proc/mounts', 'r') as f:
            mounts_content = f.read()
        root_device = None
        for line in mounts_content.split('\n'):
            if line.strip() and ' / ' in line:
                parts = line.split()
                if len(parts) >= 2:
                    root_device = parts[0]
                    break
        if not root_device or root_device in ['rootfs', 'overlay', 'aufs', '/dev/root']:
            with open('/proc/mounts', 'r') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 6:
                        device = parts[0]
                        mount_point = parts[1]
                        if any(keyword in mount_point for keyword in ['/run/live', '/lib/live', '/live/', '/cdrom']):
                            match = re.search(r'/dev/([a-zA-Z]+\d*[a-zA-Z]*\d*)', device)
                            if match:
                                devices.add(match.group(1))
                            live_boot_found = True
                        elif device.startswith('/dev/') and any(keyword in device for keyword in ['sd', 'nvme', 'mmc']):
                            if '/media' in mount_point or '/mnt' in mount_point or '/run' in mount_point:
                                match = re.search(r'/dev/([a-zA-Z]+\d*[a-zA-Z]*\d*)', device)
                                if match:
                                    devices.add(match.group(1))
            if not devices:
                try:
                    output = run_command(["df", "-h"])
                    lines = output.strip().split('\n')
                    for line in lines[1:]:
                        parts = line.split()
                        if len(parts) >= 6:
                            device = parts[0]
                            mount_point = parts[5]
                            if device.startswith('/dev/') and any(keyword in device for keyword in ['sd', 'nvme', 'mmc']):
                                match = re.search(r'/dev/([a-zA-Z]+\d*[a-zA-Z]*\d*)', device)
                                if match:
                                    devices.add(match.group(1))
                except (FileNotFoundError, subprocess.CalledProcessError) as e:
                    log_error(f"Erreur lors de l’exécution de la commande df : {str(e)}")
        else:
            if '/dev/mapper/' in root_device or '/dev/dm-' in root_device:
                try:
                    output = run_command(["lsblk", "-no", "PKNAME", root_device])
                    if output:
                        parent_devices = output.strip().split('\n')
                        for parent in parent_devices:
                            if parent.strip():
                                devices.add(get_base_disk(parent.strip()))
                except (FileNotFoundError, subprocess.CalledProcessError):
                    pass
            else:
                match = re.search(r'/dev/([a-zA-Z]+\d*[a-zA-Z]*\d*)', root_device)
                if match:
                    devices.add(match.group(1))
            try:
                output = run_command(["df", "-h"])
                lines = output.strip().split('\n')
                for line in lines[1:]:
                    parts = line.split()
                    if len(parts) >= 6:
                        device = parts[0]
                        mount_point = parts[5]
                        if "/run/live" in mount_point or "/lib/live" in mount_point:
                            match = re.search(r'/dev/([a-zA-Z]+\d*[a-zA-Z]*\d*)', device)
                            if match:
                                devices.add(match.group(1))
                            live_boot_found = True
            except (FileNotFoundError, subprocess.CalledProcessError):
                pass
        if devices:
            device_list = list(devices)
            if live_boot_found:
                final_devices = [dev for dev in device_list if not dev.startswith('/dev/')]
                if final_devices:
                    return final_devices
            return device_list
        else:
            log_error("Aucun périphérique actif détecté")
            return None
    except FileNotFoundError as e:
        log_error(f"Fichier requis introuvable : {str(e)}")
        return None
    except PermissionError as e:
        log_error(f"Permission refusée pour accéder aux fichiers système : {str(e)}")
        return None
    except OSError as e:
        log_error(f"Erreur système lors de l’accès aux informations système : {str(e)}")
        return None
    except subprocess.CalledProcessError as e:
        log_error(f"Erreur lors de l’exécution de la commande : {str(e)}")
        return None
    except (IndexError, ValueError) as e:
        log_error(f"Erreur lors de l’analyse des sorties de commande : {str(e)}")
        return None
    except re.error as e:
        log_error(f"Erreur de motif regex : {str(e)}")
        return None
    except KeyboardInterrupt:
        log_error("Opération interrompue par l’utilisateur")
        return None
    except UnicodeDecodeError as e:
        log_error(f"Erreur lors du décodage du contenu du fichier : {str(e)}")
        return None
    except MemoryError:
        log_error("Mémoire insuffisante pour traiter les informations de périphérique")
        return None

def get_disk_serial(device: str) -> str:
    """Retourne un identifiant unique du disque via udevadm."""
    try:
        output = subprocess.run(
            ["udevadm", "info", "--query=property", f"--name=/dev/{device}"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        ).stdout.decode()
        wwn_match = re.search(r'ID_WWN=(\S+)', output)
        if wwn_match:
            return wwn_match.group(1)
        serial_match = re.search(r'ID_SERIAL_SHORT=(\S+)', output)
        if serial_match:
            return serial_match.group(1)
        model_match = re.search(r'ID_MODEL=(\S+)', output)
        if model_match:
            return f"{model_match.group(1)}_{device}"
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log_error(f"Erreur lors de l’interrogation de {device} : {e}")
    except KeyboardInterrupt:
        log_error("Identification disque interrompue par l’utilisateur (Ctrl+C)")
        print("\nIdentification disque interrompue par l’utilisateur (Ctrl+C)")
        sys.exit(130)
    return f"INCONNU_{device}"

def is_ssd(device: str) -> bool:
    try:
        output = subprocess.run(
            ["cat", f"/sys/block/{device}/queue/rotational"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return output.stdout.decode().strip() == "0"
    except (FileNotFoundError, subprocess.SubprocessError) as e:
        log_warning(f"Vérification SSD échouée pour {device} : {e}")
        return False
    except KeyboardInterrupt:
        log_error("Vérification SSD interrompue par l’utilisateur (Ctrl+C)")
        print("\nVérification SSD interrompue par l’utilisateur (Ctrl+C)")
        sys.exit(130)