# config_utils.py
"""
Utilities for generating and updating config.json from scan results
and user-selected variable assignments.
"""

import json
from pathlib import Path


def load_json(filepath):
    """Load and return a parsed JSON file, or None on error."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {filepath}")
        return None
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in file: {filepath}")
        return None


def save_json(filepath, data):
    """Write data to a JSON file with indentation."""
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"Successfully saved to {filepath}")


def find_variable_metadata(var_name, scan_results):
    """Find a variable's metadata in the scan results by name."""
    for var in scan_results.get('variables', []):
        if var['name'] == var_name:
            return var
    return None


def _coerce_value(value_str, dtype):
    """
    Convert a string value to the appropriate Python type based on the data type tag.
    Returns the converted value, or the original string if conversion fails.
    """
    try:
        if dtype == 'int':
            return int(float(value_str))  # Handle "30.0" as int
        elif dtype == 'double':
            return float(value_str)
        elif dtype == 'boolean':
            return str(value_str).lower() == 'true'
    except (ValueError, TypeError):
        pass
    return value_str


def _process_configuration(selected_names, scan_results, overrides):
    """Build the SIM_CONFIG dict from selected configuration variables."""
    # NEW: Start with an empty dict to ensure stale parameters are removed
    sim_config = {}

    for var_name in selected_names:
        metadata = find_variable_metadata(var_name, scan_results)
        if not metadata:
            print(f"  [WARN] Metadata not found for {var_name}")
            continue

        dtype = metadata.get('data_type')

        # Check for override
        if var_name in overrides and 'value' in overrides[var_name]:
            val = _coerce_value(overrides[var_name]['value'], dtype)
            if val == overrides[var_name]['value'] and dtype in ('int', 'double'):
                print(f"  [WARN] Could not convert override '{val}' to {dtype} for {var_name}")
            else:
                # Use default value
                default_val = metadata.get('default_value')
                val = _coerce_value(default_val, dtype)
                if val == default_val and dtype == 'int':
                    val = 0
                elif val == default_val and dtype == 'double':
                    val = 0.0

        sim_config[var_name] = val
        print(f"  [CONFIG] {var_name} = {val}")

    return sim_config


def _process_bounds(selected_names, scan_results, overrides, section_label,
                    default_low=0.0, default_high=1.0):
    """Build a bounds dict (low/high) for action or observation variables."""
    result = {}

    for var_name in selected_names:
        metadata = find_variable_metadata(var_name, scan_results)
        if metadata:
            bounds = metadata.get('bounds', {})
            
            # Check for overrides
            if var_name in overrides:
                low = float(overrides[var_name].get('low', bounds.get('suggested_min', default_low)))
                high = float(overrides[var_name].get('high', bounds.get('suggested_max', default_high)))
            else:
                low = bounds.get('suggested_min', default_low)
                if low is None:
                    low = default_low
                high = bounds.get('suggested_max', default_high)
                if high is None:
                    high = default_high

            result[var_name] = {"low": float(low), "high": float(high)}
            print(f"  [{section_label}] {var_name} (low={low}, high={high})")
        else:
            print(f"  [WARN] Metadata not found for {var_name}")
            # Fallback
            result[var_name] = {"low": default_low, "high": default_high}
            
    return result


def update_config(selected_vars, scan_results, config, overrides=None):
    """
    Update the configuration dictionary based on selected variables and scan results.
    Returns the updated config dictionary.
    """
    if overrides is None:
        overrides = {}

    config_names = selected_vars.get('configuration', [])
    action_names = selected_vars.get('actions', [])
    obs_names = selected_vars.get('observations', [])

    # 2. Process Configuration Parameters
    print(f"Processing {len(config_names)} configuration parameters...")
    config['SIM_CONFIG'] = _process_configuration(config_names, scan_results, overrides)

    # 3. Process Actions
    print(f"Processing {len(action_names)} actions...")
    config['ACTIONS'] = _process_bounds(
        action_names, scan_results, overrides, "ACTION",
        default_low=0.0, default_high=1.0)

    # 4. Process Observations
    print(f"Processing {len(obs_names)} observations...")
    config['OBSERVATIONS'] = _process_bounds(
        obs_names, scan_results, overrides, "OBSERVATION",
        default_low=-1e9, default_high=1e9)

    return config


def main():
    """Load inputs, update config.json, and save the result."""
    # Define file paths
    base_dir = Path(__file__).parent
    selected_vars_path = base_dir / "2_SelectedVariables.json"
    scan_results_path = base_dir / "Logs" / "structured_scan_results.json"
    config_path = base_dir / "config.json"

    print("--- Starting Configuration Generation ---")

    # 1. Load input files
    selected_vars = load_json(selected_vars_path)
    scan_results = load_json(scan_results_path)
    config = load_json(config_path)

    if not (selected_vars and scan_results and config):
        print("Aborting: Could not load all necessary files.")
        return

    # Update config
    updated_config = update_config(selected_vars, scan_results, config)

    # 5. Save
    save_json(config_path, updated_config)

    print("--- Configuration Generation Complete ---")


if __name__ == "__main__":
    main()

