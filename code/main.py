#!/usr/bin/env python3

import os
import sys
import time
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Dict, List, Set
from subprocess import CalledProcessError

# Import functions from existing modules
from utils import get_disk_list, get_base_disk, get_active_disk, get_disk_serial, is_ssd, run_command, run_command_with_progress
from log_handler import log_info, log_error

class DiskClonerGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Secure Disk Cloner")
        self.root.geometry("800x600")
        # Set fullscreen mode
        self.root.attributes("-fullscreen", True)
        
        # Variables for disk selection
        self.source_disk_var = tk.StringVar()
        self.dest_disk_var = tk.StringVar()
        self.clone_method_var = tk.StringVar(value="full")  # full or smart
        self.verify_clone_var = tk.BooleanVar(value=True)
        
        # Data storage
        self.disks: List[Dict[str, str]] = []
        self.active_disks: Set[str] = set()
        self.is_cloning = False
        
        # Check for root privileges
        if os.geteuid() != 0:
            messagebox.showerror("Error", "This program must be run as root!")
            root.destroy()
            sys.exit(1)
        
        self.create_widgets()
        self.refresh_disks()
    
    def create_widgets(self) -> None:
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = ttk.Label(main_frame, text="Secure Disk Cloner", font=("Arial", 16, "bold"))
        title_label.pack(pady=10)
        
        # Top frame for disk selection
        selection_frame = ttk.Frame(main_frame)
        selection_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Source disk frame
        source_frame = ttk.LabelFrame(selection_frame, text="Source Disk (Clone From)")
        source_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        # Source disk listbox with scrollbar
        source_list_frame = ttk.Frame(source_frame)
        source_list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.source_listbox = tk.Listbox(source_list_frame, selectmode=tk.SINGLE, height=8)
        source_scrollbar = ttk.Scrollbar(source_list_frame, orient=tk.VERTICAL, command=self.source_listbox.yview)
        self.source_listbox.configure(yscrollcommand=source_scrollbar.set)
        self.source_listbox.bind('<<ListboxSelect>>', self.on_source_select)
        
        self.source_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        source_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Source disk info
        self.source_info_var = tk.StringVar(value="No source disk selected")
        source_info_label = ttk.Label(source_frame, textvariable=self.source_info_var, 
                                     wraplength=300, justify=tk.LEFT)
        source_info_label.pack(pady=5)
        
        # Destination disk frame
        dest_frame = ttk.LabelFrame(selection_frame, text="Destination Disk (Clone To)")
        dest_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5)
        
        # Destination disk listbox with scrollbar
        dest_list_frame = ttk.Frame(dest_frame)
        dest_list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.dest_listbox = tk.Listbox(dest_list_frame, selectmode=tk.SINGLE, height=8)
        dest_scrollbar = ttk.Scrollbar(dest_list_frame, orient=tk.VERTICAL, command=self.dest_listbox.yview)
        self.dest_listbox.configure(yscrollcommand=dest_scrollbar.set)
        self.dest_listbox.bind('<<ListboxSelect>>', self.on_dest_select)
        
        self.dest_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        dest_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Destination disk info
        self.dest_info_var = tk.StringVar(value="No destination disk selected")
        dest_info_label = ttk.Label(dest_frame, textvariable=self.dest_info_var, 
                                   wraplength=300, justify=tk.LEFT)
        dest_info_label.pack(pady=5)
        
        # Warning labels
        self.source_warning_var = tk.StringVar()
        source_warning_label = ttk.Label(source_frame, textvariable=self.source_warning_var, 
                                        foreground="red", wraplength=300)
        source_warning_label.pack(pady=2)
        
        self.dest_warning_var = tk.StringVar()
        dest_warning_label = ttk.Label(dest_frame, textvariable=self.dest_warning_var, 
                                      foreground="red", wraplength=300)
        dest_warning_label.pack(pady=2)
        
        # Options frame
        options_frame = ttk.LabelFrame(main_frame, text="Clone Options")
        options_frame.pack(fill=tk.X, pady=10)
        
        # Clone method options
        method_frame = ttk.Frame(options_frame)
        method_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(method_frame, text="Clone Method:").pack(side=tk.LEFT, padx=5)
        
        ttk.Radiobutton(method_frame, text="Full Clone (bit-by-bit)", 
                       value="full", variable=self.clone_method_var).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(method_frame, text="Smart Clone (used sectors only)", 
                       value="smart", variable=self.clone_method_var).pack(side=tk.LEFT, padx=10)
        
        # Verify option
        verify_frame = ttk.Frame(options_frame)
        verify_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Checkbutton(verify_frame, text="Verify clone after completion", 
                       variable=self.verify_clone_var).pack(side=tk.LEFT, padx=5)
        
        # Control buttons frame
        control_frame = ttk.Frame(options_frame)
        control_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Refresh button
        ttk.Button(control_frame, text="Refresh Disks", 
                  command=self.refresh_disks).pack(side=tk.LEFT, padx=5)
        
        # Start clone button
        self.start_button = ttk.Button(control_frame, text="Start Clone", 
                                      command=self.start_clone)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        # Stop clone button
        self.stop_button = ttk.Button(control_frame, text="Stop Clone", 
                                     command=self.stop_clone, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        # Exit fullscreen button
        ttk.Button(control_frame, text="Exit Fullscreen", 
                  command=self.toggle_fullscreen).pack(side=tk.RIGHT, padx=5)
        
        # Exit button
        ttk.Button(control_frame, text="Exit", 
                  command=self.exit_application).pack(side=tk.RIGHT, padx=5)
        
        # Progress frame
        progress_frame = ttk.LabelFrame(main_frame, text="Progress")
        progress_frame.pack(fill=tk.X, pady=10)
        
        self.progress_var = tk.DoubleVar()
        self.progress = ttk.Progressbar(progress_frame, variable=self.progress_var, 
                                       maximum=100, mode='determinate')
        self.progress.pack(fill=tk.X, padx=10, pady=5)
        
        self.status_var = tk.StringVar(value="Ready")
        status_label = ttk.Label(progress_frame, textvariable=self.status_var)
        status_label.pack(pady=5)
        
        # Log frame
        log_frame = ttk.LabelFrame(main_frame, text="Log")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        self.log_text = tk.Text(log_frame, height=8, wrap=tk.WORD)
        log_scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Window close protocol
        self.root.protocol("WM_DELETE_WINDOW", self.exit_application)
    
    def refresh_disks(self) -> None:
        """Refresh the list of available disks"""
        self.update_log("Refreshing disk list...")
        
        # Clear existing selections
        self.source_listbox.delete(0, tk.END)
        self.dest_listbox.delete(0, tk.END)
        self.source_disk_var.set("")
        self.dest_disk_var.set("")
        
        # Get disk list and active disks
        self.disks = get_disk_list()
        active_disk_list = get_active_disk()
        
        if active_disk_list:
            # Convert to base disk names and store as set
            self.active_disks = {get_base_disk(disk) for disk in active_disk_list}
            log_info(f"Active disks detected: {self.active_disks}")
        else:
            self.active_disks = set()
        
        if not self.disks:
            self.update_log("No disks found.")
            self.source_warning_var.set("No disks available")
            self.dest_warning_var.set("No disks available")
            return
        
        # Populate listboxes
        for disk in self.disks:
            device_name = disk['device'].replace('/dev/', '')
            base_device = get_base_disk(device_name)
            
            try:
                disk_serial = get_disk_serial(device_name)
                is_device_ssd = is_ssd(device_name)
                ssd_indicator = " (Electronic)" if is_device_ssd else " (Mechanic)"
                
                # Check if this is an active disk
                is_active = base_device in self.active_disks
                active_indicator = " [ACTIVE - UNAVAILABLE]" if is_active else ""
                
                disk_info = f"{disk_serial}{ssd_indicator} - {disk['size']}{active_indicator}"
                
                # Add to source listbox (disable active disks)
                self.source_listbox.insert(tk.END, disk_info)
                if is_active:
                    # Change color for active disks
                    self.source_listbox.itemconfig(tk.END, {'fg': 'red'})
                
                # Add to destination listbox (disable active disks)
                self.dest_listbox.insert(tk.END, disk_info)
                if is_active:
                    # Change color for active disks
                    self.dest_listbox.itemconfig(tk.END, {'fg': 'red'})
                    
            except Exception as e:
                self.update_log(f"Error getting info for {device_name}: {str(e)}")
        
        # Update warning messages
        if self.active_disks:
            warning_msg = f"WARNING: Active system disks ({', '.join(self.active_disks)}) cannot be selected"
            self.source_warning_var.set(warning_msg)
            self.dest_warning_var.set(warning_msg)
        else:
            self.source_warning_var.set("")
            self.dest_warning_var.set("")
        
        self.update_source_dest_info()
        self.update_log(f"Found {len(self.disks)} disks")
    
    def on_source_select(self, event) -> None:
        """Handle source disk selection"""
        selection = self.source_listbox.curselection()
        if selection:
            index = selection[0]
            if index < len(self.disks):
                disk = self.disks[index]
                device_name = disk['device'].replace('/dev/', '')
                base_device = get_base_disk(device_name)
                
                # Check if this is an active disk
                if base_device in self.active_disks:
                    messagebox.showwarning("Invalid Selection", 
                                         "Cannot select active system disk as source!")
                    self.source_listbox.selection_clear(0, tk.END)
                    return
                
                self.source_disk_var.set(disk['device'])
                self.update_source_dest_info()
                self.update_dest_availability()
    
    def on_dest_select(self, event) -> None:
        """Handle destination disk selection"""
        selection = self.dest_listbox.curselection()
        if selection:
            index = selection[0]
            if index < len(self.disks):
                disk = self.disks[index]
                device_name = disk['device'].replace('/dev/', '')
                base_device = get_base_disk(device_name)
                
                # Check if this is an active disk
                if base_device in self.active_disks:
                    messagebox.showwarning("Invalid Selection", 
                                         "Cannot select active system disk as destination!")
                    self.dest_listbox.selection_clear(0, tk.END)
                    return
                
                # Check if this is the same as source
                if disk['device'] == self.source_disk_var.get():
                    messagebox.showwarning("Invalid Selection", 
                                         "Source and destination cannot be the same disk!")
                    self.dest_listbox.selection_clear(0, tk.END)
                    return
                
                self.dest_disk_var.set(disk['device'])
                self.update_source_dest_info()
    
    def update_dest_availability(self) -> None:
        """Update destination listbox to disable source disk"""
        source_device = self.source_disk_var.get()
        if not source_device:
            return
        
        # Find the index of the source device in the destination list
        for i, disk in enumerate(self.disks):
            if disk['device'] == source_device:
                # Update the item text to show it's unavailable
                current_text = self.dest_listbox.get(i)
                if "[SOURCE - UNAVAILABLE]" not in current_text:
                    new_text = current_text.replace("[ACTIVE - UNAVAILABLE]", "").strip()
                    new_text += " [SOURCE - UNAVAILABLE]"
                    self.dest_listbox.delete(i)
                    self.dest_listbox.insert(i, new_text)
                    self.dest_listbox.itemconfig(i, {'fg': 'orange'})
                break
    
    def update_source_dest_info(self) -> None:
        """Update the information display for source and destination disks"""
        source_device = self.source_disk_var.get()
        dest_device = self.dest_disk_var.get()
        
        # Update source info
        if source_device:
            source_disk = next((d for d in self.disks if d['device'] == source_device), None)
            if source_disk:
                device_name = source_device.replace('/dev/', '')
                try:
                    disk_serial = get_disk_serial(device_name)
                    is_device_ssd = is_ssd(device_name)
                    disk_type = "SSD" if is_device_ssd else "HDD"
                    info = f"Selected: {disk_serial}\nType: {disk_type}\nSize: {source_disk['size']}\nModel: {source_disk['model']}"
                    self.source_info_var.set(info)
                except Exception as e:
                    self.source_info_var.set(f"Selected: {source_device}\nError getting details: {str(e)}")
        else:
            self.source_info_var.set("No source disk selected")
        
        # Update destination info
        if dest_device:
            dest_disk = next((d for d in self.disks if d['device'] == dest_device), None)
            if dest_disk:
                device_name = dest_device.replace('/dev/', '')
                try:
                    disk_serial = get_disk_serial(device_name)
                    is_device_ssd = is_ssd(device_name)
                    disk_type = "SSD" if is_device_ssd else "HDD"
                    info = f"Selected: {disk_serial}\nType: {disk_type}\nSize: {dest_disk['size']}\nModel: {dest_disk['model']}"
                    self.dest_info_var.set(info)
                except Exception as e:
                    self.dest_info_var.set(f"Selected: {dest_device}\nError getting details: {str(e)}")
        else:
            self.dest_info_var.set("No destination disk selected")
    
    def start_clone(self) -> None:
        """Start the disk cloning process"""
        source_device = self.source_disk_var.get()
        dest_device = self.dest_disk_var.get()
        
        if not source_device or not dest_device:
            messagebox.showwarning("Selection Required", 
                                 "Please select both source and destination disks!")
            return
        
        # Get disk information for confirmation
        source_disk = next((d for d in self.disks if d['device'] == source_device), None)
        dest_disk = next((d for d in self.disks if d['device'] == dest_device), None)
        
        if not source_disk or not dest_disk:
            messagebox.showerror("Error", "Could not find disk information!")
            return
        
        # Get disk serials for display
        try:
            source_serial = get_disk_serial(source_device.replace('/dev/', ''))
            dest_serial = get_disk_serial(dest_device.replace('/dev/', ''))
        except Exception as e:
            source_serial = source_device
            dest_serial = dest_device
        
        # Show confirmation dialog
        clone_method = "Full clone (bit-by-bit copy)" if self.clone_method_var.get() == "full" else "Smart clone (used sectors only)"
        verify_text = "with verification" if self.verify_clone_var.get() else "without verification"
        
        confirm_msg = (f"WARNING: This will completely overwrite the destination disk!\n\n"
                      f"Source: {source_serial} ({source_disk['size']})\n"
                      f"Destination: {dest_serial} ({dest_disk['size']})\n\n"
                      f"Method: {clone_method} {verify_text}\n\n"
                      f"ALL DATA ON THE DESTINATION DISK WILL BE LOST!\n\n"
                      f"Are you sure you want to continue?")
        
        if not messagebox.askyesno("Confirm Clone Operation", confirm_msg):
            return
        
        # Final confirmation
        if not messagebox.askyesno("FINAL WARNING", 
                                  "This is your final warning!\n\n"
                                  "The destination disk will be completely overwritten.\n\n"
                                  "Do you want to proceed?"):
            return
        
        # Start cloning in a separate thread
        self.is_cloning = True
        self.start_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self.progress_var.set(0)
        
        clone_thread = threading.Thread(target=self.clone_disk_thread, 
                                       args=(source_device, dest_device), daemon=True)
        clone_thread.start()
    
    def clone_disk_thread(self, source_device: str, dest_device: str) -> None:
        """Thread function for disk cloning"""
        try:
            method = self.clone_method_var.get()
            verify = self.verify_clone_var.get()
            
            self.update_log(f"Starting clone operation: {source_device} -> {dest_device}")
            self.status_var.set("Initializing clone operation...")
            
            if method == "full":
                self.full_clone(source_device, dest_device)
            else:
                self.smart_clone(source_device, dest_device)
            
            if verify and self.is_cloning:
                self.verify_clone(source_device, dest_device)
            
            if self.is_cloning:
                self.status_var.set("Clone operation completed successfully!")
                self.update_log("Clone operation completed successfully!")
                messagebox.showinfo("Success", "Disk clone completed successfully!")
        
        except Exception as e:
            error_msg = f"Clone operation failed: {str(e)}"
            self.status_var.set("Clone operation failed!")
            self.update_log(error_msg)
            log_error(error_msg)
            messagebox.showerror("Error", error_msg)
        
        finally:
            self.is_cloning = False
            self.start_button.configure(state=tk.NORMAL)
            self.stop_button.configure(state=tk.DISABLED)
            self.progress_var.set(0)
    
    def full_clone(self, source: str, dest: str) -> None:
        """Perform full disk clone using dd"""
        self.update_log("Starting full clone (bit-by-bit copy)...")
        self.status_var.set("Performing full clone...")
        
        # Use dd with progress monitoring
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
            if current_progress < 90:  # Don't reach 100% until actually done
                self.progress_var.set(current_progress + 1)
        
        def stop_flag():
            return not self.is_cloning
        
        try:
            run_command_with_progress(cmd, progress_callback, stop_flag)
            self.progress_var.set(100)
            self.update_log("Full clone completed successfully")
        except Exception as e:
            raise Exception(f"Full clone failed: {str(e)}")
    
    def smart_clone(self, source: str, dest: str) -> None:
        """Perform smart clone using partclone or similar"""
        self.update_log("Starting smart clone (filesystem-aware copy)...")
        self.status_var.set("Performing smart clone...")
        
        # For now, fallback to dd - in a real implementation, you'd use partclone
        # or similar tools that understand filesystem structures
        self.update_log("Note: Smart clone not fully implemented, using dd...")
        self.full_clone(source, dest)
    
    def verify_clone(self, source: str, dest: str) -> None:
        """Verify the cloned disk"""
        if not self.is_cloning:
            return
            
        self.update_log("Starting clone verification...")
        self.status_var.set("Verifying clone...")
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
            self.update_log("Clone verification completed successfully - disks are identical")
        except CalledProcessError as e:
            if e.returncode == 1:
                self.update_log("WARNING: Clone verification failed - disks differ!")
                messagebox.showwarning("Verification Failed", 
                                     "Clone verification failed! The disks are not identical.")
            else:
                raise Exception(f"Verification command failed: {e.stderr}")
        except Exception as e:
            raise Exception(f"Verification failed: {str(e)}")
    
    def stop_clone(self) -> None:
        """Stop the cloning process"""
        if self.is_cloning:
            if messagebox.askyesno("Confirm Stop", 
                                  "Are you sure you want to stop the clone operation?\n\n"
                                  "This will leave the destination disk in an incomplete state."):
                self.is_cloning = False
                self.update_log("Clone operation stopped by user")
                self.status_var.set("Clone operation stopped")
    
    def toggle_fullscreen(self) -> None:
        """Toggle fullscreen mode"""
        is_fullscreen = self.root.attributes("-fullscreen")
        self.root.attributes("-fullscreen", not is_fullscreen)
    
    def exit_application(self) -> None:
        """Exit the application"""
        if self.is_cloning:
            if not messagebox.askyesno("Clone in Progress", 
                                      "A clone operation is in progress.\n\n"
                                      "Are you sure you want to exit?"):
                return
            self.is_cloning = False
        
        log_info("Disk Cloner application closed by user")
        self.root.destroy()
    
    def update_log(self, message: str) -> None:
        """Update the log display"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"
        
        self.log_text.insert(tk.END, log_message)
        self.log_text.see(tk.END)
        self.root.update_idletasks()

def main():
    """Main function to run the disk cloner"""
    # Check for root privileges
    if os.geteuid() != 0:
        print("This program must be run as root!")
        sys.exit(1)
    
    root = tk.Tk()
    app = DiskClonerGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()