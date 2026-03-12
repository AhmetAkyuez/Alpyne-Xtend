# scan_server.py
import os
import sys
import re
import json
import time
import glob
import atexit
import signal
import argparse
import subprocess
import traceback

from alpyne.sim import AnyLogicSim

RESULTS_TIMEOUT_SEC = 120
POLL_INTERVAL_SEC = 1
LOG_POLL_INTERVAL_SEC = 5


def _find_newest_results(log_dir):
    """Return the path to the most recently modified raw_scan_results log, or None."""
        files = glob.glob(os.path.join(log_dir, "raw_scan_results*.log"))
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def _parse_raw_log(log_path, json_path):
    """Parse a raw scan results log file and write structured JSON output."""
    print(f"Parsing raw logs from {log_path}...")
    variables = []

    try:
        with open(log_path, 'r') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Failed to read log file: {e}")
        return

    section = None
    for line in lines:
        line = line.strip()
        if not line:
            continue

        if "--- Inputs" in line:
            section = "inputs"
            continue
        elif "--- Outputs" in line:
            section = "outputs"
            continue
        elif "--- Other Descriptions" in line:
            section = "other"
            continue
        elif line.startswith("--- ") and "---" in line[4:]:
            section = None
            continue

        if section == "inputs":
            if "|" not in line or "Parameter Name" in line:
                continue
            parts = line.split('|')
            name = parts[0].strip()
            meta = parts[1].strip()

            dtype = "double"
            default = "0.0"

            m = re.search(r"Type:\s*(\w+)", meta)
            if m:
                dtype = m.group(1)

            m = re.search(r"Default:\s*(.+)", meta)
            if m:
                default = m.group(1)

            variables.append({
                "name": name,
                "category": "input",
                "data_type": dtype,
                "default_value": default,
                "path": f"root.{name}",
                "is_exposed": False,
                "suggested_as": ["configuration"],
            })

        elif section == "outputs":
            if "|" not in line or "Element Path" in line:
                continue
            parts = line.split('|')
            path = parts[0].strip()
            meta = parts[1].strip()

            if path.startswith("root._"):
                continue

            # Extract Raw Type (Simplified for dumb reporting)
            type_str = "unknown"
            if ":" in meta:
                _, type_str = meta.split(':', 1)
                type_str = type_str.strip()

            name = path.split('.')[-1].replace("()", "")

            variables.append({
                "name": name,
                "category": "output",
                "data_type": type_str,
                "default_value": "",
                "path": path,
                "is_exposed": False,
                "suggested_as": ["observation"],
            })

        elif section == "other":
            # Pass through natively exposed items
            if ":" in line:
                type_label, content = line.split(":", 1)
                names = [x.strip() for x in content.strip().split(",") if x.strip()]

                usage_map = {
                    "Configuration": "configuration",
                    "Observation": "observation",
                    "Action": "action",
                }
                sys_usage = usage_map.get(type_label, "unknown")

                for name in names:
                    variables.append({
                        "name": name,
                        "category": "exposed",
                        "data_type": "double",
                        "default_value": "0.0",
                        "path": name,
                        "is_exposed": True,
                        "suggested_as": [sys_usage],
                    })

    data = {
        "scan_timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        "model_name": "Main",
        "variables": variables,
        "rl_experiment_current_state": {"configuration": [], "observations": [], "actions": []},
    }

    try:
        with open(json_path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Successfully generated {json_path}")
    except Exception as e:
        print(f"Failed to write JSON: {e}")


def _try_recover_results(log_dir):
    """Attempt to parse scan results that may have been generated despite an error."""
    files = glob.glob(os.path.join(log_dir, "raw_scan_results*.log"))
    if not files:
        return False

    newest = max(files, key=os.path.getmtime)
            # Check if it's somewhat recent (e.g. last 2 mins)
    if time.time() - os.path.getmtime(newest) < RESULTS_TIMEOUT_SEC:
                print(f"Scan results found at {newest} despite error.")
                json_path = os.path.join(log_dir, "structured_scan_results.json")
        _parse_raw_log(newest, json_path)
        return True
                
    return False


def _kill_sim_process(sim):
    """Attempt to terminate the simulation's Java process."""
    try:
        if sim and hasattr(sim, '_proc') and sim._proc:
            print(f"Attempting to kill Java process {sim._proc.pid}...")
            # On Windows, SIGTERM is an alias for TerminateProcess
            os.kill(sim._proc.pid, signal.SIGTERM)
    except Exception as e:
        print(f"Failed to kill Java process: {e}")


def run_scan(model_path, java_path="java", log_dir="./Logs"):
    """
    Launch an AnyLogic simulation in scan mode, wait for the raw results log,
    and parse it into a structured JSON file.
    """
    print("--- Starting Scan ---")
    print(f"Model: {model_path}")
    print(f"Java:  {java_path}")
    print(f"Logs:  {log_dir}")
    print(f"Python Executable: {sys.executable}")
    print(f"Python Path: {sys.path}")
    
    # Ensure log directory exists
    log_dir = os.path.abspath(log_dir)
    os.makedirs(log_dir, exist_ok=True)
    
    # Diagnostics
    if not os.path.exists(model_path):
        print(f"Error: Model file not found at {model_path}")
        sys.exit(1)
            
    # Validate Java installation
    print(f"Checking Java version at: {java_path}")
    try:
        subprocess.check_call([java_path, "-version"])
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(f"Error: Java executable not found or not working at '{java_path}'")
        sys.exit(1)

    # Normalize Java path casing for AnyLogicSim validation
    # AnyLogicSim (Mod11) enforces strict "java.exe" filename check
    if os.path.basename(java_path).lower() == "java.exe":
        java_path = os.path.join(os.path.dirname(java_path), "java.exe")

    # Ensure model path is absolute before changing CWD
    model_path = os.path.abspath(model_path)
    
    # AnyLogicSim (Mod11) ignores log_dir and writes to ./Logs relative to CWD.
    # We must change CWD to the parent of the desired log_dir so that ./Logs lands in the right place.
    desired_cwd = os.path.dirname(log_dir)
    print(f"Changing CWD to: {desired_cwd}")
    os.chdir(desired_cwd)

    sim = None
    try:
        print(f"Initializing AnyLogicSim with log_dir={log_dir}...")
        sim = AnyLogicSim(
            model_path=model_path,
            java_exe=java_path,
            log_dir=log_dir,
            blocking=False,
            verbose=True,
            max_server_await_time=60.0,
        )
        print("Server started (non-blocking).")

        start_time = time.time()
        results_file = None
        print(f"Waiting for results in: {log_dir}")

        while time.time() - start_time < RESULTS_TIMEOUT_SEC:
            latest = _find_newest_results(log_dir)
            if latest and os.path.getmtime(latest) >= start_time - 10:  # Allow clock skew
                # Wait briefly and check if the file has stabilized (finished writing)
                mtime = os.path.getmtime(latest)
                time.sleep(POLL_INTERVAL_SEC)
                if os.path.getmtime(latest) == mtime:
                    print(f"Scan results file found: {latest}")
                    results_file = latest

                    # Parse and generate JSON
                    json_path = os.path.join(log_dir, "structured_scan_results.json")
                    _parse_raw_log(latest, json_path)
                    break

            # Debug: Print files in log dir periodically
            elapsed = int(time.time() - start_time)
            if elapsed % LOG_POLL_INTERVAL_SEC == 0:
                try:
                    files = os.listdir(log_dir)
                    if files:
                        print(f"Files in log dir: {files}")
                except OSError:
                    pass

            # Check if the Java process has terminated unexpectedly
            if sim._proc and sim._proc.poll() is not None:
                print(f"Java process died with code {sim._proc.returncode}")
                # Try to capture stdout/stderr if possible
                try:
                    stdout, stderr = sim._proc.communicate(timeout=1)
                    print(f"STDOUT: {stdout}")
                    print(f"STDERR: {stderr}")
                except Exception:
                    pass
                break

            time.sleep(POLL_INTERVAL_SEC)
        else:
            print("Timeout waiting for scan results.")
            try:
                print(f"Final check of {log_dir}: {os.listdir(log_dir)}")
            except OSError:
                pass

        # Shut down the simulation server
        print("Stopping server...")
        try: 
            # prevent double-cleanup error by removing the auto-registered handler
            atexit.unregister(sim._quit_app)
            sim._quit_app()
        except Exception:
            # Suppress "Cannot send input" error or other cleanup issues
            pass
        
        print("--- Scan Complete ---")
        
    except Exception as e:
        print(f"Error during scan: {e}")
        traceback.print_exc()
        
        # Attempt to kill lingering Java processes to release file locks
        _kill_sim_process(sim)

        # Check if results were actually generated despite the error
        if _try_recover_results(log_dir):
            print("--- Scan Complete ---")
            sys.exit(0)

        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scan AnyLogic model for variables.")
    parser.add_argument("--model-path", required=True, help="Path to the exported model .zip file")
    parser.add_argument("--java-path", default="java", help="Path to the Java executable")
    parser.add_argument("--log-dir", default="./Logs", help="Directory to store logs")
    
    args = parser.parse_args()
    run_scan(args.model_path, args.java_path, args.log_dir)

