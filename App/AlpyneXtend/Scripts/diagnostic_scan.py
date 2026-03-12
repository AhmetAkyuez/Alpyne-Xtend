# diagnostic_scan.py
"""
Unfiltered diagnostic scan of an AnyLogic model.

Launches the simulation, captures the raw scan log, and parses all discovered
variables (inputs, outputs, exposed RL fields) into a structured JSON file
without applying any type filtering.
"""
import os
import re
import json
import time
import glob
import atexit
import argparse
from alpyne.sim import AnyLogicSim

LOG_WAIT_TIMEOUT_SEC = 60
POLL_INTERVAL_SEC = 1

_USAGE_MAP = {
    "Configuration": "configuration",
    "Observation": "observation",
    "Action": "action",
}


def _wait_for_log(log_dir, sim, start_time):
    """Poll the log directory until a recent raw_scan_results log appears or timeout."""
    while time.time() - start_time < LOG_WAIT_TIMEOUT_SEC:
        files = glob.glob(os.path.join(log_dir, "raw_scan_results*.log"))
        if files:
            latest = max(files, key=os.path.getmtime)
            if os.path.getmtime(latest) > start_time - 5:
                time.sleep(POLL_INTERVAL_SEC)
                return latest

        if sim._proc and sim._proc.poll() is not None:
            break
        time.sleep(POLL_INTERVAL_SEC)

    return None


def _shutdown_sim(sim):
    """Gracefully shut down the simulation process."""
    if sim is None:
        return
    try:
        atexit.unregister(sim._quit_app)
        sim._quit_app()
    except Exception:
        pass


def _parse_raw_log(log_path):
    """
    Parse a raw scan results log into a list of variable dictionaries.
    No type filtering is applied — all discovered variables are preserved.
    """
    with open(log_path, 'r') as f:
        lines = f.readlines()

    variables = []
    section = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Detect section headers
        if "--- Inputs" in line:
            section = "inputs"
            continue
        elif "--- Outputs" in line:
            section = "outputs"
            continue
        elif "--- Other" in line:
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
            
            # Extract defaults
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

            # Extract Raw Type
            type_str = "unknown"
            if ":" in meta:
                _, type_str = meta.split(':', 1)
                type_str = type_str.strip()

            name = path.split('.')[-1].replace("()", "")
            
            # SAVE EVERYTHING. No filtering.
            # We save the complex type string (e.g. "com.anylogic...ResourcePool") so the App can read it.
            variables.append({
                "name": name,
                "category": "output",
                "data_type": type_str,  # <--- The full Java type!
                "path": path,
                "is_exposed": False,
                "suggested_as": ["observation"],
            })
        
        elif section == "other":
            # Parse "Other Descriptions" for exposed Configuration, Observation, Action
            # Format: "Configuration: var1, var2, var3"
            if ":" in line:
                type_label, content = line.split(":", 1)
                type_label = type_label.strip()
                names = [x.strip() for x in content.strip().split(",") if x.strip()]
                sys_usage = _USAGE_MAP.get(type_label, "unknown")

                for name in names:
                    variables.append({
                        "name": name,
                        "category": "exposed",  # Mark as exposed
                        "data_type": "double",  # Default
                        "default_value": "0.0",
                        "path": name,
                        "is_exposed": True,
                        "suggested_as": [sys_usage],
                    })

    return variables


def run_diagnostic_scan(model_path, java_path="java", log_dir="./Logs"):
    """
    Run an unfiltered diagnostic scan of an AnyLogic model and write
    all discovered variables to structured_scan_results.json.
    """
    print("--- DIAGNOSTIC SCAN START ---")
    print(f"Target: {model_path}")
    print(f"Logs:   {log_dir}")

    log_dir = os.path.abspath(log_dir)
    os.makedirs(log_dir, exist_ok=True)
    os.chdir(os.path.dirname(log_dir))

    # Launch simulation in non-blocking mode
    sim = None
    latest_log = None
    try:
        sim = AnyLogicSim(
            model_path=model_path,
            java_exe=java_path,
            log_dir=log_dir,
            blocking=False,
            verbose=False,
            max_server_await_time=30.0,
        )
        print("Waiting for raw log generation...")
        latest_log = _wait_for_log(log_dir, sim, time.time())
    except Exception as e:
        print(f"Simulation error: {e}")
    finally:
        _shutdown_sim(sim)

    if not latest_log:
        print("CRITICAL: No log generated.")
        return

    # Parse log and write structured JSON
    print(f"Parsing {os.path.basename(latest_log)}...")
    variables = _parse_raw_log(latest_log)
    # Save JSON
    json_path = os.path.join(log_dir, "structured_scan_results.json")
    data = {
        "scan_timestamp": time.ctime(),
        "model_name": "Main",
        "variables": variables,
    }
    with open(json_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"Generated unfiltered JSON at: {json_path}")
    print("--- SCAN COMPLETE ---")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unfiltered diagnostic scan of an AnyLogic model.")
    parser.add_argument("--model-path", required=True, help="Path to the exported model .zip file")
    parser.add_argument("--java-path", default="java", help="Path to the Java executable")
    parser.add_argument("--log-dir", default="./Logs", help="Directory to store logs and results")
    args = parser.parse_args()
    
    run_diagnostic_scan(args.model_path, args.java_path, args.log_dir)
