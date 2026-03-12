# test_agent.py

import os
import sys
import math
import json
import argparse

import numpy as np
from gymnasium import spaces
from stable_baselines3 import SAC, PPO, DQN
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
from alpyne.data import SimConfiguration
import alpyne.env
import alpyne.sim
import alpyne.data

# --- Setup Paths ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

# --- Load Config ---
CONFIG_PATH = os.path.join(SCRIPT_DIR, "..", "config.json")
try:
    with open(CONFIG_PATH, "r") as f:
        CONFIG = json.load(f)
except FileNotFoundError:
    print(f"CRITICAL: config.json not found at {CONFIG_PATH}")
    sys.exit(1)


class AlpyneEnv(alpyne.env.AlpyneEnv):
    """
    Dynamic Alpyne environment for evaluation.
    Must match the training environment definition exactly.
    """

    def __init__(self, sim: alpyne.sim.AnyLogicSim):
        super().__init__(sim)
        self.obs_names = list(CONFIG.get("OBSERVATIONS", {}).keys())
        self.act_names = list(CONFIG.get("ACTIONS", {}).keys())

        obs_low = np.array(
            [float(v.get("low", -1.0)) for v in CONFIG.get("OBSERVATIONS", {}).values()], dtype=np.float32
        )
        obs_high = np.array(
            [float(v.get("high", 1.0)) for v in CONFIG.get("OBSERVATIONS", {}).values()], dtype=np.float32
        )
        self.observation_space = spaces.Box(low=obs_low, high=obs_high)

        act_low = np.array([float(v.get("low", -1.0)) for v in CONFIG.get("ACTIONS", {}).values()], dtype=np.float32)
        act_high = np.array([float(v.get("high", 1.0)) for v in CONFIG.get("ACTIONS", {}).values()], dtype=np.float32)
        self.action_space = spaces.Box(low=act_low, high=act_high)

    def _get_config(self) -> SimConfiguration | None:
        """Build SimConfiguration, evaluating any randomized parameter expressions."""
        sim_config = CONFIG.get("SIM_CONFIG", {}).copy()

        for k, v in sim_config.items():
            if isinstance(v, str) and ("np." in v or "random" in v):
                try:
                    sim_config[k] = eval(v, {"__builtins__": {}}, {"np": np, "math": math})
                except Exception as e:
                    print(f"Warning: Failed to evaluate {k}={v}: {e}")

        return SimConfiguration(**sim_config)

    def _get_obs(self, status: alpyne.data.SimObservation) -> np.ndarray:
        """Convert observation attributes to a numpy array in the order defined by config."""
        obs_list = []
        for name in self.obs_names:
            val = getattr(status, name, None)
            if val is None and hasattr(status, "observation"):
                val = status.observation.get(name, 0.0)
            obs_list.append(float(val) if val is not None else 0.0)
        return np.array(obs_list, dtype=np.float32)

    def _to_action(self, action: np.ndarray) -> alpyne.data.SimAction:
        """Convert a numpy action array back to named action inputs with correct types."""
        act_dict = {}
        vars_meta = CONFIG.get("variables", [])

        for i, name in enumerate(self.act_names):
            val = float(action[i])

            is_int = any(v["name"] == name and v.get("data_type") == "int" for v in vars_meta)
            if is_int:
                val = int(round(val))
            act_dict[name] = val

        return alpyne.data.SimAction(**act_dict)

    def _is_terminal(self, status: alpyne.data.SimObservation) -> bool:
        return False

    def _is_truncated(self, status: alpyne.data.SimObservation) -> bool:
        return False

    def _calc_reward(self, status: alpyne.data.SimObservation) -> float:
        """Evaluate the reward function expression from config against current status."""
        if "REWARD_FUNCTION" not in CONFIG:
            return 0.0

        expr_data = CONFIG["REWARD_FUNCTION"]
        expression = expr_data.get("expression", "0")

        context = {}
        try:
            for v in expr_data.get("variables", []):
                val = getattr(status, v, None)
                if val is None and hasattr(status, "observation"):
                    val = status.observation.get(v)
                if val is None:
                    val = 0.0
                context[v] = val

            context["math"] = math
            context["abs"] = abs
            context["min"] = min
            context["max"] = max

            return float(eval(expression, {"__builtins__": {}}, context))
        except Exception as e:
            print(f"  [REWARD ERROR] {e}")
            return 0.0

    def step(self, action):
        try:
            return super().step(action)
        except Exception as e:
            if "409" in str(e) or "STOP_TIMEDATE" in str(e):
                obs = np.zeros(self.observation_space.shape, dtype=np.float32)
                return obs, 0.0, True, False, {"error": "Simulation stopped naturally"}
            raise


def _find_vec_normalize_path(model_path):
    """
    Locate the VecNormalize statistics file matching a given model checkpoint.
    Searches by naming convention first, then falls back to generic filenames.
    """
    model_dir = os.path.dirname(model_path)
    model_filename = os.path.basename(model_path)

    if model_filename.endswith("_final.zip"):
        expected_pkl_name = model_filename.replace("_final.zip", "_vec_normalize.pkl")
    else:
        base_name = os.path.splitext(model_filename)[0]
        expected_pkl_name = f"{base_name}_vec_normalize.pkl"

    # Check in the model directory with the expected name
    vec_norm_path = os.path.join(model_dir, expected_pkl_name)
    if os.path.exists(vec_norm_path):
        return vec_norm_path

    # Fallback: generic name in model directory
    candidate = os.path.join(model_dir, "vec_normalize.pkl")
    if os.path.exists(candidate):
        return candidate

    # Fallback: generic name in parent directory
    candidate = os.path.join(os.path.dirname(model_dir), "vec_normalize.pkl")
    if os.path.exists(candidate):
        return candidate

    return None


def run_test(model_path, num_episodes=5, deterministic=True):
    """Run evaluation episodes with a trained model and print summary statistics."""
    print(f"\n--- ALPYNE-XTEND EVALUATION ---")
    print(f"Model: {model_path}")

    # Initialize simulation
    print("Initializing AnyLogic Simulation...")
    try:
        sim = alpyne.sim.AnyLogicSim(
            model_path=CONFIG["MODEL_PATH"],
            java_exe=CONFIG["JAVA_EXE_PATH"],
            log_dir=os.path.join(SCRIPT_DIR, "..", "Logs"),
            **CONFIG.get("ALPYNE_SIM_SETTINGS", {}),
        )
    except Exception as e:
        print(f"CRITICAL: Failed to start simulation: {e}")
        return

    env = DummyVecEnv([lambda: AlpyneEnv(sim)])

    # Load normalization statistics if available
    vec_norm_path = _find_vec_normalize_path(model_path)
    if vec_norm_path:
        print(f"Loading Normalization Stats: {vec_norm_path}")
        env = VecNormalize.load(vec_norm_path, env)
        env.training = False
        env.norm_reward = False
    else:
        print("No normalization stats found. Using raw inputs.")

    # Load model (algorithm type from config, default SAC)
    algo_key = CONFIG.get("TRAINING", {}).get("algorithm", "SAC")
    algo_map = {"SAC": SAC, "PPO": PPO, "DQN": DQN}
    algo_class = algo_map.get(algo_key, SAC)

    print(f"Loading {algo_class.__name__} policy...")
    try:
        model = algo_class.load(model_path, env=env)
    except Exception as e:
        print(f"Error loading model: {e}")
        env.close()
        return

    # Evaluation loop
    print(f"\nRunning {num_episodes} evaluation episodes...\n")

    results = []
    all_actions_recorded = []

    for ep in range(num_episodes):
        obs = env.reset()
        done = False
        steps = 0
        ep_reward = 0

        while not done:
            action, _states = model.predict(obs, deterministic=deterministic)

            if len(action.shape) > 1:
                all_actions_recorded.append(action[0])
            else:
                all_actions_recorded.append(action)

            obs, reward, done, info = env.step(action)
            ep_reward += reward[0]
            steps += 1

        print(f"Episode {ep + 1}/{num_episodes} finished. Steps: {steps}, Total Reward: {ep_reward:.2f}")
        results.append(ep_reward)

    # Print summary
    print(f"\n--- Evaluation Summary ---")
    print(f"Average Reward: {np.mean(results):.2f} (±{np.std(results):.2f})")

    if all_actions_recorded:
        avg_actions = np.mean(all_actions_recorded, axis=0)

        print("\n--- Average Action Values ---")
        print(f"{'Action Name':<25} | {'Min':<10} | {'Max':<10} | {'Avg Value':<15}")
        print("-" * 70)

        act_config = CONFIG.get("ACTIONS", {})
        act_names = list(act_config.keys())

        for i, name in enumerate(act_names):
            bounds = act_config.get(name, {})
            low = bounds.get("low", -float("inf"))
            high = bounds.get("high", float("inf"))
            print(f"{name:<25} | {str(low):<10} | {str(high):<10} | {avg_actions[i]:<15.4f}")
        print("-" * 70)

    print("--- EVALUATION COMPLETE ---")
    env.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate a trained RL agent in an AnyLogic simulation.")
    parser.add_argument("--model", type=str, required=True, help="Path to the trained model (.zip)")
    parser.add_argument("--episodes", type=int, default=5, help="Number of evaluation episodes")
    parser.add_argument("--stochastic", action="store_true", help="Use stochastic policy instead of deterministic")
    args = parser.parse_args()

    run_test(args.model, args.episodes, deterministic=not args.stochastic)
