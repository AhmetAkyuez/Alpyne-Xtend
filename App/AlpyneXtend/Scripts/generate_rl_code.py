# generate_rl_code.py
"""
Code Generator for AnyLogic RL Experiment Integration.

Reads structured scan results and generates copy-pasteable Java and Python code
snippets for integrating variables into AnyLogic RL Experiments.
"""

import json
import traceback
from typing import Dict, List, Optional
from pathlib import Path


# Java type mapping for AnyLogic parameter definitions
_JAVA_TYPE_MAP = {
    "double": "double",
    "Double": "double",
    "int": "int",
    "Integer": "int",
    "boolean": "boolean",
    "Boolean": "boolean",
    "String": "String",
    "float": "double",
    "Float": "double",
    "long": "long",
    "Long": "long",
}

# Keyword-based heuristics for reward weight suggestions
_MAXIMIZE_KEYWORDS = ["utilization", "throughput", "produced", "efficiency"]
_MINIMIZE_KEYWORDS = ["time", "delay", "waiting", "cost", "waste"]


class RLCodeGenerator:
    """
    Generates copy-pasteable Java code snippets for AnyLogic RL Experiment blocks
    and corresponding Python configuration snippets.
    """

    def __init__(self, scan_results_path: str):
        """
        Initialize the code generator with scan results.

        Args:
            scan_results_path: Path to structured_scan_results.json

        Raises:
            FileNotFoundError: If scan results file doesn't exist.
            json.JSONDecodeError: If JSON file is malformed.
        """
        scan_path = Path(scan_results_path)
        if not scan_path.exists():
            raise FileNotFoundError(f"Scan results not found: {scan_results_path}")

        with open(scan_path, "r", encoding="utf-8") as f:
            self.scan_data = json.load(f)

        self.variables = self.scan_data.get("variables", [])
        self.model_name = self.scan_data.get("model_name", "Unknown")
        self.scan_timestamp = self.scan_data.get("scan_timestamp", "Unknown")

        print(f"Loaded {len(self.variables)} variables from {self.model_name}")
        print(f"Scan timestamp: {self.scan_timestamp}")

    def get_variable(self, name: str) -> Optional[Dict]:
        """Get variable info by name."""
        return next((v for v in self.variables if v["name"] == name), None)

    # -------------------------------------------------------------------------
    # Java code generation for AnyLogic RL Experiment blocks
    # -------------------------------------------------------------------------

    def generate_configuration_code(self, selected_vars: List[str]) -> Dict[str, str]:
        """Generate Java code for the Configuration block (fields + assignment)."""
        if not selected_vars:
            return {
                "fields": "// No configuration parameters selected.",
                "code": "// No configuration parameters selected.",
            }

        field_lines = []
        code_lines = []
        for var_name in selected_vars:
            var = self.get_variable(var_name)
            if var:
                java_type = self._map_type_to_java(var["data_type"])
                field_lines.append(f"{var_name}\t{java_type}")
                code_lines.append(f"root.{var_name} = {var_name};")

        return {"fields": "\n".join(field_lines), "code": "\n".join(code_lines)}

    def generate_actions_code(self, selected_vars: List[str]) -> Dict[str, str]:
        """Generate Java code for the Actions block (fields + setter calls)."""
        if not selected_vars:
            return {"fields": "// No actions selected.", "code": "// No actions selected."}

        field_lines = []
        code_lines = []
        for var_name in selected_vars:
            var = self.get_variable(var_name)
            if var:
                java_type = self._map_type_to_java(var["data_type"])
                field_lines.append(f"{var_name}\t{java_type}")

                # Remove action prefix if present (e.g., a_bussingTime -> bussingTime)
                clean_name = var_name[2:] if var_name.startswith("a_") else var_name
                # Use setter method format like in the real RL Experiment
                code_lines.append(f"root.set_{clean_name}({var_name});")

        return {"fields": "\n".join(field_lines), "code": "\n".join(code_lines)}

    def generate_observations_code(self, selected_vars: List[str]) -> Dict[str, str]:
        """Generate Java code for the Observations block (fields + access expressions)."""
        if not selected_vars:
            return {"fields": "// No observations selected.", "code": "// No observations selected."}

        field_lines = []
        code_lines = []
        for var_name in selected_vars:
            var = self.get_variable(var_name)
            if var:
                java_type = self._map_type_to_java(var["data_type"])
                field_lines.append(f"{var_name}\t{java_type}")
                # Generate intelligent observation access code
                access_code = self._generate_observation_access(var)
                code_lines.append(f"{var_name} = {access_code};")

        return {"fields": "\n".join(field_lines), "code": "\n".join(code_lines)}

    # -------------------------------------------------------------------------
    # Python / config.json code generation
    # -------------------------------------------------------------------------

    def generate_action_space_definition(self, selected_vars: List[str]) -> str:
        """Generate a JSON snippet defining the action space for config.json."""
        return self._generate_space_definition("ACTIONS", selected_vars, default_high=100)

    def generate_observation_space_definition(self, selected_vars: List[str]) -> str:
        """Generate a JSON snippet defining the observation space for config.json."""
        return self._generate_space_definition("OBSERVATIONS", selected_vars, default_high=1)

    def generate_reward_function_template(self, obs_vars: List[str]) -> str:
        """Generate a template reward function section for config.json."""
        lines = [
            '"REWARD_FUNCTION": {',
            '    "components": [',
        ]

        for i, var_name in enumerate(obs_vars):
            var = self.get_variable(var_name)
            if var:
                weight = self._suggest_reward_weight(var_name)
                comma = "," if i < len(obs_vars) - 1 else ""
                lines.append("        {")
                lines.append(f'            "name": "{var_name}",')
                lines.append(f'            "weight": {weight}')
                lines.append(f"        }}{comma}")

        if not obs_vars:
            lines.append("        // No observations selected")

        lines.append("    ]")
        lines.append("}")
        return "\n".join(lines)

    def generate_config_json_section(self, action_vars: List[str], obs_vars: List[str]) -> str:
        """
        Generate a combined config.json section with actions, observations,
        and reward function definitions.
        """
        parts = [
            self.generate_action_space_definition(action_vars),
            "",
            self.generate_observation_space_definition(obs_vars),
            "",
            self.generate_reward_function_template(obs_vars),
        ]
        return "\n".join(parts)

    # -------------------------------------------------------------------------
    # Composite generation
    # -------------------------------------------------------------------------

    def generate_complete_snippet(
        self,
        config_vars: List[str],
        action_vars: List[str],
        obs_vars: List[str],
    ) -> Dict[str, Dict[str, str]]:
        """
        Generate all code snippets at once.

        Returns:
            Dictionary with keys 'observations', 'actions', 'configuration', 'python_config'.
            The first three contain 'fields' and 'code' sub-dictionaries.
        """
        return {
            "observations": self.generate_observations_code(obs_vars),
            "actions": self.generate_actions_code(action_vars),
            "configuration": self.generate_configuration_code(config_vars),
            "python_config": self.generate_config_json_section(action_vars, obs_vars),
        }

    def save_snippets_to_file(self, snippets: Dict[str, Dict[str, str]], output_path: str):
        """Save all generated snippets to a single text file."""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write(f"CODE SNIPPETS FOR: {self.model_name}\n")
            f.write(f"Generated: {self.scan_timestamp}\n")
            f.write("=" * 80 + "\n\n")

            for section, data in snippets.items():
                f.write("\n" + "=" * 80 + "\n")
                f.write(f"SECTION: {section.upper()}\n")
                f.write("=" * 80 + "\n\n")

                if isinstance(data, dict):
                    f.write("FIELD DEFINITIONS:\n")
                    f.write("-" * 80 + "\n")
                    f.write(data.get("fields", ""))
                    f.write("\n\n")
                    f.write("CODE:\n")
                    f.write("-" * 80 + "\n")
                    f.write(data.get("code", ""))
                else:
                    f.write(data)

                f.write("\n\n")

        print(f"All snippets saved to '{output_path}'")

    def check_conflicts(self, selected_vars: List[str], target_type: str) -> List[str]:
        """
        Check if selected variables conflict with existing RL experiment definitions.

        Returns:
            List of warning messages (empty if no conflicts).
        """
        warnings = []
        for var_name in selected_vars:
            var = self.get_variable(var_name)
            if var and var.get("is_currently_in_rl_experiment", False):
                current_uses = var.get("currently_used_as", [])
                if target_type not in current_uses:
                    current_str = ", ".join(current_uses)
                    warnings.append(
                        f"Warning: {var_name} is already used as {current_str}, adding it as {target_type} too"
                    )
        return warnings

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _generate_space_definition(self, label: str, selected_vars: List[str], default_high: float) -> str:
        """Generate a JSON space definition block (shared logic for actions/observations)."""
        lines = [f'"{label}": {{']

        if not selected_vars:
            lines.append(f"    // No {label.lower()} selected")

        for i, var_name in enumerate(selected_vars):
            var = self.get_variable(var_name)
            if var:
                bounds = var.get("bounds", {})
                low = bounds.get("suggested_min", 0)
                high = bounds.get("suggested_max", default_high)
                comma = "," if i < len(selected_vars) - 1 else ""

                lines.append(f'    "{var_name}": {{')
                lines.append(f'        "low": {low},')
                lines.append(f'        "high": {high}')
                lines.append(f"    }}{comma}")

        lines.append("}")
        return "\n".join(lines)

    @staticmethod
    def _generate_observation_access(var: Dict) -> str:
        """
        Generate Java access code for an observation variable based on its metadata.
        Uses naming conventions to infer utilization calls, statistical methods, etc.
        """
        name = var["name"]
        path = var.get("path", f"root.{name}")

        # Utilization patterns (operator or resource pool)
        if "utilization" in name.lower():
            resource_name = name.replace("o_", "").replace("Utilization", "").replace("utilization", "")
            return f"root.{resource_name}.utilization()"

        # Statistical mean methods (e.g., o_meanProdCycleTime -> root.dataProdCycleTime.mean())
        if name.startswith("o_mean") and "Time" in name:
            # Try to map to a data collection object
            # e.g., o_meanProdCycleTime -> dataProdCycleTime
            clean_name = name.replace("o_mean", "data").replace("mean", "data")
            return f"root.{clean_name}.mean()"

        # Direct field access from path
        if path.startswith("root.") and not path.endswith("()"):
            return path

        # Method call
        if path.endswith("()"):
            return path

        # Remove observation prefix and prepend root
        if name.startswith("o_"):
            return f"root.{name[2:]}"

        # Default: prepend root.
        return f"root.{name}"

    @staticmethod
    def _map_type_to_java(data_type: str) -> str:
        """Map scan result data types to Java types for AnyLogic parameters."""
        type_clean = data_type.replace("<", "").replace(">", "").strip()
        return _JAVA_TYPE_MAP.get(type_clean, "double")  # Default to double

    @staticmethod
    def _suggest_reward_weight(var_name: str) -> float:
        """Suggest an initial reward weight based on variable name heuristics."""
        name_lower = var_name.lower()

        # Things to maximize (positive weights)
        if any(kw in name_lower for kw in _MAXIMIZE_KEYWORDS):
            return 1.0
        # Things to minimize (negative weights)
        if any(kw in name_lower for kw in _MINIMIZE_KEYWORDS):
            return -0.1

        # Default: neutral/small positive
        return 0.5


# ============================================================================
# EXAMPLE USAGE
# ============================================================================


def main():
    """Run the code generator with example variable selections."""

    print("\n" + "=" * 80)
    print("ALPYNE-XTEND: RL CODE SNIPPET GENERATOR")
    print("=" * 80 + "\n")

    # Path to the structured scan results
    scan_file = "Logs/structured_scan_results.json"

    try:
        # Initialize generator
        generator = RLCodeGenerator(scan_file)

        # Define what you want to use (hardcoded for now, GUI later)
        selected_config = ["evaType", "laminatorCapacity"]
        selected_actions = ["bussingTime", "trimmingTime", "framingTime"]
        selected_observations = ["o_flasherOperatorUtilization", "o_panelsProduced", "o_meanProdCycleTime"]

        # Check for conflicts
        print("Checking for conflicts...")
        for warning in generator.check_conflicts(selected_actions, "action"):
            print(warning)

        # Generate all snippets
        snippets = generator.generate_complete_snippet(
            config_vars=selected_config,
            action_vars=selected_actions,
            obs_vars=selected_observations,
        )

        # Print to console
        print("\n" + "=" * 80)
        print("GENERATED CODE SNIPPETS")
        print("=" * 80 + "\n")

        for section, data in snippets.items():
            print(f"\n--- {section.upper()} ---")
            if isinstance(data, dict):
                print("\nField Definitions:")
                print(data.get("fields", ""))
                print("\nCode:")
                print(data.get("code", ""))
            else:
                print(data)
            print()

        # Save to file
        output_file = "rl_code_snippets.txt"
        generator.save_snippets_to_file(snippets, output_file)

        print("\n" + "=" * 80)
        print("GENERATION COMPLETE")
        print("=" * 80)
        print(f"\nNext steps:")
        print(f"   1. Open '{output_file}' to view all generated code")
        print(f"   2. Copy the Java code sections into AnyLogic RL Experiment")
        print(f"   3. Copy the Python sections into your config.json")
        print(f"   4. Export your AnyLogic model")
        print(f"   5. Run your training script\n")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("\nPlease ensure that:")
        print("   1. You have run the Alpyne scan server")
        print("   2. The scan generated 'structured_scan_results.json'")
        print("   3. The file is in the 'Logs' directory")
    except Exception as e:
        print(f"Unexpected error: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()
