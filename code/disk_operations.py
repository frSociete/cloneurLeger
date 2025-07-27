import time
from utils import run_command, get_physical_drives_for_logical_volumes, get_base_disk
from subprocess import CalledProcessError
import re
from disk_erase import erase_disk_hdd, get_disk_serial, is_ssd, erase_disk_crypto
from log_handler import log_info, log_error, log_erase_operation, blank


def get_active_disk():
    """
    Detect the active device backing the root filesystem.
    Always returns a list of devices or None for consistency.
    Uses LVM logic if the root device is a logical volume (/dev/mapper/),
    otherwise uses regular disk detection logic including live boot media detection.
    """
    try:
        # Initialize devices set for collecting all active devices
        devices = set()
        live_boot_found = False
        
        # Step 1: Check /proc/mounts for all mounted devices
        with open('/proc/mounts', 'r') as f:
            mounts_content = f.read()
            #log_info("Analyzing /proc/mounts content:")
            #log_info(mounts_content[:500] + "..." if len(mounts_content) > 500 else mounts_content)
            
            # Look for root filesystem mount
            root_device = None
            for line in mounts_content.split('\n'):
                if line.strip() and ' / ' in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        root_device = parts[0]
                        #log_info(f"Found root mount: {line.strip()}")
                        break

        # Step 2: Handle special live boot cases where root is not a real device
        if not root_device or root_device in ['rootfs', 'overlay', 'aufs', '/dev/root']:
            
            # In live boot, look for the actual boot media in /proc/mounts
            with open('/proc/mounts', 'r') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 6:
                        device = parts[0]
                        mount_point = parts[1]
                        
                        # Look for common live boot mount points
                        if any(keyword in mount_point for keyword in ['/run/live', '/lib/live', '/live/', '/cdrom']):
                            match = re.search(r'/dev/([a-zA-Z]+\d*[a-zA-Z]*\d*)', device)
                            if match:
                                devices.add(match.group(1))
                                live_boot_found = True
                        
                        # Also check for USB/removable media patterns
                        elif device.startswith('/dev/') and any(keyword in device for keyword in ['sd', 'nvme', 'mmc']):
                            # Check if this looks like a removable device by checking mount point
                            if '/media' in mount_point or '/mnt' in mount_point or '/run' in mount_point:
                                match = re.search(r'/dev/([a-zA-Z]+\d*[a-zA-Z]*\d*)', device)
                                if match:
                                    devices.add(match.group(1))
                                    #log_info(f"Found potential boot device: {match.group(1)} at {mount_point}")
            
            
            # If we still haven't found anything, fall back to df command analysis
            if not devices:
                # Use df command instead of viewing /proc/mounts
                try:
                    output = run_command(["df", "-h"])
                    lines = output.strip().split('\n')
                    
                    for line in lines[1:]:  # Skip header
                        parts = line.split()
                        if len(parts) >= 6:
                            device = parts[0]
                            mount_point = parts[5]
                            
                            # Look for any mounted storage devices
                            if device.startswith('/dev/') and any(keyword in device for keyword in ['sd', 'nvme', 'mmc']):
                                match = re.search(r'/dev/([a-zA-Z]+\d*[a-zA-Z]*\d*)', device)
                                if match:
                                    devices.add(match.group(1))
                except (FileNotFoundError, CalledProcessError) as e:
                    log_error(f"Error running df command: {str(e)}")
        
        else:
            # Step 3: Handle normal root device (installed system)
            # Check if this is LVM/device mapper
            if '/dev/mapper/' in root_device or '/dev/dm-' in root_device:
                # LVM resolution - map to physical drives
                active_physical_drives = get_physical_drives_for_logical_volumes([root_device])
                #Redundant logging
                #log_info(f"Active logical device: {root_device}")
                #log_info(f"Mapped to physical drives: {active_physical_drives}")
                
                # Add physical drives to devices set
                for drive in active_physical_drives:
                    devices.add(get_base_disk(drive))
                    
            else:
                # Regular disk - extract device name with improved regex for NVMe
                match = re.search(r'/dev/([a-zA-Z]+\d*[a-zA-Z]*\d*)', root_device)
                if match:
                    devices.add(match.group(1))
            
            # Also check for live boot media even in normal systems
            try:
                output = run_command(["df", "-h"])
                lines = output.strip().split('\n')
                
                for line in lines[1:]:  # Skip header line
                    parts = line.split()
                    if len(parts) >= 6:
                        device = parts[0]
                        mount_point = parts[5]
                        
                        # Check for live boot mount points
                        if "/run/live" in mount_point or "/lib/live" in mount_point:
                            match = re.search(r'/dev/([a-zA-Z]+\d*[a-zA-Z]*\d*)', device)
                            if match:
                                devices.add(match.group(1))
                                live_boot_found = True
                                #log_info(f"Found live boot device: {match.group(1)}")
            except (FileNotFoundError, CalledProcessError) as e:
                log_info(f"Could not check for live boot devices: {str(e)}")

        # Step 4: Return logic
        if devices:
            device_list = list(devices)
            
            # If we found live boot devices, prioritize those (remove LVM if present)
            if live_boot_found:
                # Filter out LVM devices when live boot is detected, keep only regular disk names
                final_devices = [dev for dev in device_list if not dev.startswith('/dev/')]
                if final_devices:
                    return final_devices
            return device_list
        else:
            log_error("No active devices found")
            return None

    except FileNotFoundError as e:
        log_error(f"Required file not found: {str(e)}")
        return None
    except PermissionError as e:
        log_error(f"Permission denied accessing system files: {str(e)}")
        return None
    except OSError as e:
        log_error(f"OS error accessing system information: {str(e)}")
        return None
    except CalledProcessError as e:
        log_error(f"Error running command: {str(e)}")
        return None
    except (IndexError, ValueError) as e:
        log_error(f"Error parsing command output: {str(e)}")
        return None
    except re.error as e:
        log_error(f"Regex pattern error: {str(e)}")
        return None
    except KeyboardInterrupt:
        log_error("Operation interrupted by user")
        return None
    except UnicodeDecodeError as e:
        log_error(f"Error decoding file content: {str(e)}")
        return None
    except MemoryError:
        log_error("Insufficient memory to process device information")
        return None