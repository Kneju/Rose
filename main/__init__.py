#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Main entry point for Rose
"""

import argparse
import sys
from typing import Optional
from pathlib import Path

# Python version check
MIN_PYTHON = (3, 11)
if sys.version_info < MIN_PYTHON:
    raise RuntimeError(
        f"Rose requires Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer. "
        "Please upgrade your interpreter and rebuild the application."
    )


def _get_tools_dir() -> Path:
    """Get the tools directory path (works in both frozen and development environments)"""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable (PyInstaller)
        if hasattr(sys, '_MEIPASS'):
            # One-file mode: tools are in _MEIPASS
            base_path = Path(sys._MEIPASS)
            return base_path / "injection" / "tools"
        else:
            # One-dir mode: tools are alongside executable
            base_dir = Path(sys.executable).parent
            possible_dirs = [
                base_dir / "injection" / "tools",
                base_dir / "_internal" / "injection" / "tools",
            ]
            for dir_path in possible_dirs:
                if dir_path.exists():
                    return dir_path
            return possible_dirs[0]
    else:
        # Running as Python script
        return Path(__file__).parent.parent / "injection" / "tools"


_VALID_DLL_HASHES = {
    "4a009619c6dea691780b2f20cf17e08de478a78b3f11cd72759dd71c00ad1c90",
}


def _check_dll_hash(dll_path) -> bool:
    """Verify cslol-dll.dll matches a known-good SHA-256 hash."""
    import hashlib
    try:
        sha = hashlib.sha256()
        with open(dll_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha.update(chunk)
        return sha.hexdigest() in _VALID_DLL_HASHES
    except Exception:
        return False


def _show_dll_dialog(tools_dir, reason="missing") -> bool:
    """Show a dialog using Tkinter to avoid Windows API crashes."""
    import subprocess
    import webbrowser
    
    tools_dir.mkdir(parents=True, exist_ok=True)
    
    if reason == "invalid":
        title = "Rose - Broken DLL"
        header = "Broken File: cslol-dll.dll"
        body = (
            "The file you put in the folder is broken, outdated, or wrong.\n"
            "Using an unverified DLL can compromise your system.\n\n"
            "STEPS TO FIX:\n"
            "1. Download a NEW 'cslol-dll.dll' from the internet.\n"
            "2. Click the [ Open Folder ] button below.\n"
            "3. Delete the old file and put the new correct one there.\n"
            "4. Restart Rose.\n\n"
            "WARNING: Do NOT ask for and do NOT share this file on our Discord.\n"
            "This file is NOT available in there due DMCA (license) restrictions!\n"
            "Instead, you will be banned permanently."
        )
    else:
        title = "Rose - Missing DLL"
        header = "Missing File: cslol-dll.dll"
        body = (
            "Rose cannot start without this file.\n\n"
            "STEPS TO FIX:\n"
            "1. Download 'cslol-dll.dll' from the internet.\n"
            "2. Click the [ Open Folder ] button below.\n"
            "3. Drag and drop the file into the opened folder.\n"
            "4. Restart Rose.\n\n"
            "WARNING: Do NOT ask for and do NOT share this file on our Discord.\n"
            "This file is NOT available in there due DMCA (license) restrictions!\n"
            "Instead, you will be banned permanently."
        )

    try:
        import tkinter as tk
        from tkinter import ttk
        
        root = tk.Tk()
        root.title(title)
        
        root.attributes('-toolwindow', True)
        root.attributes('-topmost', True)
        root.resizable(False, False)
        
        style = ttk.Style()
        if 'vista' in style.theme_names():
            style.theme_use('vista')
        
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        lbl_header = ttk.Label(frame, text=header, font=("Segoe UI", 11, "bold"), foreground="#D32F2F")
        lbl_header.pack(anchor=tk.W, pady=(0, 10))
        
        lbl_body = ttk.Label(frame, text=body, font=("Segoe UI", 10), justify=tk.LEFT)
        lbl_body.pack(anchor=tk.W, pady=(0, 10))
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        def on_open():
            try:
                subprocess.run(["explorer", str(tools_dir)], check=False)
            except Exception:
                pass
            root.destroy()

        def on_close():
            root.destroy()

        def on_discord():
            try:
                webbrowser.open("https://discord.gg/roseskins")
            except Exception:
                pass

        btn_open = ttk.Button(btn_frame, text="📂 Open Folder", command=on_open)
        btn_open.pack(side=tk.LEFT, padx=(0, 10), ipadx=5, ipady=2)
        
        btn_close = ttk.Button(btn_frame, text="❌ Close Rose", command=on_close)
        btn_close.pack(side=tk.LEFT, padx=(0, 8), ipadx=5, ipady=2)

        btn_discord = ttk.Button(btn_frame, text="✉ Join Discord", command=on_discord)
        btn_discord.pack(side=tk.LEFT, ipadx=5, ipady=2)
        
        root.update_idletasks()
        w = root.winfo_width()
        h = root.winfo_height()
        x = int(root.winfo_screenwidth()/2 - w/2)
        y = int(root.winfo_screenheight()/2 - h/2)
        root.geometry(f"+{x}+{y}")
        
        root.mainloop()
        return False
        
    except ImportError:
        import ctypes
        msg = f"{header}\n\n{body}\n\nDiscord: https://discord.gg/roseskins\n\nClick OK to open the folder."
        res = ctypes.windll.user32.MessageBoxW(0, msg, title, 0x40031) # MB_OKCANCEL | MB_ICONWARNING | MB_SETFOREGROUND
        if res == 6: # IDYES
            try: subprocess.run(["explorer", str(tools_dir)], check=False)
            except Exception: pass
        elif res == 7: # IDNO
            try: webbrowser.open("https://discord.gg/roseskins")
            except Exception: pass
        return False


def _check_dll_present() -> bool:
    """
    Check if cslol-dll.dll is present and valid. 
    If a valid DLL is found under a different name (e.g. 'cslol-dll (1).dll'),
    it will automatically be renamed to the correct filename.
    """
    import sys
    if sys.platform != "win32":
        return True  # Only relevant on Windows

    tools_dir = _get_tools_dir()
    target_dll_path = tools_dir / "cslol-dll.dll"

    if target_dll_path.exists() and _check_dll_hash(target_dll_path):
        return True

    valid_dll_found = False
    if tools_dir.exists():
        for file_path in tools_dir.glob("*.dll"):
            if file_path == target_dll_path:
                continue
            
            if _check_dll_hash(file_path):
                import shutil
                try:
                    if target_dll_path.exists():
                        target_dll_path.unlink()
                    file_path.rename(target_dll_path)
                    valid_dll_found = True
                    break
                except Exception:
                    try:
                        shutil.copy2(file_path, target_dll_path)
                        valid_dll_found = True
                        break
                    except Exception:
                        pass

    if valid_dll_found:
        return True

    if target_dll_path.exists():
        return _show_dll_dialog(tools_dir, reason="invalid")

    return _show_dll_dialog(tools_dir, reason="missing")

# Setup console first (before any imports that might use it)
from .setup.console import setup_console, redirect_none_streams, start_console_buffer_manager
setup_console()
redirect_none_streams()
start_console_buffer_manager()

# Setup signal handlers
from .core.signals import setup_signal_handlers
setup_signal_handlers()

# Now import everything else
from .setup.arguments import setup_arguments
from .setup.initialization import setup_logging_and_cleanup, initialize_tray_manager
from .core.lockfile import check_single_instance
from .core.initialization import initialize_core_components
from .core.threads import initialize_threads
from .core.lcu_handler import create_lcu_disconnection_handler
from .core.cleanup import perform_cleanup
from .runtime.loop import run_main_loop

import utils.integration.pengu_loader as pengu_loader
from state import AppStatus
from utils.core.logging import get_logger, log_success
from utils.threading.thread_manager import create_daemon_thread
from config import APP_VERSION, MAIN_LOOP_FORCE_QUIT_TIMEOUT_S, set_config_option
from injection.config.config_manager import ConfigManager
from injection.game.game_detector import GameDetector
import time

log = get_logger()


def _setup_pengu_and_injection(lcu, injection_manager, activate_pengu: bool = True) -> None:
    """
    Detect and save leaguepath/clientpath, then setup Pengu Loader and injection system.

    Args:
        activate_pengu: If True, activate Pengu Loader (first startup).
                        If False, skip Pengu activation (reconnection after account swap).
    """
    log.info("Detecting League paths...")

    # Detect paths using GameDetector (only once)
    config_manager = ConfigManager()
    game_detector = GameDetector(config_manager)
    league_path, client_path = game_detector.detect_paths()

    if not league_path or not client_path:
        log.warning("Could not detect League paths, skipping setup")
        return

    # Save paths to config.ini
    log.info("Saving League paths to config.ini: league=%s, client=%s", league_path, client_path)
    config_manager.save_paths(str(league_path), str(client_path))

    # Verify paths are written to config.ini (with retries)
    max_verify_attempts = 5
    verify_interval = 0.2
    paths_verified = False

    for attempt in range(max_verify_attempts):
        saved_league_path = config_manager.load_league_path()
        saved_client_path = config_manager.load_client_path()

        if saved_league_path and saved_client_path:
            # Normalize paths for comparison
            saved_league_normalized = str(Path(saved_league_path).resolve())
            saved_client_normalized = str(Path(saved_client_path).resolve())
            league_normalized = str(league_path.resolve())
            client_normalized = str(client_path.resolve())

            if saved_league_normalized == league_normalized and saved_client_normalized == client_normalized:
                paths_verified = True
                log.info("Paths verified in config.ini")
                break

        if attempt < max_verify_attempts - 1:
            time.sleep(verify_interval)

    if not paths_verified:
        log.warning("Could not verify paths in config.ini, continuing anyway")

    # Set client path in Pengu Loader and activate (skip on reconnection)
    if activate_pengu:
        log.info("Setting client path in Pengu Loader and activating...")
        pengu_loader.activate_on_start(str(client_path))

    # Initialize injection system now (with detected paths already in config.ini)
    log.info("Initializing injection system...")
    injection_manager.initialize_when_ready()


def _update_registry_version() -> None:
    """Update the DisplayVersion in Windows registry to match the current app version.

    After an auto-update the Inno Setup registry entry still shows the version
    that was originally installed.  Writing the current ``APP_VERSION`` on every
    startup keeps "Apps & features" in sync.
    """
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    try:
        import winreg
        key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Rose"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
    except Exception:
        pass


def run_league_unlock(args: Optional[argparse.Namespace] = None,
                      injection_threshold: Optional[float] = None) -> None:
    """Run the core Rose application startup and main loop."""
    # Check for single instance before doing anything else
    check_single_instance()

    # Keep the Windows "Apps & features" version in sync after auto-updates
    _update_registry_version()

    # Safety net: if a previous session didn't shut down cleanly, deactivate
    # Pengu Loader before we re-activate it later in the startup sequence.
    pengu_loader.cleanup_if_dirty()

    # Parse arguments if they were not provided
    if args is None:
        args = setup_arguments()
    
    # Setup logging and cleanup
    setup_logging_and_cleanup(args)

    # Clean up old Pengu Loader IFEO registry entry that can cause client crashes
    # This runs on every startup to handle both fresh installs and updates
    pengu_loader.cleanup_old_pengu_ifeo()

    # Initialize system tray manager immediately to hide console
    tray_manager = initialize_tray_manager(args)
    
    # Initialize app status manager
    app_status = AppStatus(tray_manager)
    log_success(log, "App status manager initialized", "")
    
    # Check initial status (will show locked until all components are ready)
    app_status.update_status(force=True)
    
    # Initialize core components
    lcu, skin_scraper, state, injection_manager = initialize_core_components(args, injection_threshold)
    
    # Configure skin writing based on the final injection threshold (seconds → ms)
    state.skin_write_ms = max(0, int(injection_manager.injection_threshold * 1000))
    state.inject_batch = getattr(args, 'inject_batch', state.inject_batch) or state.inject_batch
    
    # Create LCU disconnection handler
    on_lcu_disconnected = create_lcu_disconnection_handler(state, skin_scraper, app_status)

    # Create LCU reconnection handler. Riot's account-swap flow repairs the
    # client and wipes Pengu's d3d9.dll proxy, so the restarted UX never loads
    # plugins. Always re-activate Pengu to re-drop the proxy and trigger a
    # client restart.
    def on_lcu_reconnected():
        log.info("[Main] LCU reconnected after account swap - re-activating Pengu Loader...")
        try:
            _setup_pengu_and_injection(lcu, injection_manager, activate_pengu=False)
            client_path = ConfigManager().load_client_path()
            if client_path:
                pengu_loader.activate_on_start(str(client_path))
            else:
                log.warning("[Main] Cannot re-activate Pengu — client path unknown")
        except Exception as e:
            log.warning(f"[Main] Failed to re-initialize after reconnection: {e}")

    # Update tray manager quit callback now that state is available
    if tray_manager:
        def updated_tray_quit_callback():
            """Callback for tray quit - set the shared state stop flag"""
            log.info("Setting stop flag from tray quit")
            log.debug(f"[DEBUG] State before setting stop: {state.stop}")
            state.stop = True
            log.debug(f"[DEBUG] State after setting stop: {state.stop}")
            log.info("Stop flag set - main loop should exit")
            
            # Immediately try to trigger any pending console operations that might be blocking
            if sys.platform == "win32":
                try:
                    # Force a console input check to unblock any stuck operations
                    import msvcrt  # Windows-only module
                    if msvcrt.kbhit():
                        msvcrt.getch()  # Consume any pending input
                except (ImportError, OSError) as e:
                    log.debug(f"Console input check failed: {e}")
            
            # Add a timeout to force quit if main loop doesn't exit
            def force_quit_timeout():
                import time
                from .core.signals import force_quit_handler
                time.sleep(MAIN_LOOP_FORCE_QUIT_TIMEOUT_S)
                from .core.state import get_app_state
                app_state = get_app_state()
                if not app_state.shutting_down:
                    log.warning(f"Main loop did not exit within {MAIN_LOOP_FORCE_QUIT_TIMEOUT_S}s - forcing quit")
                    force_quit_handler()
            
            timeout_thread = create_daemon_thread(target=force_quit_timeout, 
                                                 name="ForceQuitTimeout")
            timeout_thread.start()
        
        tray_manager.quit_callback = updated_tray_quit_callback
    
    # Initialize threads (this starts the WebSocket server)
    thread_manager, t_phase, t_ui, t_ws, t_lcu_monitor = initialize_threads(
        lcu, state, args, injection_manager, skin_scraper, app_status, on_lcu_disconnected, on_lcu_reconnected
    )
    
    # Wait for WebSocket status to be active before activating Pengu Loader
    log.info("Waiting for WebSocket status to be active before activating Pengu Loader...")
    while not t_ws.connection.is_connected:
        time.sleep(0.1)
    
    log.info("WebSocket status is active, proceeding with Pengu Loader and injection system setup")
    
    # Setup Pengu Loader and injection system (LCU is already connected when WebSocket is active)
    _setup_pengu_and_injection(lcu, injection_manager)
    
    # Run main loop
    try:
        run_main_loop(state, skin_scraper)
    finally:
        # Perform cleanup
        perform_cleanup(state, thread_manager, tray_manager, injection_manager)


def main() -> None:
    """Program entry point that prepares and launches Rose."""
    # Check for required DLL before anything else
    if not _check_dll_present():
        sys.exit(1)

    args = setup_arguments()
    if sys.platform == "win32":
        if not args.dev:
            try:
                from launcher import run_launcher
                run_launcher(
                    dev_mode=args.dev,
                    test_download_fail=getattr(args, 'test_download_fail', False),
                )
            except ModuleNotFoundError as err:
                print(f"[Launcher] Unable to import launcher module: {err}")
            except Exception as err:  # noqa: BLE001
                print(f"[Launcher] Launcher encountered an error: {err}")

    run_league_unlock(args=args)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Top-level exception handler to catch any unhandled crashes
        import traceback
        import ctypes
        try:
            from utils.core.issue_reporter import report_issue
            report_issue(
                "FATAL_CRASH",
                "error",
                "Rose crashed unexpectedly.",
                details={"type": type(e).__name__, "error": str(e)},
                hint="Check %LOCALAPPDATA%\\Rose\\logs\\ for details.",
            )
        except Exception:
            pass
        
        error_msg = f"""
================================================================================
FATAL ERROR - Rose Crashed
================================================================================
Error: {e}
Type: {type(e).__name__}

Traceback:
{traceback.format_exc()}
================================================================================

This error has been logged. Please report this issue with the log file.
Log location: Check %LOCALAPPDATA%\\Rose\\logs\\
================================================================================
"""
        
        # Try to log the error
        try:
            log = get_logger()
            log.error(error_msg)
        except (AttributeError, RuntimeError, OSError) as e:
            # If logging fails, print to stderr
            print(error_msg, file=sys.stderr)
            print(f"Logging system error: {e}", file=sys.stderr)
        
        # Show error dialog on Windows
        if sys.platform == "win32":
            try:
                ctypes.windll.user32.MessageBoxW(
                    0,
                    f"Rose crashed with an unhandled error:\n\n{str(e)}\n\nError type: {type(e).__name__}\n\nPlease check the log file in:\n%LOCALAPPDATA%\\Rose\\logs\\",
                    "Rose - Fatal Error",
                    0x50010  # MB_OK | MB_ICONERROR | MB_SETFOREGROUND | MB_TOPMOST
                )
            except Exception:
                pass
        
        sys.exit(1)
