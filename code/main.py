#!/usr/bin/env python3

import os
import sys
import time
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Dict, List, Set
from subprocess import CalledProcessError, TimeoutExpired

from utils import get_disk_list, get_base_disk, get_active_disk, get_disk_serial, is_ssd, run_command, run_command_with_progress
from log_handler import log_info, log_error

class DiskClonerGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Clonage Disque Sécurisé")
        self.root.geometry("800x600")
        self.root.attributes("-fullscreen", True)

        self.source_disk_var = tk.StringVar()
        self.dest_disk_var = tk.StringVar()
        self.clone_method_var = tk.StringVar(value="full")
        self.verify_clone_var = tk.BooleanVar(value=True)

        self.disks: List[Dict[str, str]] = []
        self.active_disks: Set[str] = set()
        self.is_cloning = False

        if os.geteuid() != 0:
            messagebox.showerror("Erreur", "Ce programme doit être lancé en tant que root !")
            root.destroy()
            sys.exit(1)

        self.create_widgets()
        self.refresh_disks()

    def create_widgets(self) -> None:
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        title_label = ttk.Label(main_frame, text="Clonage Disque Sécurisé", font=("Arial", 16, "bold"))
        title_label.pack(pady=10)

        selection_frame = ttk.Frame(main_frame)
        selection_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        source_frame = ttk.LabelFrame(selection_frame, text="Disque Source (Cloner depuis)")
        source_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)

        source_list_frame = ttk.Frame(source_frame)
        source_list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.source_listbox = tk.Listbox(source_list_frame, selectmode=tk.SINGLE, height=8)
        source_scrollbar = ttk.Scrollbar(source_list_frame, orient=tk.VERTICAL, command=self.source_listbox.yview)
        self.source_listbox.configure(yscrollcommand=source_scrollbar.set)
        self.source_listbox.bind('<ButtonRelease-1>', self.on_source_select)
        self.source_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        source_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.source_info_var = tk.StringVar(value="Aucun disque source sélectionné")
        source_info_label = ttk.Label(source_frame, textvariable=self.source_info_var,
            wraplength=300, justify=tk.LEFT)
        source_info_label.pack(pady=5)

        dest_frame = ttk.LabelFrame(selection_frame, text="Disque Destination (Cloner vers)")
        dest_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5)

        dest_list_frame = ttk.Frame(dest_frame)
        dest_list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.dest_listbox = tk.Listbox(dest_list_frame, selectmode=tk.SINGLE, height=8)
        dest_scrollbar = ttk.Scrollbar(dest_list_frame, orient=tk.VERTICAL, command=self.dest_listbox.yview)
        self.dest_listbox.configure(yscrollcommand=dest_scrollbar.set)
        self.dest_listbox.bind('<ButtonRelease-1>', self.on_dest_select)
        self.dest_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        dest_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.dest_info_var = tk.StringVar(value="Aucun disque de destination sélectionné")
        dest_info_label = ttk.Label(dest_frame, textvariable=self.dest_info_var,
            wraplength=300, justify=tk.LEFT)
        dest_info_label.pack(pady=5)

        self.source_warning_var = tk.StringVar()
        source_warning_label = ttk.Label(source_frame, textvariable=self.source_warning_var,
            foreground="red", wraplength=300)
        source_warning_label.pack(pady=2)
        self.dest_warning_var = tk.StringVar()
        dest_warning_label = ttk.Label(dest_frame, textvariable=self.dest_warning_var,
            foreground="red", wraplength=300)
        dest_warning_label.pack(pady=2)

        options_frame = ttk.LabelFrame(main_frame, text="Options de clonage")
        options_frame.pack(fill=tk.X, pady=10)

        method_frame = ttk.Frame(options_frame)
        method_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(method_frame, text="Méthode de clonage :").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(method_frame, text="Clonage Complet (bit-à-bit)",
                value="full", variable=self.clone_method_var).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(method_frame, text="Clonage Intelligent (seulement les secteurs utilisés)",
                value="smart", variable=self.clone_method_var).pack(side=tk.LEFT, padx=10)

        verify_frame = ttk.Frame(options_frame)
        verify_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Checkbutton(verify_frame, text="Vérifier le clone après la fin",
            variable=self.verify_clone_var).pack(side=tk.LEFT, padx=5)

        control_frame = ttk.Frame(options_frame)
        control_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(control_frame, text="Rafraîchir les disques",
            command=self.refresh_disks).pack(side=tk.LEFT, padx=5)
        self.start_button = ttk.Button(control_frame, text="Démarrer le clonage",
            command=self.start_clone)
        self.start_button.pack(side=tk.LEFT, padx=5)
        self.stop_button = ttk.Button(control_frame, text="Arrêter le clonage",
            command=self.stop_clone, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Quitter le mode plein écran",
            command=self.toggle_fullscreen).pack(side=tk.RIGHT, padx=5)
        ttk.Button(control_frame, text="Quitter",
            command=self.exit_application).pack(side=tk.RIGHT, padx=5)

        progress_frame = ttk.LabelFrame(main_frame, text="Progression")
        progress_frame.pack(fill=tk.X, pady=10)
        self.progress_var = tk.DoubleVar()
        self.progress = ttk.Progressbar(progress_frame, variable=self.progress_var,
            maximum=100, mode='determinate')
        self.progress.pack(fill=tk.X, padx=10, pady=5)
        self.status_var = tk.StringVar(value="Prêt")
        status_label = ttk.Label(progress_frame, textvariable=self.status_var)
        status_label.pack(pady=5)

        log_frame = ttk.LabelFrame(main_frame, text="Journal")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        self.log_text = tk.Text(log_frame, height=8, wrap=tk.WORD)
        log_scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.root.protocol("WM_DELETE_WINDOW", self.exit_application)

    def refresh_disks(self) -> None:
        self.update_log("Rafraîchissement de la liste des disques...")
        self.source_listbox.delete(0, tk.END)
        self.dest_listbox.delete(0, tk.END)
        self.source_disk_var.set("")
        self.dest_disk_var.set("")

        self.disks = get_disk_list()
        active_disk_list = get_active_disk()
        if active_disk_list:
            self.active_disks = {get_base_disk(disk) for disk in active_disk_list}
            log_info(f"Disques actifs détectés : {self.active_disks}")
        else:
            self.active_disks = set()

        if not self.disks:
            self.update_log("Aucun disque trouvé.")
            self.source_warning_var.set("Aucun disque disponible")
            self.dest_warning_var.set("Aucun disque disponible")
            return

        for disk in self.disks:
            device_name = disk['device'].replace('/dev/', '')
            base_device = get_base_disk(device_name)
            try:
                disk_serial = get_disk_serial(device_name)
                is_device_ssd = is_ssd(device_name)
                ssd_indicator = " (Électronique)" if is_device_ssd else " (Mécanique)"
                is_active = base_device in self.active_disks
                active_indicator = " [ACTIF - INDISPONIBLE]" if is_active else ""
                disk_info = f"{disk_serial}{ssd_indicator} - {disk['size']}{active_indicator}"
                self.source_listbox.insert(tk.END, disk_info)
                if is_active:
                    self.source_listbox.itemconfig(tk.END, {'fg': 'red'})
                self.dest_listbox.insert(tk.END, disk_info)
                if is_active:
                    self.dest_listbox.itemconfig(tk.END, {'fg': 'red'})
            except (OSError, IOError) as e:
                self.update_log(f"Erreur d'E/S lors de la récupération des infos pour {device_name} : {str(e)}")
            except (CalledProcessError, subprocess.SubprocessError) as e:
                self.update_log(f"Erreur de commande lors de la récupération des infos pour {device_name} : {str(e)}")
            except (ValueError, TypeError) as e:
                self.update_log(f"Erreur de données lors de la récupération des infos pour {device_name} : {str(e)}")
            except FileNotFoundError as e:
                self.update_log(f"Fichier introuvable pour {device_name} : {str(e)}")
            except PermissionError as e:
                self.update_log(f"Problème de permission pour {device_name} : {str(e)}")

        if self.active_disks:
            warning_msg = f"ATTENTION : Les disques système actifs ({', '.join(self.active_disks)}) ne peuvent pas être sélectionnés"
            self.source_warning_var.set(warning_msg)
            self.dest_warning_var.set(warning_msg)
        else:
            self.source_warning_var.set("")
            self.dest_warning_var.set("")

        self.update_source_dest_info()
        self.update_log(f"{len(self.disks)} disque(s) trouvé(s)")

    def on_source_select(self, event) -> None:
        selection = self.source_listbox.curselection()
        if selection:
            index = selection[0]
            if index < len(self.disks):
                disk = self.disks[index]
                device_name = disk['device'].replace('/dev/', '')
                base_device = get_base_disk(device_name)
                if base_device in self.active_disks:
                    messagebox.showwarning("Sélection invalide", "Impossible de sélectionner un disque système actif comme source !")
                    self.source_listbox.selection_clear(0, tk.END)
                    return
                self.source_disk_var.set(disk['device'])
                self.update_source_dest_info()
                self.update_dest_availability()

    def on_dest_select(self, event) -> None:
        selection = self.dest_listbox.curselection()
        if selection:
            index = selection[0]
            if index < len(self.disks):
                disk = self.disks[index]
                device_name = disk['device'].replace('/dev/', '')
                base_device = get_base_disk(device_name)
                if base_device in self.active_disks:
                    messagebox.showwarning("Sélection invalide", "Impossible de sélectionner un disque système actif comme destination !")
                    self.dest_listbox.selection_clear(0, tk.END)
                    return
                if disk['device'] == self.source_disk_var.get():
                    messagebox.showwarning("Sélection invalide", "La source et la destination ne peuvent pas être le même disque !")
                    self.dest_listbox.selection_clear(0, tk.END)
                    return
                self.dest_disk_var.set(disk['device'])
                self.update_source_dest_info()

    def update_dest_availability(self) -> None:
        source_device = self.source_disk_var.get()
        if not source_device:
            return
        for i, disk in enumerate(self.disks):
            if disk['device'] == source_device:
                current_text = self.dest_listbox.get(i)
                if "[SOURCE - INDISPONIBLE]" not in current_text:
                    new_text = current_text.replace("[ACTIF - INDISPONIBLE]", "").strip()
                    new_text += " [SOURCE - INDISPONIBLE]"
                    self.dest_listbox.delete(i)
                    self.dest_listbox.insert(i, new_text)
                    self.dest_listbox.itemconfig(i, {'fg': 'orange'})
                break

    def update_source_dest_info(self) -> None:
        source_device = self.source_disk_var.get()
        dest_device = self.dest_disk_var.get()
        if source_device:
            source_disk = next((d for d in self.disks if d['device'] == source_device), None)
            if source_disk:
                device_name = source_device.replace('/dev/', '')
                try:
                    disk_serial = get_disk_serial(device_name)
                    is_device_ssd = is_ssd(device_name)
                    disk_type = "SSD" if is_device_ssd else "HDD"
                    info = f" Sélectionné : {disk_serial}\nType : {disk_type}\nTaille : {source_disk['size']}\nModèle : {source_disk['model']}"
                    self.source_info_var.set(info)
                except (OSError, IOError) as e:
                    self.source_info_var.set(f"Sélectionné : {source_device}\nErreur d’E/S lors de la récupération des détails : {str(e)}")
                except (CalledProcessError, subprocess.SubprocessError) as e:
                    self.source_info_var.set(f"Sélectionné : {source_device}\nErreur de commande lors de la récupération des détails : {str(e)}")
                except (ValueError, TypeError) as e:
                    self.source_info_var.set(f"Sélectionné : {source_device}\nErreur de données lors de la récupération des détails : {str(e)}")
                except FileNotFoundError as e:
                    self.source_info_var.set(f"Sélectionné : {source_device}\nFichier introuvable : {str(e)}")
                except PermissionError as e:
                    self.source_info_var.set(f"Sélectionné : {source_device}\nPermission refusée : {str(e)}")
            else:
                self.source_info_var.set("Aucun disque source sélectionné")
        else:
            self.source_info_var.set("Aucun disque source sélectionné")
        if dest_device:
            dest_disk = next((d for d in self.disks if d['device'] == dest_device), None)
            if dest_disk:
                device_name = dest_device.replace('/dev/', '')
                try:
                    disk_serial = get_disk_serial(device_name)
                    is_device_ssd = is_ssd(device_name)
                    disk_type = "SSD" if is_device_ssd else "HDD"
                    info = f"Sélectionné : {disk_serial}\nType : {disk_type}\nTaille : {dest_disk['size']}\nModèle : {dest_disk['model']}"
                    self.dest_info_var.set(info)
                except (OSError, IOError) as e:
                    self.dest_info_var.set(f"Sélectionné : {dest_device}\nErreur d’E/S lors de la récupération des détails : {str(e)}")
                except (CalledProcessError, subprocess.SubprocessError) as e:
                    self.dest_info_var.set(f"Sélectionné : {dest_device}\nErreur de commande lors de la récupération des détails : {str(e)}")
                except (ValueError, TypeError) as e:
                    self.dest_info_var.set(f"Sélectionné : {dest_device}\nErreur de données lors de la récupération des détails : {str(e)}")
                except FileNotFoundError as e:
                    self.dest_info_var.set(f"Sélectionné : {dest_device}\nFichier introuvable : {str(e)}")
                except PermissionError as e:
                    self.dest_info_var.set(f"Sélectionné : {dest_device}\nPermission refusée : {str(e)}")
            else:
                self.dest_info_var.set("Aucun disque de destination sélectionné")
        else:
            self.dest_info_var.set("Aucun disque de destination sélectionné")

    def start_clone(self) -> None:
        source_device = self.source_disk_var.get()
        dest_device = self.dest_disk_var.get()
        if not source_device or not dest_device:
            messagebox.showwarning("Sélection requise", "Veuillez sélectionner à la fois le disque source et le disque de destination !")
            return
        source_disk = next((d for d in self.disks if d['device'] == source_device), None)
        dest_disk = next((d for d in self.disks if d['device'] == dest_device), None)
        if not source_disk or not dest_disk:
            messagebox.showerror("Erreur", "Impossible de trouver les informations du disque !")
            return
        try:
            source_serial = get_disk_serial(source_device.replace('/dev/', ''))
            dest_serial = get_disk_serial(dest_device.replace('/dev/', ''))
        except (OSError, IOError, CalledProcessError, subprocess.SubprocessError,
                FileNotFoundError, PermissionError):
            source_serial = source_device
            dest_serial = dest_device

        clone_method = "Clonage complet (bit-à-bit)" if self.clone_method_var.get() == "full" else "Clonage intelligent (seulement les secteurs utilisés)"
        verify_text = "avec vérification" if self.verify_clone_var.get() else "sans vérification"
        confirm_msg = (f"ATTENTION : Ceci va complètement écraser le disque de destination !\n\n"
                       f"Source : {source_serial} ({source_disk['size']})\n"
                       f"Destination : {dest_serial} ({dest_disk['size']})\n\n"
                       f"Méthode : {clone_method} {verify_text}\n\n"
                       f"TOUTES LES DONNÉES SUR LE DISQUE DE DESTINATION SERONT PERDUES !\n\n"
                       f"Êtes-vous sûr de vouloir continuer ?")
        if not messagebox.askyesno("Confirmer l’opération de clonage", confirm_msg):
            return
        if not messagebox.askyesno("AVERTISSEMENT FINAL",
                                   "Ceci est votre dernier avertissement !\n\n"
                                   "Le disque de destination sera complètement écrasé.\n\n"
                                   "Voulez-vous continuer ?"):
            return
        self.is_cloning = True
        self.start_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self.progress_var.set(0)
        clone_thread = threading.Thread(target=self.clone_disk_thread,
            args=(source_device, dest_device), daemon=True)
        clone_thread.start()

    def clone_disk_thread(self, source_device: str, dest_device: str) -> None:
        try:
            method = self.clone_method_var.get()
            verify = self.verify_clone_var.get()
            self.update_log(f"Démarrage de l’opération de clonage : {source_device} -> {dest_device}")
            self.status_var.set("Initialisation de l’opération de clonage ...")
            if method == "full":
                self.full_clone(source_device, dest_device)
            else:
                self.smart_clone(source_device, dest_device)
            if verify and self.is_cloning:
                self.verify_clone(source_device, dest_device)
            if self.is_cloning:
                self.status_var.set("Opération de clonage terminée avec succès !")
                self.update_log("Opération de clonage terminée avec succès !")
                messagebox.showinfo("Succès", "Clonage du disque terminé avec succès !")
        except (OSError, IOError) as e:
            error_msg = f"Erreur d’E/S lors de l’opération de clonage : {str(e)}"
            self.status_var.set("Échec de l’opération de clonage - Erreur d’E/S !")
            self.update_log(error_msg)
            log_error(error_msg)
            messagebox.showerror("Erreur d’E/S", error_msg)
        except (CalledProcessError, subprocess.SubprocessError) as e:
            error_msg = f"L’exécution de la commande a échoué lors du clonage : {str(e)}"
            self.status_var.set("Échec de l’opération de clonage - Erreur de commande !")
            self.update_log(error_msg)
            log_error(error_msg)
            messagebox.showerror("Erreur de commande", error_msg)
        except FileNotFoundError as e:
            error_msg = f"Fichier ou commande introuvable requis : {str(e)}"
            self.status_var.set("Échec de l’opération de clonage - Fichier introuvable !")
            self.update_log(error_msg)
            log_error(error_msg)
            messagebox.showerror("Fichier introuvable", error_msg)
        except PermissionError as e:
            error_msg = f"Permission refusée lors de l’opération de clonage : {str(e)}"
            self.status_var.set("Échec de l’opération de clonage - Permission refusée !")
            self.update_log(error_msg)
            log_error(error_msg)
            messagebox.showerror("Erreur de permission", error_msg)
        except TimeoutExpired as e:
            error_msg = f"Délai dépassé pour l’opération de clonage : {str(e)}"
            self.status_var.set("Échec de l’opération de clonage - Délai dépassé !")
            self.update_log(error_msg)
            log_error(error_msg)
            messagebox.showerror("Erreur de délai", error_msg)
        except KeyboardInterrupt:
            error_msg = "Opération de clonage interrompue par l’utilisateur"
            self.status_var.set("Opération de clonage interrompue !")
            self.update_log(error_msg)
            log_error(error_msg)
            messagebox.showwarning("Interrompu", error_msg)
        except MemoryError as e:
            error_msg = f"Mémoire insuffisante pour l’opération de clonage : {str(e)}"
            self.status_var.set("Échec de l’opération de clonage - Erreur mémoire !")
            self.update_log(error_msg)
            log_error(error_msg)
            messagebox.showerror("Erreur mémoire", error_msg)
        finally:
            self.is_cloning = False
            self.start_button.configure(state=tk.NORMAL)
            self.stop_button.configure(state=tk.DISABLED)
            self.progress_var.set(0)

    def full_clone(self, source: str, dest: str) -> None:
        self.update_log("Démarrage du clonage complet (bit-à-bit)...")
        self.status_var.set("Clonage complet en cours...")
        block_size = "1M"
        cmd = [
            "dd",
            f"if={source}",
            f"of={dest}",
            f"bs={block_size}",
            "conv=fdatasync",
            "status=progress"
        ]
        def progress_callback():
            current_progress = self.progress_var.get()
            if current_progress < 90:
                self.progress_var.set(current_progress + 1)
        def stop_flag():
            return not self.is_cloning
        try:
            run_command_with_progress(cmd, progress_callback, stop_flag)
            self.progress_var.set(100)
            self.update_log("Clonage complet terminé avec succès")
        except (CalledProcessError, subprocess.SubprocessError) as e:
            raise subprocess.SubprocessError(f"Commande de clonage complet échouée : {str(e)}")
        except (OSError, IOError) as e:
            raise IOError(f"Erreur d’E/S lors du clonage complet : {str(e)}")
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Commande dd introuvable : {str(e)}")
        except PermissionError as e:
            raise PermissionError(f"Permission refusée lors du clonage complet : {str(e)}")
        except TimeoutExpired as e:
            raise TimeoutExpired(cmd, None, f"Délai dépassé lors du clonage complet : {str(e)}")

    def smart_clone(self, source: str, dest: str) -> None:
        self.update_log("Démarrage du clonage intelligent (copie consciente du système de fichiers)...")
        self.status_var.set("Clonage intelligent en cours...")
        self.update_log("Note : Le clonage intelligent n’est pas encore totalement implémenté, utilisation de dd...")
        self.full_clone(source, dest)

    def verify_clone(self, source: str, dest: str) -> None:
        if not self.is_cloning:
            return
        self.update_log("Démarrage de la vérification du clone...")
        self.status_var.set("Vérification du clone en cours...")
        self.progress_var.set(0)
        cmd = [
            "cmp",
            source,
            dest
        ]
        def progress_callback():
            current_progress = self.progress_var.get()
            if current_progress < 90:
                self.progress_var.set(current_progress + 2)
        def stop_flag():
            return not self.is_cloning
        try:
            run_command_with_progress(cmd, progress_callback, stop_flag)
            self.progress_var.set(100)
            self.update_log("Vérification du clone terminée avec succès - les disques sont identiques")
        except CalledProcessError as e:
            if e.returncode == 1:
                self.update_log("ATTENTION : Échec de la vérification du clone - les disques diffèrent !")
                messagebox.showwarning("Vérification échouée", "Échec de la vérification du clone ! Les disques ne sont pas identiques.")
            else:
                raise CalledProcessError(e.returncode, cmd, f"Échec de la commande de vérification : {e.stderr}")
        except (OSError, IOError) as e:
            raise IOError(f"Erreur d’E/S lors de la vérification : {str(e)}")
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Commande cmp introuvable : {str(e)}")
        except PermissionError as e:
            raise PermissionError(f"Permission refusée lors de la vérification : {str(e)}")
        except TimeoutExpired as e:
            raise TimeoutExpired(cmd, None, f"Délai dépassé lors de la vérification : {str(e)}")

    def stop_clone(self) -> None:
        if self.is_cloning:
            if messagebox.askyesno("Confirmer l’arrêt",
                "Voulez-vous vraiment arrêter l’opération de clonage ?\n\n"
                "Cela laissera le disque de destination dans un état incomplet."):
                self.is_cloning = False
                self.update_log("Opération de clonage arrêtée par l’utilisateur")
                self.status_var.set("Opération de clonage arrêtée")

    def toggle_fullscreen(self) -> None:
        is_fullscreen = self.root.attributes("-fullscreen")
        self.root.attributes("-fullscreen", not is_fullscreen)

    def exit_application(self) -> None:
        if self.is_cloning:
            if not messagebox.askyesno("Clonage en cours",
                                       "Une opération de clonage est en cours ... Voulez-vous vraiment quitter ?"):
                return
            self.is_cloning = False
        log_info("L’application de clonage de disque a été fermée par l'utilisateur")
        self.root.destroy()

    def update_log(self, message: str) -> None:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"
        self.log_text.insert(tk.END, log_message)
        self.log_text.see(tk.END)
        self.root.update_idletasks()

def main():
    if os.geteuid() != 0:
        print("Ce programme doit être lancé en tant que root !")
        sys.exit(1)
    root = tk.Tk()
    app = DiskClonerGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
