# train_agent.py

import os
import re
import math
import json
import time
from datetime import datetime
import numpy as np
from gymnasium import spaces
from stable_baselines3 import SAC
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize, SubprocVecEnv
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.callbacks import BaseCallback
from alpyne.data import SimConfiguration
import alpyne.env
import alpyne.sim
import alpyne.data

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)
LOG_DIR = os.path.join(SCRIPT_DIR, "Logs")
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs("./ModelsRL", exist_ok=True)

# ======================================================================================
# --- Load Configuration from External JSON File ---
# ======================================================================================
try:
    # Look for config.json in the parent directory (AlpyneXtend root)
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config.json")
    with open(config_path, 'r') as f:
        CONFIG = json.load(f)
except FileNotFoundError:
    print("Error: 'config.json' not found. Please ensure the configuration file exists.")
    exit()
# ======================================================================================


class AlpyneEnv(alpyne.env.AlpyneEnv):
    """
    A dynamic Alpyne environment that configures itself based on the loaded CONFIG dictionary.
    Observation/action spaces, reward function, and simulation configuration are all
    derived from the external config.json file.
    """

    def __init__(self, sim: alpyne.sim.AnyLogicSim):
        super().__init__(sim)
        
        # Dynamically create the observation and action spaces from the config
        self.obs_names = list(CONFIG["OBSERVATIONS"].keys())
        self.act_names = list(CONFIG["ACTIONS"].keys())
        
        self.observation_space = spaces.Box(
            low=np.array([v["low"] for v in CONFIG["OBSERVATIONS"].values()], dtype=np.float32),
            high=np.array([v["high"] for v in CONFIG["OBSERVATIONS"].values()], dtype=np.float32),
        )
        self.action_space = spaces.Box(
            low=np.array([v["low"] for v in CONFIG["ACTIONS"].values()], dtype=np.float32),
            high=np.array([v["high"] for v in CONFIG["ACTIONS"].values()], dtype=np.float32),
        )

    def _get_obs(self, status: alpyne.data.SimObservation) -> np.ndarray:
        """Convert observation attributes to a numpy array in the order defined by config."""
        obs_list = []
        for name in self.obs_names:
            # Robust extraction logic (same as _calc_reward)
            val = getattr(status, name, None)
            
            # If not found, check inside status.observation
            if val is None and hasattr(status, 'observation'):
                obs = status.observation
                # Try attribute access first
                val = getattr(obs, name, None)
                # If failed, try dictionary-style get
                if val is None and hasattr(obs, 'get'):
                    val = obs.get(name)

            if val is None:
                # If truly missing, default to 0
                val = 0.0
                
            obs_list.append(float(val))
        return np.array(obs_list, dtype=np.float32)

    def _to_action(self, action: np.ndarray) -> alpyne.data.SimAction:
        """Convert a numpy action array back to named action inputs with correct types."""
        act_dict = {}
        for i, name in enumerate(self.act_names):
            val = float(action[i])
            
            # Determine target type from config variable definitions
            # Smart casting based on name or config
            # We can look up the variable definition in CONFIG['variables'] if available to be precise
            target_type = float
            for v in CONFIG.get('variables', []):
                if v['name'] == name:
                    if v['data_type'] == 'int':
                        target_type = int
                    break

            if target_type == int:
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
        req_vars = expr_data.get("variables", [])
        try:
            for v in req_vars:
                # Try getting directly from status
                val = getattr(status, v, None)
                
                # If not found, check inside status.observation
                if val is None and hasattr(status, 'observation'):
                    obs = status.observation
                    # Try attribute access first
                    val = getattr(obs, v, None)
                    # If failed, try dictionary-style get
                    if val is None and hasattr(obs, 'get'):
                        val = obs.get(v)

                if val is None:
                    print(f"  [REWARD WARNING] Variable '{v}' not found in status or status.observation!")
                    val = 0.0
                context[v] = val
            
            context['math'] = math
            context['abs'] = abs
            context['min'] = min
            context['max'] = max
            
            res = float(eval(expression, {"__builtins__": {}}, context))
            if abs(res) < 1e-9:
                print(f"  [REWARD ZERO] Expr: '{expression}' with ctx {req_vars} -> Result: {res}")
            return res
        except Exception as e:
            print(f"  [REWARD ERROR] Failed to calculate reward: {e}")
            return 0.0
            
    def step(self, action):
        try:
            return super().step(action)
        except Exception as e:
            # Handle AnyLogic stop condition (usually 409 Conflict with STOP info)
            if "409" in str(e) or "STOP_TIMEDATE" in str(e):
                # Simulation finished naturally
                print("Simulation stopped naturally (409 Conflict / STOP_TIMEDATE). Ending episode.")
                obs = np.zeros(self.observation_space.shape, dtype=np.float32)
                return obs, 0.0, True, False, {"error": "Simulation stopped"}
            raise

    def _get_config(self) -> SimConfiguration | None:
        """Build SimConfiguration from config, with type coercion and expression evaluation."""
        # Pass simulation configuration from the config dictionary
        sim_config_dict = CONFIG["SIM_CONFIG"].copy()
        
        # Robustly convert strings to numbers or evaluated expressions
        for k, v in sim_config_dict.items():
            if isinstance(v, str):
                # Try explicit types first
                try:
                    sim_config_dict[k] = int(v)
                    continue
                except ValueError:
                    pass

                try:
                    sim_config_dict[k] = float(v)
                    continue
                except ValueError:
                    pass

                # Check for Randomized Expressions (np.random..., random...)
                if "random" in v or "np." in v:
                    try:
                        # Safe eval context
                        context = {"np": np, "math": math}
                        res = eval(v, {"__builtins__": {}}, context)
                        print(f"Randomized Parameter '{k}': Evaluated '{v}' -> {res}")
                        sim_config_dict[k] = res
                    except Exception as e:
                        print(f"Warning: Failed to evaluate randomized parameter '{k}': {e}")
                        
        # Iteratively remove fields not present in the AnyLogic RL Experiment specification
        while True:
            try:
                return SimConfiguration(**sim_config_dict)
            except Exception as e:
                # Handle alpyne.errors.NotAFieldException without explicitly importing it
                if type(e).__name__ == 'NotAFieldException':
                    msg = str(e)
                    # Extract the invalid field name from the error message
                    # Error format: "'nCellsInRow' not in SimConfiguration spec; options: [...]"
                    match = re.search(r"'([^']+)' not in SimConfiguration spec", msg)
                    if match:
                        bad_key = match.group(1)
                        print(f"Warning: Removing invalid configuration parameter '{bad_key}' "
                              f"from SimConfiguration (not exposed in AnyLogic RL Experiment).")
                        sim_config_dict.pop(bad_key, None)
                else:
                    raise
            else:
                # If it's another error, we can't handle it automatically
                raise


class ReproducibleAlpyneEnv(AlpyneEnv):
    """
    Wrapper to ensure AnyLogic simulation uses a deterministic seed derived from
    a base seed and the environment rank. This couples AnyLogic randomness to the
    RL agent's seed for full reproducibility across parallel environments.
    """

    def __init__(self, sim, base_seed, rank):
        super().__init__(sim)
        self.base_seed = base_seed
        self.rank = rank

    def reset(self, **kwargs):
        # Deterministic Seed per Environment Rank
        # User request: "The Seed should stay the same across the entire training! The only logic... is that the Seeds are not the same across parallel environments."
        # So Env 0 -> Seed X, Env 1 -> Seed X+1, etc. ALWAYS.
        episode_seed = self.base_seed + self.rank if self.base_seed is not None else 0
        
        # Log the seed for verification (Console only)
        print(f"[Env {self.rank}] Resetting with Static Seed: {episode_seed}")

        if "options" not in kwargs or kwargs["options"] is None:
            kwargs["options"] = {}
             
        # Inject seed into options for Alpyne to pick up
        kwargs["options"].setdefault('engine_overrides', {})
        kwargs["options"]['engine_overrides']['seed'] = episode_seed

        # Remove top-level engine_overrides if present to avoid conflicts
        kwargs.pop('engine_overrides', None)

        return super().reset(**kwargs)


def make_env(rank: int, seed: int = 0):
    """
    Factory function that creates a single environment instance.

    :param rank: Index of the subprocess (used for unique seeding).
    :param seed: Base seed for the RNG.
    """
    def _init():
        sim = alpyne.sim.AnyLogicSim(
            model_path=CONFIG["MODEL_PATH"],
            java_exe=CONFIG["JAVA_EXE_PATH"],
            log_dir=LOG_DIR,
            **CONFIG["ALPYNE_SIM_SETTINGS"],
        )
        # Use ReproducibleAlpyneEnv to ensure unique seeds per environment
        # AnyLogic simulates with random seeds by default, but we want control.
        env = ReproducibleAlpyneEnv(sim, base_seed=seed, rank=rank)
        
        # Wrap the environment with a monitor for logging episode statistics
        return Monitor(env)
    return _init


class DetailedTensorboardCallback(BaseCallback):
    """
    Custom callback for logging additional insights to TensorBoard.
    Logs:
    - Hyperparameters (Text Summary)
    - Action Distributions (Histogram)
    - Observation Distributions (Histogram) - Split into Raw and Normalized
    """

    def __init__(self, action_names, obs_names, verbose=0, log_freq=1000):
        super().__init__(verbose)
        self.log_freq = log_freq
        self.action_names = action_names
        self.obs_names = obs_names
        self.hparams_logged = False  # Prevent duplicate logging

    def _on_training_start(self):
        # Log Hyperparameters as Text (Once)
        if self.hparams_logged:
            return

        # Note: We access the model's configuration
        hparams = {
            "Policy": str(self.model.policy_class),
            "Learning Rate": str(self.model.learning_rate),
            "Gamma": str(self.model.gamma),
            "Tau": str(self.model.tau),
            "Batch Size": str(self.model.batch_size),
            "Train Freq": str(self.model.train_freq),
            "Gradient Steps": str(self.model.gradient_steps),
            "Ent Coef": str(self.model.ent_coef),
            "Base Seed": str(self.model.seed),
            "Env Seeds": str([self.model.seed + i for i in range(self.model.n_envs)]),
            "Num Envs": str(self.model.n_envs),
            "Normalized Obs": str(CONFIG["TRAINING"].get("norm_obs", True)),
            "Normalized Reward": str(CONFIG["TRAINING"].get("norm_reward", True)),
        }
        
        # Format as Markdown Table
        table = "| Parameter | Value |\n|---|---|\n"
        for k, v in hparams.items():
            table += f"| {k} | {v} |\n"
            
        self.logger.record("hparams/config", table, exclude=("stdout", "log", "json", "csv"))
        self.hparams_logged = True

    def _on_step(self) -> bool:
        if self.n_calls % self.log_freq == 0:
            # --- LOG ACTIONS ---
            if 'actions' in self.locals:
                actions = self.locals['actions']
                # actions is (n_envs, action_dim)
                for i in range(actions.shape[1]):
                    name = self.action_names[i] if i < len(self.action_names) else f"Action_{i}"
                    vals = actions[:, i]
                    
                    # Scalar (Mean)
                    self.logger.record(f"actions/{name}_mean", np.mean(vals),
                                       exclude=("stdout", "log", "json", "csv"))

                    # Distribution
                    self.logger.record(f"actions_dist/{name}", vals,
                                       exclude=("stdout", "log", "json", "csv"))

            # --- LOG OBSERVATIONS ---
            if 'new_obs' in self.locals:
                obs_norm = self.locals['new_obs']
                obs_raw = obs_norm.copy()
                
                # Check for Normalization
                vec_norm = self.model.get_vec_normalize_env()
                is_normalized = vec_norm is not None
                
                if is_normalized:
                    # unnormalize_obs returns the original observation space values
                    obs_raw = vec_norm.unnormalize_obs(obs_norm)

                # obs is (n_envs, obs_dim)
                if isinstance(obs_raw, np.ndarray):
                    for i in range(obs_raw.shape[1]):
                        name = self.obs_names[i] if i < len(self.obs_names) else f"Obs_{i}"
                        
                        # --- RAW Logs (Category: observations_raw) ---
                        vals_raw = obs_raw[:, i]
                        # Scalar
                        self.logger.record(f"observations_raw/{name}_mean", np.mean(vals_raw),
                                           exclude=("stdout", "log", "json", "csv"))
                        # Distribution
                        self.logger.record(f"observations_dist_raw/{name}", vals_raw,
                                           exclude=("stdout", "log", "json", "csv"))

                        # --- NORMALIZED Logs (Category: observations_norm) ---
                        if is_normalized:
                            vals_norm = obs_norm[:, i]
                            # Scalar
                            self.logger.record(f"observations_norm/{name}_mean", np.mean(vals_norm),
                                               exclude=("stdout", "log", "json", "csv"))
                            # Distribution
                            self.logger.record(f"observations_dist_norm/{name}", vals_norm,
                                               exclude=("stdout", "log", "json", "csv"))
        return True


class BestEpisodeCallback(BaseCallback):
    """Callback to track the episode with the best cumulative reward."""

    def __init__(self, verbose=0):
        super().__init__(verbose)
        self.best_reward = -float('inf')
        self.best_episode_number = 0
        self.total_episodes_counted = 0

    def _on_step(self) -> bool:
        # Check for episode completion in the 'infos' dictionary
        # 'infos' is a list of dicts, one per env
        for info in self.locals.get("infos", []):
            if "episode" in info:
                self.total_episodes_counted += 1
                reward = info["episode"]["r"]
                
                if reward > self.best_reward:
                    self.best_reward = reward
                    self.best_episode_number = self.total_episodes_counted
                    if self.verbose > 0:
                        print(f"New Best Reward: {reward:.2f} at Episode {self.best_episode_number}")
        return True


def get_next_model_index(directory, prefix):
    """Find the next available index for model checkpoint filenames."""
    existing_files = [f for f in os.listdir(directory) if f.startswith(prefix) and f.endswith(".zip")]
    if not existing_files:
        return 1
    indices = []
    for f in existing_files:
        try:
            index = int(f.split("_")[-1].split(".")[0])
            indices.append(index)
        except ValueError:
            continue
    return max(indices) + 1 if indices else 1


if __name__ == "__main__":
    # Create a vectorized environment
    # Use SubprocVecEnv if n_envs > 1 for true parallelism, else DummyVecEnv (faster for single)
    n_envs = CONFIG["TRAINING"]["n_envs"]
    base_seed = CONFIG["RL_AGENT_SETTINGS"].get("seed", 42)
    
    # Prepare environment constructors with ranks and seeds
    env_fns = [make_env(rank=i, seed=base_seed) for i in range(n_envs)]
    
    vec_env_cls = SubprocVecEnv if n_envs > 1 else DummyVecEnv
    
    # Instantiate VecEnv directly since we have a list of callables
    env = vec_env_cls(env_fns)
    
    # Normalize observations and rewards (Configurable)
    # Default to True for backward compatibility if not in config
    norm_obs = CONFIG["TRAINING"].get("norm_obs", True)
    norm_reward = CONFIG["TRAINING"].get("norm_reward", True)
    
    if norm_obs or norm_reward:
        print(f"Normalization Enabled: Obs={norm_obs}, Reward={norm_reward}")
        env = VecNormalize(env, norm_obs=norm_obs, norm_reward=norm_reward)
    else:
        print("Normalization Disabled.")

    sac_params = CONFIG["SAC_PARAMS"].copy()
    agent_settings = CONFIG["RL_AGENT_SETTINGS"].copy()
    
    tensorboard_log = None
    if CONFIG["TRAINING"].get("use_tensorboard", False):
        tensorboard_log = os.path.join(SCRIPT_DIR, "..", "tensorboard_logs")
        os.makedirs(tensorboard_log, exist_ok=True)
        print(f"TensorBoard logging enabled at: {tensorboard_log}")

    # Use unique log name to prevent overwrites (SAC_YYYYMMDD_HHMMSS)
    tb_log_name = f"SAC_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    model = SAC(
        env=env,
        policy=agent_settings.pop("policy"),
        policy_kwargs=dict(net_arch=sac_params.pop("policy_net_arch")),
        learning_starts=sac_params.pop("learning_starts") * CONFIG["TRAINING"]["n_envs"],
        tensorboard_log=tensorboard_log,
        **agent_settings,
        **sac_params,
    )
    
    total_episodes = CONFIG["TRAINING"]["total_episodes"]
    timesteps_per_episode = CONFIG["TRAINING"]["steps_per_episode"]
    start_time = time.time()
    # Get max duration limit (convert minutes to seconds)
    max_duration_min = float(CONFIG["TRAINING"].get("max_duration", 0))
    max_duration_sec = max_duration_min * 60
    print("--- Starting Training ---")
    
    # Setup Callbacks
    callbacks = []
    if CONFIG["TRAINING"].get("extended_logging", False):
        print("Enabling Extended Logging (HParams, Distributions)...")
        # Extract names from config
        act_names = list(CONFIG["ACTIONS"].keys())
        obs_names = list(CONFIG["OBSERVATIONS"].keys())
        
        # Get frequency from config, default to 1000
        try:
            log_freq = int(CONFIG["TRAINING"].get("extended_logging_freq", 10))
        except ValueError:
            log_freq = 1000
            
        print(f"Extended Logging Enabled (Freq: {log_freq} steps)...")
        callbacks.append(DetailedTensorboardCallback(
            action_names=act_names, obs_names=obs_names, log_freq=log_freq))

    best_reward_callback = BestEpisodeCallback()
    callbacks.append(best_reward_callback)

    for episode in range(total_episodes):
        model.learn(
            total_timesteps=timesteps_per_episode,
            progress_bar=True,
            reset_num_timesteps=CONFIG["TRAINING"].get("reset_num_timesteps", False),
            tb_log_name=tb_log_name,
            callback=callbacks,
        )
        
        saved_status = "Skipped"
        if CONFIG["TRAINING"].get("save_models", False):
            next_index = get_next_model_index("./ModelsRL", "SAC_model")
            model_filename = f"./ModelsRL/SAC_model_{next_index:03d}.zip"
            model.save(model_filename)
            
            # Save the normalization statistics
            env.save(os.path.join("./ModelsRL", "vec_normalize.pkl"))
            print(f"Saved checkpoint: {model_filename}")
            saved_status = model_filename
        
        print(f"--- Episode {episode + 1}/{total_episodes} --- "
              f"Time: {time.time() - start_time:.2f}s --- "
              f"Saved: {saved_status} ---")

        # --- Time Limit Check ---
        # If max_duration is set (greater than 0) and we exceeded it
        elapsed_time = time.time() - start_time
        if max_duration_sec > 0 and elapsed_time >= max_duration_sec:
            print(f"\n[STOP] Max training duration of {max_duration_min} minutes reached.")
            break

    # --- SAVE FINAL MODEL (ALWAYS) ---
    print("Saving final model...")
    model_path = CONFIG.get("MODEL_PATH", "UnknownModel")
    model_name = os.path.splitext(os.path.basename(model_path))[0]
    timestamp = time.strftime("%Y%m%d_%H%M")
    final_model_filename = f"./ModelsRL/{model_name}_{timestamp}_final.zip"
    model.save(final_model_filename)

    # Save normalization statistics if the environment supports it
    if hasattr(env, 'save'):
        # Save vec_normalize with the same naming convention for easier matching
        norm_filename = f"./ModelsRL/{model_name}_{timestamp}_vec_normalize.pkl"
        env.save(norm_filename)
    print(f"Final model saved to: {final_model_filename}")

    # --- CLEANUP ---
    try:
        env.close()
    except Exception as e:
        print(f"Warning: Error closing environments: {e}")

    # --- Print Best Episode Log ---
    if best_reward_callback.best_episode_number > 0:
        print("\n" + "=" * 40)
        print(" BEST EPISODE SUMMARY")
        print("=" * 40)
        print(f" Best Reward:  {best_reward_callback.best_reward:.2f}")
        print(f" Episode #:    {best_reward_callback.best_episode_number}")
        print("=" * 40 + "\n")
    else:
        print("\n[Info] No episodes completed fully during this session.\n")

    print("--- Training Complete ---")
