# train_bayes_opt.py
"""
Bayesian Optimization for Alpyne-Xtend.

Finds optimal configuration parameters for an AnyLogic model using Bayesian Optimization.
Unlike RL training (SAC), this approach runs simulations to completion without stepping,
evaluates based on final outcomes, and outputs optimal parameter values.
"""

import os
import re
import sys
import json
import math
import time
    import argparse
from datetime import datetime
    
import numpy as np

try:
    from bayes_opt import BayesianOptimization
    from bayes_opt import acquisition
    from bayes_opt.exception import NotUniqueError
    _LEGACY_BAYES_OPT = False
except ImportError:
    try:
        from bayes_opt import BayesianOptimization, UtilityFunction
        from bayes_opt.util import NotUniqueError
        _LEGACY_BAYES_OPT = True
    except ImportError:
        print("Critical Error: bayesian-optimization library not found.")
        print("Install with: pip install bayesian-optimization")
        sys.exit(1)

from alpyne.sim import AnyLogicSim

# --- Path Setup ---

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)
LOG_DIR = os.path.join(SCRIPT_DIR, "Logs")
os.makedirs(LOG_DIR, exist_ok=True)
MODEL_OUT_DIR = os.path.join(SCRIPT_DIR, "ModelsBO")
os.makedirs(MODEL_OUT_DIR, exist_ok=True)

# --- Load Configuration ---

try:
    _config_path = os.path.join(SCRIPT_DIR, "..", "config.json")
    with open(_config_path, 'r') as _f:
        CONFIG = json.load(_f)
except FileNotFoundError:
    print("Error: 'config.json' not found.")
    sys.exit(1)

# Regex pattern for extracting numeric arguments from expressions
_NUM_PATTERN = r"([-+]?\d*\.?\d+)"

# Penalty score assigned to failed simulation runs
_FAILURE_SCORE = -1e9

# ======================================================================================
# --- Parsing & Helper Functions ---
# ======================================================================================

def parse_bounds_from_expression(expression):
    """
    Parse a Python expression string to extract min/max bounds for optimization.

    Supported patterns:
    - np.arange(start, stop, ...) -> (start, stop - 1)
    - np.random.randint(low, high) -> (low, high - 1)
    - range(start, stop) -> (start, stop - 1)

    Returns a (low, high) tuple or None if no pattern matches.
    """
    for pattern in [r"arange\(", r"randint\(", r"range\("]:
        match = re.search(
            pattern + r"\s*" + _NUM_PATTERN + r"\s*,\s*" + _NUM_PATTERN,
            expression,
        )
        if match:
            start = float(match.group(1))
            stop = float(match.group(2))
            return (start, stop - 1)

    return None


def get_optimization_params():
    """
    Identify parameters in SIM_CONFIG whose values are randomized expressions
    and return their parsed bounds as a dict suitable for BayesianOptimization.
    """
    params = {}
    sim_config = CONFIG.get("SIM_CONFIG", {})
    
    randomized_keywords = ("random", "arange", "linspace", "range")

    for key, value in sim_config.items():
        if isinstance(value, str) and any(kw in value for kw in randomized_keywords):
            bounds = parse_bounds_from_expression(value)
            if bounds:
                params[key] = bounds
                print(f"  [Auto-Detected] '{key}' -> bounds {bounds}")
            else:
                print(f"  [Warning] Could not parse bounds for '{key}' = '{value}'")
    
    return params


def calculate_reward(status, input_params):
    """
    Calculate the objective score from the reward function expression in config.
    Includes both input parameters (e.g. resource counts) and output observations
    (e.g. waiting times) in the evaluation context.
    """
    if "REWARD_FUNCTION" not in CONFIG:
        print("  [Warning] No REWARD_FUNCTION in config, returning 0")
        return 0.0
    
    expr_data = CONFIG["REWARD_FUNCTION"]
    expression = expr_data.get("expression", "0")
    req_vars = expr_data.get("variables", [])
    
    # 1. Add input parameters (numCarInspectors, numBusInspectors, etc.)
    context = dict(input_params)

    # 2. Add observation values from final status
    obs = getattr(status, 'observation', None)
    if obs is None:
        obs = status
    
    for v in req_vars:
        if v in context:
            continue  # Already set from input_params
        
        val = None
        # Try attribute access
        if hasattr(obs, v):
            val = getattr(obs, v)
        # Try dict access
        elif isinstance(obs, dict) and v in obs:
            val = obs[v]
        # Try __getitem__
        elif hasattr(obs, '__getitem__'):
            try:
                val = obs[v]
            except (KeyError, TypeError):
                pass
        
        if val is None:
            print(f"    [Warning] Variable '{v}' not found in observation, defaulting to 0")
            val = 0.0
        context[v] = val
    
    # 3. Add math helpers
    context['math'] = math
    context['abs'] = abs
    context['min'] = min
    context['max'] = max
    context['np'] = np
    
    try:
        return float(eval(expression, {"__builtins__": {}}, context))
    except Exception as e:
        print(f"  [Reward Error] {e} | Expression: {expression}")
        return _FAILURE_SCORE


# ======================================================================================
# --- Optimizer Class ---
# ======================================================================================

class BCOptimizer:
    """
    Bayesian Optimization wrapper for Alpyne-Xtend.
    Handles discrete parameter spaces via rounding and caches evaluated
    parameter combinations to avoid redundant simulations.
    """

    _MAX_REATTEMPTS = 100

    def __init__(self, pbounds, round_values=True, optimizer_seed=None, kappa=2.5):
        self._round_values = round_values
        self._history = {}
        self.pbounds = pbounds
        self._reattempts = 0

        if _LEGACY_BAYES_OPT:
            # Legacy API (< 2.0)
            self.optimizer = BayesianOptimization(
                f=None, pbounds=pbounds, random_state=optimizer_seed, verbose=0)
            self.optimizer.set_gp_params(alpha=1e-3)
            self._utility = UtilityFunction(kind="ucb", kappa=kappa, xi=0.0)
        else:
            # Modern API (>= 2.0 / 3.x)
            self.optimizer = BayesianOptimization(
                f=None, pbounds=pbounds, random_state=optimizer_seed,
                allow_duplicate_points=True,
                acquisition_function=acquisition.UpperConfidenceBound(kappa=kappa))

    def suggest(self):
        """Get the next parameter suggestion, skipping previously evaluated (rounded) points."""
        if self._reattempts > self._MAX_REATTEMPTS:
            raise StopIteration("Cannot find new unique parameters to try")

        try:
            if _LEGACY_BAYES_OPT:
                suggestion = self.optimizer.suggest(self._utility)
            else:
                suggestion = self.optimizer.suggest()
        except Exception as e:
            raise StopIteration(str(e)) from e

        # Check if we've already tried this (rounded) parameter set
        if self._round_values:
            key = tuple(int(round(suggestion[k])) for k in sorted(suggestion))
            cached_score = self._history.get(key)
            if cached_score is not None:
                # Already evaluated, register and try again
                try:
                    self.optimizer.register(params=suggestion, target=cached_score)
                except (NotUniqueError, KeyError, ValueError):
                    pass
                self._reattempts += 1
                return self.suggest()

        self._reattempts = 0
        return suggestion

    def register(self, inputs, score):
        """Register a result. Returns True if this is the new best score."""
        if not inputs:
            return False
            
        try:
            self.optimizer.register(params=inputs, target=score)
        except (NotUniqueError, KeyError, ValueError):
            pass

        # Cache for deduplication
        if self._round_values:
            key = tuple(int(round(inputs[k])) for k in sorted(inputs))
            self._history[key] = score

        # Check if this is the new best
        try:
            return self.optimizer.max and self.optimizer.max['target'] == score
        except Exception:
            return False


# ======================================================================================
# --- Main Optimization Logic ---
# ======================================================================================

def _build_full_config(params_rounded):
    """
    Merge optimized (rounded) parameters with the remaining SIM_CONFIG entries,
    evaluating any randomized expressions for non-optimized parameters.
    """
    full_config = {}
    for k, v in CONFIG.get("SIM_CONFIG", {}).items():
        if k in params_rounded:
            full_config[k] = params_rounded[k]
        elif isinstance(v, str):
            # Evaluate expression for non-optimized randomized params
            try:
                full_config[k] = float(eval(v, {"__builtins__": {}, "np": np, "math": math}))
            except Exception:
                full_config[k] = v
        else:
            full_config[k] = v
    return full_config
def run_optimization():
    """Main optimization loop: detect parameters, create simulations, and iterate."""
    print("=" * 60)
    print(" BAYESIAN OPTIMIZATION FOR ALPYNE MODEL")
    print("=" * 60)
    
    # 1. Identify Parameters to Optimize
    print("\nDetecting optimization parameters from SIM_CONFIG...")
    pbounds = get_optimization_params()
    
    if not pbounds:
        print("\nERROR: No parameters found to optimize!")
        print("Ensure SIM_CONFIG contains randomized expressions like:")
        print('  "numCarInspectors": "np.random.choice(np.arange(1, 6, 1))"')
        return None
    
    print(f"\nOptimizing {len(pbounds)} parameter(s): {list(pbounds.keys())}")
    
    # 2. Load Settings
    bo_config = CONFIG.get("BAYES_OPT", {})
    training_config = CONFIG.get("TRAINING", {})
    
    n_envs = training_config.get("n_envs", 1)
    total_iterations = bo_config.get("iterations", training_config.get("total_episodes", 20))
    timeout_per_run = float(bo_config.get("timeout", 120))  # seconds per simulation run
    verbose = bo_config.get("verbose", True)
    round_values = bo_config.get("round_values", True)
    kappa = bo_config.get("kappa", 2.5)
    seed = bo_config.get("seed", CONFIG.get("RL_AGENT_SETTINGS", {}).get("seed", 1))
    
    print(f"\nSettings:")
    print(f"  Parallel Envs:  {n_envs}")
    print(f"  Iterations:     {total_iterations}")
    print(f"  Timeout/Run:    {timeout_per_run}s")
    print(f"  Round Values:   {round_values}")
    print(f"  Kappa (UCB):    {kappa}")
    print(f"  Seed:           {seed}")
    
    # 3. Create Simulation Instances
    print(f"\nCreating {n_envs} simulation instance(s)...")
    sims = []
    for i in range(n_envs):
        try:
            sim = AnyLogicSim(
                model_path=CONFIG["MODEL_PATH"],
                java_exe=CONFIG.get("JAVA_EXE_PATH"),
                log_dir=LOG_DIR,
                log_id=f"-BO_{i}",
                auto_lock=False,  # Non-blocking resets for parallelism
                lock_defaults=dict(timeout=timeout_per_run),
                **CONFIG.get("ALPYNE_SIM_SETTINGS", {}),
            )
            sims.append(sim)
            print(f"    Sim {i}: Created")
        except Exception as e:
            print(f"    Sim {i}: FAILED - {e}")
    
    if not sims:
        print("\nERROR: Failed to create any simulation instances!")
        return None
    
    # 4. Create Global Optimizer
    print("Initializing Bayesian Optimizer...")
    optimizer = BCOptimizer(
        pbounds=pbounds, round_values=round_values,
        optimizer_seed=seed, kappa=kappa)

    # 5. Run Optimization Loop
    print(f"\nStarting optimization ({total_iterations} iterations)...")
    print("-" * 60)
    
    start_time = time.time()
    last_iteration = 0

    try:
        for iteration in range(total_iterations):
            last_iteration = iteration
            iter_start = time.time()
            print(f"\nIteration {iteration + 1}/{total_iterations}")
            
            # Phase A: Get suggestions and start simulations
            active_runs = []  # (sim_idx, params_raw, params_rounded)
            for i, sim in enumerate(sims):
                try:
                    params_raw = optimizer.suggest()
                    params_rounded = {k: int(round(v)) for k, v in params_raw.items()}
                    
                    # Build complete config (include non-optimized static params)
                    full_config = _build_full_config(params_rounded)

                    # Start simulation (non-blocking)
                    sim.reset(**full_config)
                    active_runs.append((i, params_raw, params_rounded))
                    
                    if verbose:
                        print(f"  [Sim {i}] Started: {params_rounded}")
                except StopIteration:
                    print(f"  [Sim {i}] Skipped: No new parameters available")
                except Exception as e:
                    print(f"  [Sim {i}] Failed to start: {e}")
            
            if not active_runs:
                print("\n  Early termination: All parameter combinations explored")
                break
            
            # Phase B: Wait for completions and collect results
            for sim_idx, params_raw, params_rounded in active_runs:
                try:
                    status = sims[sim_idx].lock()
                    score = calculate_reward(status, params_rounded)
                    is_best = optimizer.register(params_raw, score)
                    
                    if verbose:
                        marker = " *** NEW BEST ***" if is_best else ""
                        print(f"  [Sim {sim_idx}] Result: {params_rounded} -> {score:.4f}{marker}")

                    if is_best:
                        # Save best immediately
                        best_info = {
                            "iteration": iteration + 1,
                            "score": score,
                            "parameters": params_rounded,
                            "timestamp": datetime.now().isoformat(),
                        }
                        with open(os.path.join(MODEL_OUT_DIR, "best_params.json"), "w") as f:
                            json.dump(best_info, f, indent=4)
                        
                except Exception as e:
                    print(f"  [Sim {sim_idx}] Error during evaluation: {e}")
                    optimizer.register(params_raw, _FAILURE_SCORE)

            print(f"  Iteration completed in {time.time() - iter_start:.1f}s")

    except KeyboardInterrupt:
        print("\n\nOptimization interrupted by user.")
    
    finally:
        # Cleanup
        print("\nClosing simulations...")
        for i, sim in enumerate(sims):
            try:
                sim.close()
                print(f"    Sim {i}: Closed")
            except Exception:
                pass
    
    # 6. Report Results
    total_time = time.time() - start_time
    print("\n" + "=" * 60)
    print(" OPTIMIZATION COMPLETE")
    print("=" * 60)
    print(f" Total Time: {total_time:.1f}s")
    
    if optimizer.optimizer.max:
        best = optimizer.optimizer.max
        best_score = best['target']
        best_params_raw = best['params']
        best_params_rounded = {k: int(round(v)) for k, v in best_params_raw.items()}
        
        print(f"\n BEST RESULT:")
        print(f"   Score:      {best_score:.4f}")
        print(f"   Parameters: {best_params_rounded}")
        
        # Save final result
        final_result = {
            "best_score": best_score,
            "best_params_raw": best_params_raw,
            "best_params_rounded": best_params_rounded,
            "total_iterations": last_iteration + 1,
            "total_time_seconds": total_time,
            "timestamp": datetime.now().isoformat(),
        }
        result_path = os.path.join(MODEL_OUT_DIR, "final_optimization_result.json")
        with open(result_path, "w") as f:
            json.dump(final_result, f, indent=4)
        print(f"\n Results saved to: {result_path}")
        
        return final_result
    else:
        print("\n No valid results found.")
        return None


# ======================================================================================
# --- Entry Point ---
# ======================================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bayesian Optimization for Alpyne Models")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse config and exit without running")
    args = parser.parse_args()
    
    if args.dry_run:
        print("Dry run mode - checking configuration...")
        detected = get_optimization_params()
        print(f"\nDetected parameters: {detected}")
        print(f"\nReward function:")
        print(f"  Expression: {CONFIG.get('REWARD_FUNCTION', {}).get('expression', 'NOT SET')}")
        print(f"  Variables:  {CONFIG.get('REWARD_FUNCTION', {}).get('variables', [])}")
        print("\nConfiguration valid. Ready to run.")
    else:
        run_optimization()

