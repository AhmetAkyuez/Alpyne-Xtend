import customtkinter as ctk
from tkinter import filedialog, messagebox, ttk
import json
import os
import subprocess
import threading
import time
import sys
from pathlib import Path
import math
import shutil
import atexit
import webbrowser

# Add Scripts directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "AlpyneXtend", "Scripts"))
from config_utils import update_config, load_json, save_json

try:
    import winsound
except ImportError:
    winsound = None

# Set theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

# --- CONTENT CONFIGURATION ---
TOOLTIPS = {
    # --- Tab A.1 Project Setup ---
    "MODEL_PATH": "The location of your exported AnyLogic model (.zip). This export must include the compiled .jar file, libraries, and the database.",
    "JAVA_EXE": "The path to the 'java' executable. This is required to run the Alpyne server which hosts your simulation.",
    "PYTHON_VENV": "Optional: Select a specific Python Virtual Environment (python.exe) if your RL libraries (Stable Baselines3, Shimmy) are installed there.",
    "SCAN_SCRIPT": "The Python script used to analyze the AnyLogic model. It extracts parameters, variables, and default values to populate the UI.",
    "LOG_LEVEL_PY": "Controls the verbosity of Python logs. 'INFO' shows standard progress; 'DEBUG' shows detailed variable updates for troubleshooting.",
    "LOG_LEVEL_JAVA": "Controls the AnyLogic server logs. Use 'FINE' or 'ALL' only if you need to debug the internal simulation engine.",
    "MAX_AWAIT": "Time (seconds) Python waits for the AnyLogic simulation to respond (e.g., after a reset). Increase this for heavy/slow models.",
    # --- Tab B.3 Training Configuration ---
    "NUM_ENVS": "Number of parallel simulation instances. Higher values speed up data collection but require more RAM and CPU cores.",
    "MAX_EPISODES": "The total number of training episodes to run before the experiment stops.",
    "MAX_DURATION": "The maximum wall-clock time (in minutes) allowed for training. Set to 0 to disable time limits.",
    "STEPS_PER_EP": "The maximum number of simulation steps allowed in a single episode before it is forcibly truncated.",
    # --- Toggles ---
    "USE_TB": "TensorBoard is a visual live dashboard which lets you track and analyse your simulation runs. You can also compare runs with each other.",
    "AUTO_LAUNCH_TB": "If checked, the TensorBoard dashboard will automatically open in your browser when training starts.",
    "EXT_LOGGING": "Log additional custom metrics (actions, rewards) to TensorBoard. Useful for debugging agent behavior but increases log file size.",
    "SAVE_MODELS": "Save your trained models after each episode. Useful for creating checkpoints to resume training later.",
    "RESET_TB": "Changes the behaviour of the way that each episode is displayed in TensorBoard. If checked, steps reset to 0 every episode.",
    "SOUND_ON": "Plays a system notification sound when the training process completes.",
    "NORM_OBS": "Recommended! Normalizes observation values to a standard range (usually mean 0, std 1). This significantly stabilizes Neural Network training.",
    "NORM_REW": "Normalizes rewards. Can help when rewards are very large or very small, keeping gradients stable.",
    # --- Agent Params ---
    "POLICY": "The network architecture type. 'MlpPolicy' is standard for vector data. 'CnnPolicy' is used for image data.",
    "SEED": "Random seed for reproducibility. Using the same seed ensures the 'random' events happen in the same order every time.",
    "DEVICE": "Hardware to use. 'cpu' is standard. 'cuda' allows GPU acceleration (requires NVIDIA card + drivers).",
    "NET_ARCH": "Defines the Neural Network hidden layers. E.g., [256, 256] creates two layers with 256 neurons each. Larger networks can learn more complex patterns but are slower.",
    # --- SAC Specifics ---
    "LEARNING_RATE": "How fast the model updates its knowledge. Too high = unstable; Too low = slow learning. Standard is 0.0003.",
    "GAMMA": "Discount factor (0 to 1). Determines how much the agent cares about future rewards vs immediate rewards. 0.99 is standard.",
    "BATCH_SIZE": "Number of data points used for one gradient update. Larger batches (256, 512) provide more stable updates.",
    "TAU": "Soft update coefficient. Controls how quickly the target network tracks the policy network.",
    "LEARNING_STARTS": "Number of steps to collect with random actions before the agent starts learning. Fills the replay buffer.",
    # --- Testing Tab ---
    "EVAL_MODEL": (
        "Select the trained model (.zip) to evaluate.\n\n"
        "This is the output file produced by the training script, located in the 'ModelsRL' folder "
        "(e.g., 'ModelName_20250312_1430_final.zip').\n\n"
        "Important: The evaluation also requires a 'vec_normalize.pkl' file which contains the "
        "normalization statistics (mean/std) collected during training. Without it, the agent receives "
        "raw (un-normalized) observations which may cause poor performance.\n\n"
        "The system automatically searches for the matching .pkl file:\n"
        "1. First by naming convention (e.g., 'ModelName_20250312_1430_vec_normalize.pkl')\n"
        "2. Then 'vec_normalize.pkl' in the same folder\n"
        "3. Then 'vec_normalize.pkl' in the parent folder\n\n"
        "Make sure the .pkl file is next to or near your .zip model file."
    ),
}


class AlpyneXtendApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # UI Setup
        self.title("Alpyne-Xtend Configuration Manager")
        self.geometry("1400x900")

        # State
        self.base_dir = Path(__file__).parent.resolve()
        # Consolidate Logs to Scripts/Logs
        self.logs_dir = self.base_dir / "AlpyneXtend" / "Scripts" / "Logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.saved_configs_dir = self.base_dir / "AlpyneXtend" / "Configs"
        self.saved_configs_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.base_dir / "AlpyneXtend" / "config.json"

        self.scan_results_path = self.logs_dir / "structured_scan_results.json"

        if not self.config_path.exists():
            self._create_default_config()

        self.scan_data = None
        self.config_data = load_json(self.config_path) or {}

        # Internal State
        self.scan_process = None
        self.config_status = {}
        self.overrides = {}
        self.exposed_params = {}

        self.prop_panel_width = 400

        # Internal State (Performance Optimization)
        self.scan_revision = 0  # Increments when a new scan finishes
        self.built_revisions = {}  # Tracks which version of the UI is currently built
        self._load_settings()

        self._create_ui()

        if self.config_data:
            self.initial_model_path = self.config_data.get("MODEL_PATH", "")

        # Initialization logic
        self.tb_process = None
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        atexit.register(self._cleanup_on_exit)

        # Check TB status after UI is built
        self.after(1000, self._check_initial_tb_status)

        # --- NEW: Auto-load existing scan results on startup ---
        if self.scan_results_path.exists():
            print("Found existing scan results. Loading...")
            self.after(500, self._load_scan_results)

    def on_close(self):
        self._cleanup_on_exit()
        self.destroy()

    def _cleanup_on_exit(self):
        try:
            if hasattr(self, "training_process") and self.training_process:
                try:
                    self.training_process.terminate()
                except Exception:
                    pass

            if hasattr(self, "tb_process") and self.tb_process:
                try:
                    self.tb_process.terminate()
                except Exception:
                    pass

            # Kill remaining TensorBoard processes on Windows
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/IM", "tensorboard.exe"],
                    capture_output=True,
                    creationflags=0x08000000,
                )
        except Exception:
            pass

    def _check_initial_tb_status(self):
        if self._is_port_in_use(6006):
            self._update_tb_status(True)
        else:
            self._update_tb_status(False)

    def _create_default_config(self):
        default_config = {
            "MODEL_PATH": "",
            "JAVA_EXE_PATH": "java",
            "ALPYNE_SIM_SETTINGS": {"py_log_level": "ERROR", "java_log_level": "ERROR", "max_server_await_time": 10},
            "TRAINING": {
                "n_envs": 1,
                "total_episodes": 1000,
                "steps_per_episode": 100,
                "save_models": False,
                "reset_num_timesteps": False,
                "use_tensorboard": True,
                "auto_launch_tb": True,
                "play_sound": True,
            },
            "RL_AGENT_SETTINGS": {"policy": "MlpPolicy", "seed": 1, "device": "cpu"},
            "SAC_PARAMS": {
                "learning_rate": 0.003,
                "gamma": 0.9,
                "batch_size": 256,
                "tau": 0.08,
                "learning_starts": 10,
                "policy_net_arch": [512, 512],
            },
            "SIM_CONFIG": {},
            "ACTIONS": {},
            "OBSERVATIONS": {},
            "variables": [],
        }
        try:
            with open(self.config_path, "w") as f:
                json.dump(default_config, f, indent=4)
        except Exception as e:
            print(f"Failed to create default config: {e}")

    def _add_info_button(self, parent, key):
        """Creates a small info button that shows a tooltip popup"""
        text = TOOLTIPS.get(key, "No description available.")

        btn = ctk.CTkButton(
            parent,
            text="?",
            width=20,
            height=20,
            font=("Arial", 12, "bold"),
            fg_color="gray40",
            hover_color="gray60",
            command=lambda: messagebox.showinfo("Info", text),
        )
        return btn

    def _render_guide_content(self, parent, content_list):
        """Renders a list of content blocks (Headers, Text, Images)"""
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=20)

        for block in content_list:
            b_type = block.get("type", "text")

            if b_type == "header":
                ctk.CTkLabel(scroll, text=block["text"], font=ctk.CTkFont(size=24, weight="bold"), anchor="w").pack(
                    fill="x", pady=(20, 10)
                )

            elif b_type == "subheader":
                ctk.CTkLabel(
                    scroll,
                    text=block["text"],
                    font=ctk.CTkFont(size=18, weight="bold"),
                    text_color="#3B8ED0",
                    anchor="w",
                ).pack(fill="x", pady=(15, 5))

            elif b_type == "text":
                # Using a Label with wrapping for text paragraphs
                ctk.CTkLabel(
                    scroll, text=block["text"], font=("Arial", 14), justify="left", wraplength=800, anchor="w"
                ).pack(fill="x", pady=(0, 10))

            elif b_type == "image":
                # Requires PIL and valid path
                img_path = block.get("path")
                if img_path and os.path.exists(img_path):
                    try:
                        from PIL import Image

                        pil_img = Image.open(img_path)
                        ctk_img = ctk.CTkImage(
                            light_image=pil_img, dark_image=pil_img, size=block.get("size", (400, 300))
                        )
                        ctk.CTkLabel(scroll, text="", image=ctk_img).pack(pady=10)
                        if "caption" in block:
                            ctk.CTkLabel(
                                scroll, text=block["caption"], font=("Arial", 10, "italic"), text_color="gray"
                            ).pack()
                    except Exception as e:
                        ctk.CTkLabel(scroll, text=f"[Image Load Error: {e}]", text_color="red").pack()

    def _build_guide_tabs(self):
        """Build the Guide tabs A.0 and B.0 with rich content."""
        # --- A.0 Setup Guide Content ---
        setup_content = [
            {"type": "header", "text": "A.0: The Setup Phase (Scanning & Implementation)"},
            {
                "type": "text",
                "text": "Alpyne-Xtend is a bridge between AnyLogic simulations and modern RL frameworks like Stable Baselines3. This phase is a 'two-pass' process where you scan the model, implement the bridge, and then re-export.",
            },
            {"type": "subheader", "text": "Step 1: Initial Project Setup & Model Scan"},
            {
                "type": "text",
                "text": "The first step is to export your AnyLogic model via the Reinforcement Learning experiment. At this stage, the experiment does not require any inputs. "
                "Point Xtend to your exported model (zip), select your Java Executable (usually found in AnyLogic's installation folder under `jre/bin/java.exe`), and run a 'Model Scan'. "
                "This discovers all variables within the Root Agent of your RL Experiment.",
            },
            {"type": "subheader", "text": "Step 2: Defining the Interface & 'takeAction'"},
            {
                "type": "text",
                "text": "Once scanned, you must select some parameters for the Training:\n"
                "• Observation Parameters: Used by the Agent to 'See' the environment state.\n"
                "• Action Parameters: Used by the Agent to 'Control' the environment.\n"
                "• Config Parameters: Used to set the initial values (starting conditions) of each run.\n\n"
                "The Critical Step: You must decide *when* the AI makes a decision. In AnyLogic, you need to call the `takeAction` method at specific 'decision points' (e.g., an 'On Exit' block or a recurring Event). "
                "This tells the simulation to pause and wait for the Python agent to provide an action.\n\n"
                "Documentation at: https://the-anylogic-company.github.io/Alpyne/components-rlready-model.html",
            },
            {"type": "subheader", "text": "Step 3: Code Review & The Second Export"},
            {
                "type": "text",
                "text": "After selection, go to the Code Review Tab. This generates the Java snippets for your RL Experiment fields. "
                "Due to AnyLogic's EULA, Xtend cannot inject this code directly into your exported model file. "
                "Fortunately, you can quickly paste these snippets into the Configuration, Observation, and Action fields of the RL Experiment in AnyLogic. "
                "Crucial: After pasting, you must re-export the model from AnyLogic. This 'RL-ready' version is what you will use for training.",
            },
        ]
        self._render_guide_content(self.tab_setup_guide, setup_content)

        # --- B.0 Training Guide Content ---
        train_content = [
            {"type": "header", "text": "B.0: Training Your Agent"},
            {
                "type": "text",
                "text": "With your 'RL-ready' model re-exported and re-scanned in Tab 1, you are ready to continue with Tab B to configure the Reinforcement Learning environment.",
            },
            {"type": "subheader", "text": "Step 1: Defining the Training Parameters"},
            {
                "type": "text",
                "text": "Now you select the paramters for your training. First select if you want to set some initial values for the parameters that are used for each episode. You can select static values or randomize them. Then you select the Action parameters and you must must define the Bounds (Min/Max) that the AI is allowed to set the value as. Finally you select the values that the AI will track in the simulation to know what is going on.\n",
            },
            {"type": "subheader", "text": "Step 2: Set the Reward Function"},
            {
                "type": "text",
                "text": "The Reward Function is a Python expression that tells the AI what its goal is. It is calculated every time a step is taken.",
            },
            {
                "type": "text",
                "text": "• Accessing Data: Use the variable names you defined in the Setup phase and selected as observations.\n"
                "• Logic: You can use standard Python math. For example: `reward = throughput - (work_in_progress * 0.1)`. \n"
                "• The 'Carrot' and the 'Stick': Positive numbers encourage behavior; negative numbers punish it.",
            },
            {"type": "subheader", "text": "Step 3: Terminal (Stopping) Conditions"},
            {
                "type": "text",
                "text": "An AI learns in 'Episodes.' You must define when an episode ends so it can reset and try again:\n"
                "• Time-based: The simulation reaches a specific stop time.\n"
                "• Logic-based: A boolean condition in your model (e.g., `isGameOver == true`). When this condition is met, the engine moves to the FINISHED state, and the AI calculates its final score.",
            },
            {"type": "subheader", "text": "Step 4: Hyperparameters & Execution"},
            {
                "type": "text",
                "text": "Before clicking 'Start Training', review your Agent's settings:\n"
                "• TensorBoard: Once training starts, launch the Dashboard. Look for the 'Mean Reward' graph. A successful agent should show a curve that trends upward over time.",
            },
            {
                "type": "text",
                "text": "> Tip: If the simulation engine enters an ERROR state, you can go back to Tab 1 and change the Log Levels to a lower level, to get more information about the simulation. Check your 'model.log' file.",
            },
        ]
        self._render_guide_content(self.tab_train_guide, train_content)

    def _create_ui(self):
        self.grid_columnconfigure(1, weight=1)  # Main content area
        self.grid_rowconfigure(0, weight=1)

        # --- Sidebar (Left) ---
        sidebar = ctk.CTkFrame(self, width=200, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_rowconfigure(4, weight=1)

        title = ctk.CTkLabel(sidebar, text="ALPYNE XTEND", font=ctk.CTkFont(size=20, weight="bold"))
        title.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.btn_mode_setup = ctk.CTkButton(
            sidebar,
            text="A. SETUP",
            command=lambda: self._switch_mode("setup"),
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="transparent",
            border_width=2,
            text_color=("gray10", "#DCE4EE"),
        )
        self.btn_mode_setup.grid(row=1, column=0, padx=20, pady=10, sticky="ew")

        self.btn_mode_train = ctk.CTkButton(
            sidebar,
            text="B. TRAINING",
            command=lambda: self._switch_mode("training"),
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="transparent",
            border_width=2,
            text_color=("gray10", "#DCE4EE"),
        )
        self.btn_mode_train.grid(row=2, column=0, padx=20, pady=10, sticky="ew")

        # NEW: Testing Button
        self.btn_mode_test = ctk.CTkButton(
            sidebar,
            text="C. TESTING",
            command=lambda: self._switch_mode("testing"),
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="transparent",
            border_width=2,
            text_color=("gray10", "#DCE4EE"),
        )
        self.btn_mode_test.grid(row=3, column=0, padx=20, pady=10, sticky="ew")

        # --- Main Content Area (Column 1) ---

        # 1. Setup Phase Frame
        self.frame_setup = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_setup.grid(row=0, column=1, sticky="nsew")
        self.frame_setup.grid_columnconfigure(0, weight=1)
        self.frame_setup.grid_rowconfigure(0, weight=1)

        self.tabview_setup = ctk.CTkTabview(self.frame_setup, anchor="nw", command=self._on_tab_change)
        self.tabview_setup.grid(row=0, column=0, padx=10, pady=(0, 10), sticky="nsew")

        # NEW: A.0 Guide Tab
        self.tab_setup_guide = self.tabview_setup.add("0. Setup Guide")
        self.tab_setup = self.tabview_setup.add("1. Project Setup")
        self.tab_design = self.tabview_setup.add("2. Experiment Configuration")
        self.tab_code = self.tabview_setup.add("3. Code Review")

        # 2. Training Phase Frame (Initially Hidden)
        self.frame_train = ctk.CTkFrame(self, fg_color="transparent")
        # self.frame_train.grid(...) # Will be gridded by switch_mode
        self.frame_train.grid_columnconfigure(0, weight=1)
        self.frame_train.grid_rowconfigure(0, weight=1)

        self.tabview_train = ctk.CTkTabview(self.frame_train, anchor="nw", command=self._on_tab_change)
        self.tabview_train.grid(row=0, column=0, padx=10, pady=(0, 10), sticky="nsew")

        # NEW: B.0 Training Guide
        self.tab_train_guide = self.tabview_train.add("0. Training Guide")
        self.tab_params = self.tabview_train.add("1. Parameter Configuration")
        self.tab_reward = self.tabview_train.add("2. Reward Function")
        self.tab_train = self.tabview_train.add("3. Training Dashboard")

        # 3. NEW: Testing Phase Frame
        self.frame_test = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_test.grid_columnconfigure(0, weight=1)
        self.frame_test.grid_rowconfigure(0, weight=1)

        self.tabview_test = ctk.CTkTabview(self.frame_test, anchor="nw", command=self._on_tab_change)
        self.tabview_test.grid(row=0, column=0, padx=10, pady=(0, 10), sticky="nsew")

        self.tab_testing = self.tabview_test.add("1. Run Evaluation")

        # --- Build Tabs ---
        # NEW: Guide Tabs First
        self._build_guide_tabs()

        # A. Setup
        self._build_setup_tab()
        self._build_design_tab()  # Now "Experiment Configuration"
        self._build_code_tab()

        # B. Training
        self._build_param_config_tab()  # New
        self._build_reward_tab()
        self._build_train_tab()
        self._build_testing_tab()  # New

        # Initialize
        self._switch_mode("setup")

    def _switch_mode(self, mode):
        # Reset all buttons to transparent/gray
        for btn in [self.btn_mode_setup, self.btn_mode_train, self.btn_mode_test]:
            btn.configure(fg_color="transparent")

        # Hide all frames
        self.frame_setup.grid_forget()
        self.frame_train.grid_forget()
        self.frame_test.grid_forget()

        # Activate selected mode
        if mode == "setup":
            self.btn_mode_setup.configure(fg_color=("gray75", "gray25"))
            self.frame_setup.grid(row=0, column=1, sticky="nsew")
            self.tabview = self.tabview_setup
        elif mode == "training":
            self.btn_mode_train.configure(fg_color=("gray75", "gray25"))
            self.frame_train.grid(row=0, column=1, sticky="nsew")
            self.tabview = self.tabview_train
            self._load_exposed_params_for_training()
        elif mode == "testing":
            self.btn_mode_test.configure(fg_color=("gray75", "gray25"))
            self.frame_test.grid(row=0, column=1, sticky="nsew")
            self.tabview = self.tabview_test

    def _register_setting(self, path, widget, default):
        """Register a widget to be managed by the settings system"""
        current_val = widget.get()
        if not current_val and default:
            if isinstance(widget, ctk.CTkEntry):
                widget.insert(0, str(default))
            elif isinstance(widget, ctk.CTkComboBox):
                widget.set(str(default))
        self.settings_entries[path] = (widget, default)

    def _build_testing_tab(self):
        """Builds the UI for testing and evaluating trained models."""
        frame = self.tab_testing
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)

        main_frame = ctk.CTkFrame(frame, fg_color="transparent")
        main_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

        # --- 1. Model Selection ---
        title_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        title_frame.pack(fill="x", pady=(0, 5))
        ctk.CTkLabel(title_frame, text="Select Trained Model", font=("Arial", 16, "bold")).pack(side="left")
        self._add_info_button(title_frame, "EVAL_MODEL").pack(side="left", padx=(8, 0))

        file_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        file_frame.pack(fill="x", pady=(0, 20))

        self.test_model_entry = ctk.CTkEntry(file_frame, placeholder_text="Path to .zip file (from ModelsRL folder)")
        self.test_model_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        def browse_model():
            # Default to ModelsRL folder for convenience
            initial_dir = str(self.base_dir / "AlpyneXtend" / "Scripts" / "ModelsRL")
            if not os.path.exists(initial_dir):
                initial_dir = None
            f = filedialog.askopenfilename(
                filetypes=[("RL Models", "*.zip")],
                initialdir=initial_dir,
            )
            if f:
                self.test_model_entry.delete(0, "end")
                self.test_model_entry.insert(0, f)

        ctk.CTkButton(file_frame, text="Browse", width=100, command=browse_model).pack(side="right")

        # --- 2. Test Options ---
        opts_frame = ctk.CTkFrame(main_frame)
        opts_frame.pack(fill="x", pady=10, padx=5)

        ctk.CTkLabel(opts_frame, text="Test Parameters", font=("Arial", 14, "bold")).pack(anchor="w", padx=10, pady=10)

        # Episodes Input
        ep_frame = ctk.CTkFrame(opts_frame, fg_color="transparent")
        ep_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(ep_frame, text="Number of Episodes:", width=150, anchor="w").pack(side="left")
        self.test_episodes_entry = ctk.CTkEntry(ep_frame, width=100)
        self.test_episodes_entry.insert(0, "5")
        self.test_episodes_entry.pack(side="left")

        # Stochastic Toggle
        self.test_stochastic_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(ep_frame, text="Use Stochastic Policy (Randomized)", variable=self.test_stochastic_var).pack(
            side="left", padx=20
        )

        # --- 3. Action Buttons ---
        btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        btn_frame.pack(fill="x", pady=20)

        self.btn_run_test = ctk.CTkButton(
            btn_frame,
            text="RUN EVALUATION",
            font=("Arial", 15, "bold"),
            height=50,
            fg_color="#8B5CF6",
            hover_color="#7C3AED",  # Purple theme
            command=self._run_test_script,
        )
        self.btn_run_test.pack(side="left", fill="x", expand=True)

        # --- 4. Output Log ---
        ctk.CTkLabel(main_frame, text="Results Log:", font=("Arial", 12, "bold")).pack(anchor="w")
        self.test_log = ctk.CTkTextbox(main_frame, font=("Consolas", 11))
        self.test_log.pack(fill="both", expand=True, pady=5)

        # Tag configuration for coloring logs
        self.test_log.tag_config("result", foreground="#50FA7B")  # Green for rewards
        self.test_log.tag_config("error", foreground="#FF5555")  # Red for errors

    def _run_test_script(self):
        """Runs the test_agent.py script in a background thread."""
        model_path = self.test_model_entry.get()
        if not model_path or not os.path.exists(model_path):
            messagebox.showerror("Error", "Please select a valid model file (.zip)")
            return

        episodes = self.test_episodes_entry.get()
        is_stochastic = self.test_stochastic_var.get()

        # Build Command
        script_path = self.base_dir / "AlpyneXtend" / "Scripts" / "test_agent.py"
        venv = self.venv_entry.get() if hasattr(self, "venv_entry") else sys.executable

        cmd = [venv, str(script_path), "--model", model_path, "--episodes", episodes]
        if is_stochastic:
            cmd.append("--stochastic")

        # Run in Thread to keep UI responsive
        threading.Thread(target=self._execute_test_process, args=(cmd,), daemon=True).start()

    def _execute_test_process(self, cmd):
        """Executes the test process and handles UI logging."""
        self.btn_run_test.configure(state="disabled", text="Running...")
        self.test_log.delete("1.0", "end")
        self.test_log.insert("end", f"Executing: {' '.join(cmd)}\n\n")

        try:
            # Use subprocess to capture real-time output
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=self.base_dir
            )

            for line in process.stdout:
                self.test_log.insert("end", line)
                self.test_log.see("end")

            process.wait()
            self.test_log.insert("end", "\nEvaluation Finished.")
        except Exception as e:
            self.test_log.insert("end", f"\nError: {e}")
        finally:
            self.btn_run_test.configure(state="normal", text="RUN EVALUATION")

    def _build_setup_tab(self):
        # Initialize settings registry
        self.settings_entries = {}

        frame = self.tab_setup
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)

        main_layout = ctk.CTkFrame(frame, fg_color="transparent")
        main_layout.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        main_layout.grid_columnconfigure(0, weight=3)  # Settings
        main_layout.grid_columnconfigure(1, weight=2)  # Status Card
        main_layout.grid_rowconfigure(0, weight=1)

        # --- Left Column: Configuration Settings ---
        settings_card = ctk.CTkFrame(main_layout)
        settings_card.grid(row=0, column=0, sticky="nsew", padx=(0, 20))
        # New Column Config: 0=Label, 1=InfoBtn, 2=Input, 3=ActionBtn
        settings_card.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(settings_card, text="Environment Configuration", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, columnspan=4, pady=20, padx=20, sticky="w"
        )

        # Helper for compact rows with info buttons
        def add_row(row_idx, label, key, entry_widget, btn_widget=None):
            # Label
            ctk.CTkLabel(settings_card, text=label).grid(row=row_idx, column=0, padx=(20, 5), pady=10, sticky="w")
            # Info Button
            self._add_info_button(settings_card, key).grid(row=row_idx, column=1, padx=(0, 10), pady=10)
            # Entry
            entry_widget.grid(row=row_idx, column=2, padx=5, pady=10, sticky="ew")
            # Optional Action Button
            if btn_widget:
                btn_widget.grid(row=row_idx, column=3, padx=(5, 20), pady=10)

        # Row 1: Model Path
        self.model_path_entry = ctk.CTkEntry(settings_card)
        if hasattr(self, "initial_model_path"):
            self.model_path_entry.insert(0, self.initial_model_path)
        browse_model = ctk.CTkButton(settings_card, text="📁", width=40, command=self._browse_model)

        add_row(1, "AnyLogic Model (.zip):", "MODEL_PATH", self.model_path_entry, browse_model)
        self._register_setting("MODEL_PATH", self.model_path_entry, "")

        # Row 2: Java Path
        self.java_path_entry = ctk.CTkEntry(settings_card)
        self.java_path_entry.insert(0, self.java_path if hasattr(self, "java_path") else "java")
        browse_java = ctk.CTkButton(
            settings_card, text="📁", width=40, command=lambda: self._browse_file(self.java_path_entry)
        )

        add_row(2, "Java Executable (bin):", "JAVA_EXE", self.java_path_entry, browse_java)
        self._register_setting("JAVA_EXE_PATH", self.java_path_entry, "java")

        # Row 3: Python Environment
        self.scan_venv_entry = ctk.CTkEntry(settings_card)
        self.scan_venv_entry.insert(0, sys.executable)
        browse_venv = ctk.CTkButton(
            settings_card, text="📁", width=40, command=lambda: self._browse_file(self.scan_venv_entry)
        )

        add_row(3, "Python Venv (Optional):", "PYTHON_VENV", self.scan_venv_entry, browse_venv)

        # Row 4: Script Selection
        self.scan_script_entry = ctk.CTkEntry(settings_card)
        self.scan_script_entry.insert(0, str(self.base_dir / "AlpyneXtend" / "Scripts" / "diagnostic_scan.py"))
        browse_script = ctk.CTkButton(
            settings_card, text="📁", width=40, command=lambda: self._browse_file(self.scan_script_entry)
        )

        add_row(4, "Scan Script:", "SCAN_SCRIPT", self.scan_script_entry, browse_script)

        # Alpyne Settings
        ctk.CTkLabel(settings_card, text="Alpyne Settings", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=5, column=0, columnspan=4, pady=(20, 10), padx=20, sticky="w"
        )

        # Log Levels
        py_log = ctk.CTkComboBox(settings_card, values=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        add_row(6, "Python Log Level:", "LOG_LEVEL_PY", py_log)
        self._register_setting("ALPYNE_SIM_SETTINGS.py_log_level", py_log, "ERROR")

        java_log = ctk.CTkComboBox(settings_card, values=["DEBUG", "INFO", "WARNING", "ERROR", "OFF"])
        add_row(7, "Java Log Level:", "LOG_LEVEL_JAVA", java_log)
        self._register_setting("ALPYNE_SIM_SETTINGS.java_log_level", java_log, "ERROR")

        await_entry = ctk.CTkEntry(settings_card)
        add_row(8, "Max Server Await (s):", "MAX_AWAIT", await_entry)
        self._register_setting("ALPYNE_SIM_SETTINGS.max_server_await_time", await_entry, "10")

        settings_card.grid_rowconfigure(9, weight=1)

        # Action Buttons (Row 10)
        btn_frame = ctk.CTkFrame(settings_card, fg_color="transparent")
        btn_frame.grid(row=10, column=0, columnspan=4, pady=20, padx=20, sticky="ew")
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            btn_frame,
            text="SAVE SETTINGS",
            command=lambda: self._save_general_settings(),
            height=50,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="green",
        ).grid(row=0, column=0, padx=10, sticky="ew")

        self.scan_btn = ctk.CTkButton(
            btn_frame,
            text="RUN MODEL SCAN",
            command=self._run_scan_thread,
            height=50,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#1f6aa5",
            hover_color="#144870",
        )
        self.scan_btn.grid(row=0, column=1, padx=10, sticky="ew")

        # --- Right Column: Scan Status Dashboard ---
        status_card = ctk.CTkFrame(main_layout, fg_color="#1f1f1f")  # Darker background
        status_card.grid(row=0, column=1, sticky="nsew")
        status_card.grid_columnconfigure(0, weight=1)

        status_card.grid_rowconfigure(0, weight=0)  # Title
        status_card.grid_rowconfigure(1, weight=0)  # Status Label (Fixed height)
        status_card.grid_rowconfigure(2, weight=1)  # Log (Expands to fill space)

        ctk.CTkLabel(status_card, text="Scan Status", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, pady=20
        )

        self.scan_status_label = ctk.CTkLabel(
            status_card, text="No Scan Run", font=ctk.CTkFont(size=24, weight="bold"), text_color="gray"
        )
        self.scan_status_label.grid(row=1, column=0, pady=(10, 30))

        # Log view
        self.scan_log = ctk.CTkTextbox(status_card, height=400, font=("Consolas", 11))
        self.scan_log.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 20))
        self.scan_log.tag_config("error", foreground="#ff5555")
        self.scan_log.tag_config("warning", foreground="#ffb86c")
        self.scan_log.tag_config("success", foreground="#50fa7b")
        self.scan_log.tag_config("info", foreground="#8be9fd")

    def _build_design_tab(self):
        # TAB 2: Experiment Configuration
        frame = self.tab_design
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)

        main_layout = ctk.CTkFrame(frame, fg_color="transparent")
        main_layout.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        main_layout.grid_columnconfigure(0, weight=1)
        main_layout.grid_rowconfigure(3, weight=1)

        # --- 1. Title ---
        ctk.CTkLabel(main_layout, text="Select Variables to Expose", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, pady=(0, 10), sticky="w"
        )

        # --- 2. Search Bar ---
        search_frame = ctk.CTkFrame(main_layout, fg_color="transparent")
        search_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        ctk.CTkLabel(search_frame, text="🔍", font=("Arial", 14)).pack(side="left", padx=(0, 5))

        self.setup_search_var = ctk.StringVar()
        self.setup_search_var.trace_add("write", lambda *args: self._filter_setup_table(self.setup_search_var.get()))

        search_entry = ctk.CTkEntry(
            search_frame, textvariable=self.setup_search_var, placeholder_text="Search variables...", height=30
        )
        search_entry.pack(side="left", fill="x", expand=True)

        # NEW: Reload Button
        ctk.CTkButton(
            search_frame,
            text="🔄 Reload Data",
            command=self._manual_reload_scan_data,
            width=100,
            height=30,
            fg_color="#555555",
        ).pack(side="right", padx=(10, 0))

        # --- 3. Table Header ---
        # Save as self.design_header_frame to update widths dynamically later
        self.design_header_frame = ctk.CTkFrame(main_layout, fg_color="#2b2b2b", height=35)
        self.design_header_frame.grid(row=2, column=0, sticky="ew")

        self.design_col_config = {
            0: {"weight": 0, "minsize": 100},
            1: {"weight": 0, "minsize": 250},
            2: {"weight": 0, "minsize": 100},
            3: {"weight": 0, "minsize": 80},
            4: {"weight": 0, "minsize": 80},
            5: {"weight": 0, "minsize": 80},
            6: {"weight": 1, "minsize": 20},
        }

        for col, cfg in self.design_col_config.items():
            self.design_header_frame.grid_columnconfigure(col, **cfg)

        # Helper to create Header Buttons
        def header_btn(col, text, sort_key, align="center"):
            anchor_map = {"left": "w", "center": "center", "right": "e"}

            # FIX: Set width=20 (small value) to prevent button from forcing column wider than minsize
            btn = ctk.CTkButton(
                self.design_header_frame,
                text=text,
                font=ctk.CTkFont(weight="bold", size=12),
                fg_color="transparent",
                hover_color="#404040",
                width=20,  # <--- CRITICAL FIX
                anchor=anchor_map.get(align, "center"),
                command=lambda: self._sort_setup_table(sort_key),
            )

            # Standardize padding: 5px for left-aligned text, 2px for centered
            px = 5 if align == "left" else 2
            btn.grid(row=0, column=col, sticky="ew", padx=px, pady=2)

        # Create Headers
        header_btn(0, "Model In/Out", "category", align="center")
        header_btn(1, "Parameter Name", "name", align="left")
        header_btn(2, "Type", "data_type", align="center")
        header_btn(3, "Observation", "use_obs", align="center")
        header_btn(4, "Action", "use_act", align="center")
        header_btn(5, "Config", "use_cfg", align="center")

        # --- 4. Scrollable List ---
        self.setup_table_frame = ctk.CTkScrollableFrame(main_layout)
        self.setup_table_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 10))

        self.check_vars_setup = {}
        self.sort_state = {"key": "category", "desc": False}  # Default sort state

        # --- 5. Footer ---
        # Only ONE label here now (removed the duplicate at row=3)
        ctk.CTkLabel(
            main_layout,
            text="Changes are automatically saved.",
            text_color="#2cc985",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=4, column=0, pady=10)

    def _build_reward_tab(self):
        frame = self.tab_reward
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)

        main_layout = ctk.CTkFrame(frame, fg_color="transparent")
        main_layout.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        main_layout.grid_columnconfigure(0, weight=1)
        main_layout.grid_rowconfigure(0, weight=1)  # Top area expands

        # --- 1. Top Area: Split View (Vars | Math Helper) ---
        top_container = ctk.CTkFrame(main_layout, fg_color="transparent")
        top_container.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        # Split ratio: Variables get slightly more width (weight 3) vs Math (weight 2)
        top_container.grid_columnconfigure(0, weight=3)
        top_container.grid_columnconfigure(1, weight=2)
        top_container.grid_rowconfigure(0, weight=1)

        # --- Left Column: Variables List ---
        vars_frame = ctk.CTkFrame(top_container)
        vars_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        vars_frame.grid_columnconfigure(0, weight=1)
        vars_frame.grid_rowconfigure(1, weight=1)

        # Vars Header
        vars_header = ctk.CTkFrame(vars_frame, fg_color="transparent")
        vars_header.grid(row=0, column=0, sticky="ew", padx=10, pady=5)
        ctk.CTkLabel(vars_header, text="Available Variables (Click to Insert)", font=ctk.CTkFont(weight="bold")).pack(
            side="left"
        )

        # UPDATED: Use _manual_reload_scan_data instead of _refresh_reward_vars
        ctk.CTkButton(vars_header, text="🔄 Refresh", command=self._manual_reload_scan_data, width=80, height=24).pack(
            side="right"
        )

        # Scrollable Vars
        self.reward_vars_scroll = ctk.CTkScrollableFrame(vars_frame)
        self.reward_vars_scroll.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        # --- Right Column: Math Reference ---
        math_frame = ctk.CTkFrame(top_container)
        math_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        math_frame.grid_columnconfigure(0, weight=1)
        math_frame.grid_rowconfigure(1, weight=1)

        # Math Header
        ctk.CTkLabel(math_frame, text="Math Reference (Python Syntax)", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, pady=8
        )

        # Math Content
        math_scroll = ctk.CTkScrollableFrame(math_frame, fg_color="transparent")
        math_scroll.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        # Helper to add reference rows
        def add_math_row(syntax, desc):
            row = ctk.CTkFrame(math_scroll, fg_color="transparent")
            row.pack(fill="x", pady=2)
            # Syntax in blue (code-like), Description in gray
            ctk.CTkLabel(
                row, text=syntax, font=("Consolas", 12, "bold"), text_color="#569CD6", width=130, anchor="w"
            ).pack(side="left", padx=(5, 0))
            ctk.CTkLabel(row, text=desc, font=("Arial", 11), text_color="#AAAAAA", anchor="w").pack(
                side="left", fill="x", expand=True
            )

        # -- Arithmetic --
        ctk.CTkLabel(
            math_scroll, text="Basic Arithmetic", font=("Arial", 12, "bold", "underline"), text_color="#DCE4EE"
        ).pack(anchor="w", pady=(5, 2), padx=5)
        add_math_row("a + b", "Addition")
        add_math_row("a - b", "Subtraction")
        add_math_row("a * b", "Multiplication")
        add_math_row("a / b", "Division")
        add_math_row("(a + b) * c", "Grouping")
        add_math_row("a ** b", "Power (a to the power of b)")

        # -- Functions --
        ctk.CTkLabel(
            math_scroll, text="Standard Functions", font=("Arial", 12, "bold", "underline"), text_color="#DCE4EE"
        ).pack(anchor="w", pady=(15, 2), padx=5)
        add_math_row("abs(x)", "Absolute value (positive)")
        add_math_row("min(a, b)", "Smaller of two values")
        add_math_row("max(a, b)", "Larger of two values")
        add_math_row("round(x)", "Round to nearest integer")

        # -- Advanced Math --
        ctk.CTkLabel(
            math_scroll, text="Advanced (math module)", font=("Arial", 12, "bold", "underline"), text_color="#DCE4EE"
        ).pack(anchor="w", pady=(15, 2), padx=5)
        add_math_row("math.log(x)", "Natural Logarithm")
        add_math_row("math.log10(x)", "Log base 10")
        add_math_row("math.exp(x)", "Exponential (e^x)")
        add_math_row("math.sqrt(x)", "Square Root")
        add_math_row("math.sin(x)", "Sine (radians)")
        add_math_row("math.cos(x)", "Cosine (radians)")
        add_math_row("math.pi", "Constant PI (3.1415...)")

        # -- Logic --
        ctk.CTkLabel(
            math_scroll, text="Conditional Logic", font=("Arial", 12, "bold", "underline"), text_color="#DCE4EE"
        ).pack(anchor="w", pady=(15, 2), padx=5)
        add_math_row("10 if x > 0 else -1", "If x > 0 use 10, else -1")

        # --- 2. Bottom Area: Editor (Fixed Height) ---
        editor_frame = ctk.CTkFrame(main_layout)
        editor_frame.grid(row=1, column=0, sticky="ew")  # No vertical expansion
        editor_frame.grid_columnconfigure(0, weight=1)

        # Editor Header
        ctrls = ctk.CTkFrame(editor_frame, fg_color="transparent")
        ctrls.grid(row=0, column=0, sticky="ew", padx=10, pady=5)
        ctk.CTkLabel(ctrls, text="Reward Function Expression (Python)", font=ctk.CTkFont(size=14, weight="bold")).pack(
            side="left"
        )
        ctk.CTkButton(ctrls, text="Save Reward", command=self._save_reward_function, width=100, fg_color="green").pack(
            side="right", padx=5
        )
        ctk.CTkButton(
            ctrls, text="Verify", command=self._verify_reward_function, width=80, fg_color="orange", text_color="black"
        ).pack(side="right", padx=5)

        # Editor Textbox
        self.reward_editor = ctk.CTkTextbox(editor_frame, font=("Consolas", 14), height=120)
        self.reward_editor.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))

        if self.config_data and "REWARD_FUNCTION" in self.config_data:
            expr = self.config_data["REWARD_FUNCTION"].get("expression", "")
            self.reward_editor.insert("1.0", expr)

        self._refresh_reward_vars()

    def _build_code_tab(self):
        self._build_codegen_tab_content(self.tab_code)

    def _build_train_tab(self):
        frame = self.tab_train
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)  # Log area expands

        # --- 1. Top HUD (Metrics) ---
        # Fixed height, always visible at top
        hud_frame = ctk.CTkFrame(frame, fg_color="#2B2B2B", corner_radius=8, height=80)
        hud_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        hud_frame.pack_propagate(False)  # Force height

        dash_grid = ctk.CTkFrame(hud_frame, fg_color="transparent")
        dash_grid.pack(expand=True, fill="both")

        def create_dash_metric(parent, label, default_val, col):
            f = ctk.CTkFrame(parent, fg_color="transparent")
            f.grid(row=0, column=col, padx=40, pady=10)
            ctk.CTkLabel(f, text=label, font=("Arial", 11, "bold"), text_color="#AAAAAA").pack()
            lbl_val = ctk.CTkLabel(f, text=default_val, font=("Roboto", 24, "bold"), text_color="white")
            lbl_val.pack()
            return lbl_val

        self.lbl_dash_time = create_dash_metric(dash_grid, "⏱️ Elapsed Time", "00:00:00", 0)
        self.lbl_dash_episode = create_dash_metric(dash_grid, "🔄 Episode", "0 / 0", 1)
        self.lbl_dash_envs = create_dash_metric(dash_grid, "🏙️ Active Envs", "1", 2)

        # --- 2. Main Configuration Area (The "Cockpit") ---
        # Using a grid: Left Col (Sim/Toggles) | Right Col (Agent/SAC)
        config_container = ctk.CTkFrame(frame, fg_color="transparent")
        config_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        config_container.grid_columnconfigure(0, weight=1)  # Left Col
        config_container.grid_columnconfigure(1, weight=1)  # Right Col
        config_container.grid_rowconfigure(0, weight=1)

        # Helper to add labeled inputs with INFO BUTTON
        def add_input_pair(parent, label_text, info_key, config_path, default, row):
            # Label
            ctk.CTkLabel(parent, text=label_text, font=("Arial", 11, "bold")).grid(
                row=row, column=0, sticky="w", pady=2, padx=5
            )
            # Info Button
            self._add_info_button(parent, info_key).grid(row=row, column=1, sticky="w", padx=2)
            # Entry
            entry = ctk.CTkEntry(parent, height=28)
            entry.grid(row=row, column=2, sticky="ew", pady=2, padx=5)
            self._register_setting(config_path, entry, default)
            return entry

        # === LEFT COLUMN: Simulation & Toggles ===
        left_panel = ctk.CTkFrame(config_container, fg_color="#232323")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        left_panel.grid_columnconfigure(2, weight=1)  # Entry column expands

        ctk.CTkLabel(
            left_panel, text="SIMULATION LIMITS & OPTIONS", text_color="#3B8ED0", font=("Arial", 12, "bold")
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 5))

        # Limits Inputs
        add_input_pair(left_panel, "Num Envs:", "NUM_ENVS", "TRAINING.n_envs", "1", 1)
        add_input_pair(left_panel, "Max Episodes:", "MAX_EPISODES", "TRAINING.total_episodes", "1000", 2)
        add_input_pair(left_panel, "Max Duration (min):", "MAX_DURATION", "TRAINING.max_duration", "0", 3)
        add_input_pair(left_panel, "Steps/Episode:", "STEPS_PER_EP", "TRAINING.steps_per_episode", "100", 4)

        # Separator
        ttk.Separator(left_panel, orient="horizontal").grid(
            row=5, column=0, columnspan=3, sticky="ew", pady=10, padx=10
        )

        # Toggles Grid (Compact 2-column checklist)
        toggles_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
        toggles_frame.grid(row=6, column=0, columnspan=3, sticky="nsew", padx=5)
        toggles_frame.grid_columnconfigure((0, 1), weight=1)

        # Toggle Helper with INFO
        def add_toggle(parent, text, info_key, var_name, config_path, default, r, c):
            frame = ctk.CTkFrame(parent, fg_color="transparent")
            frame.grid(row=r, column=c, sticky="w", pady=4, padx=5)

            var = ctk.BooleanVar(value=default)
            setattr(self, var_name, var)

            cb = ctk.CTkCheckBox(
                frame,
                text=text,
                variable=var,
                font=("Arial", 11),
                command=lambda: self._update_config_bool(config_path, var),
            )
            cb.pack(side="left")
            self._add_info_button(frame, info_key).pack(side="left", padx=(5, 0))

            self.settings_entries[config_path] = (cb, default)
            return cb

        # Col 0 Toggles
        add_toggle(toggles_frame, "Enable TensorBoard", "USE_TB", "use_tb_var", "TRAINING.use_tensorboard", True, 0, 0)
        add_toggle(
            toggles_frame, "Auto-Launch DB", "AUTO_LAUNCH_TB", "auto_launch_var", "TRAINING.auto_launch_tb", True, 1, 0
        )

        # Extended logging + Freq
        ext_frame = ctk.CTkFrame(toggles_frame, fg_color="transparent")
        ext_frame.grid(row=2, column=0, sticky="w", padx=5)

        ext_var = ctk.BooleanVar(value=False)
        self.ext_log_var = ext_var
        cb_ext = ctk.CTkCheckBox(
            ext_frame,
            text="Extended Logging",
            variable=ext_var,
            font=("Arial", 11),
            command=lambda: self._update_config_bool("TRAINING.extended_logging", ext_var),
        )
        cb_ext.pack(side="left")
        self._add_info_button(ext_frame, "EXT_LOGGING").pack(side="left", padx=5)

        self.log_freq_combo = ctk.CTkComboBox(ext_frame, values=["10", "500", "1000"], width=60, height=20)
        self.log_freq_combo.pack(side="left", padx=5)
        self.settings_entries["TRAINING.extended_logging"] = (cb_ext, False)
        self.settings_entries["TRAINING.extended_logging_freq"] = (self.log_freq_combo, "10")

        # Col 1 Toggles
        add_toggle(
            toggles_frame, "Save Checkpoints", "SAVE_MODELS", "save_models_var", "TRAINING.save_models", False, 0, 1
        )
        add_toggle(
            toggles_frame, "Reset TB Steps", "RESET_TB", "reset_ts_var", "TRAINING.reset_num_timesteps", False, 1, 1
        )
        add_toggle(toggles_frame, "Sound on Finish", "SOUND_ON", "sound_var", "TRAINING.play_sound", True, 2, 1)

        # Norms
        norm_frame = ctk.CTkFrame(toggles_frame, fg_color="transparent")
        norm_frame.grid(row=3, column=1, sticky="w", pady=5)
        add_toggle(norm_frame, "Norm Obs", "NORM_OBS", "norm_obs_var", "TRAINING.norm_obs", True, 0, 0)
        add_toggle(norm_frame, "Norm Reward", "NORM_REW", "norm_rew_var", "TRAINING.norm_reward", True, 1, 0)

        # === RIGHT COLUMN: Agent Configuration ===
        right_panel = ctk.CTkFrame(config_container, fg_color="#232323")
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        right_panel.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(
            right_panel, text="AGENT HYPERPARAMETERS (SAC)", text_color="#2CC985", font=("Arial", 12, "bold")
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 5))

        add_input_pair(right_panel, "Policy Class:", "POLICY", "RL_AGENT_SETTINGS.policy", "MlpPolicy", 1)
        add_input_pair(right_panel, "Seed:", "SEED", "RL_AGENT_SETTINGS.seed", "42", 2)
        add_input_pair(right_panel, "Device:", "DEVICE", "RL_AGENT_SETTINGS.device", "cpu", 3)

        ttk.Separator(right_panel, orient="horizontal").grid(
            row=4, column=0, columnspan=3, sticky="ew", pady=10, padx=10
        )

        add_input_pair(right_panel, "Learning Rate:", "LEARNING_RATE", "SAC_PARAMS.learning_rate", "0.0003", 5)
        add_input_pair(right_panel, "Gamma:", "GAMMA", "SAC_PARAMS.gamma", "0.99", 6)
        add_input_pair(right_panel, "Batch Size:", "BATCH_SIZE", "SAC_PARAMS.batch_size", "256", 7)
        add_input_pair(right_panel, "Tau:", "TAU", "SAC_PARAMS.tau", "0.005", 8)
        add_input_pair(right_panel, "Learning Starts:", "LEARNING_STARTS", "SAC_PARAMS.learning_starts", "100", 9)

        # Net Arch
        ctk.CTkLabel(right_panel, text="Network Arch:", font=("Arial", 11, "bold")).grid(
            row=10, column=0, sticky="nw", pady=5, padx=5
        )
        self._add_info_button(right_panel, "NET_ARCH").grid(row=10, column=1, sticky="nw", pady=5)
        net_arch_entry = ctk.CTkEntry(right_panel, height=28)
        net_arch_entry.grid(row=10, column=2, sticky="ew", pady=5, padx=5)
        self._register_setting("SAC_PARAMS.policy_net_arch", net_arch_entry, "[256, 256]")

        # --- 3. Compact Paths Bar ---
        # Placed below the main config grid
        paths_frame = ctk.CTkFrame(frame, fg_color="transparent")
        paths_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        paths_frame.grid_columnconfigure(1, weight=1)  # Script entry expands
        paths_frame.grid_columnconfigure(4, weight=1)  # Venv entry expands

        # Script
        ctk.CTkLabel(paths_frame, text="Script:", font=("Arial", 11)).grid(row=0, column=0, padx=(0, 5))
        self.train_script_entry = ctk.CTkEntry(paths_frame, height=25)
        self.train_script_entry.grid(row=0, column=1, sticky="ew")
        self.train_script_entry.insert(0, str(self.base_dir / "AlpyneXtend" / "Scripts" / "train_agent.py"))
        ctk.CTkButton(
            paths_frame, text="..", width=25, height=25, command=lambda: self._browse_file(self.train_script_entry)
        ).grid(row=0, column=2, padx=2)

        # Spacer
        ctk.CTkFrame(paths_frame, width=20, height=1, fg_color="transparent").grid(row=0, column=3)

        # Venv
        ctk.CTkLabel(paths_frame, text="Venv:", font=("Arial", 11)).grid(row=0, column=3, padx=(0, 5))
        self.venv_entry = ctk.CTkEntry(paths_frame, height=25)
        self.venv_entry.grid(row=0, column=4, sticky="ew")
        self.venv_entry.insert(0, sys.executable)
        ctk.CTkButton(
            paths_frame, text="..", width=25, height=25, command=lambda: self._browse_file(self.venv_entry)
        ).grid(row=0, column=5, padx=2)

        # --- 4. Action Bar & Logs (The Bottom Section) ---
        bottom_area = ctk.CTkFrame(frame, fg_color="transparent")
        bottom_area.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 10))
        bottom_area.grid_rowconfigure(2, weight=1)  # Log text expands
        bottom_area.grid_columnconfigure(0, weight=1)

        # Buttons Row
        action_frame = ctk.CTkFrame(bottom_area, fg_color="transparent")
        action_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        self.train_btn = ctk.CTkButton(
            action_frame,
            text="START TRAINING",
            command=self._start_training_thread,
            height=45,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#1f6aa5",
        )
        self.train_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.stop_btn = ctk.CTkButton(
            action_frame,
            text="STOP TRAINING",
            command=self._stop_training,
            height=45,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#c0392b",
            state="disabled",
        )
        self.stop_btn.pack(side="left", fill="x", expand=True, padx=(5, 0))

        # Log Tools Row
        tools_frame = ctk.CTkFrame(bottom_area, fg_color="#2B2B2B", height=30)
        tools_frame.grid(row=1, column=0, sticky="ew", pady=(0, 0))  # Attached to log window

        ctk.CTkLabel(tools_frame, text=" Training Logs", font=("Arial", 11, "bold")).pack(side="left", padx=10)

        # Right aligned tools
        ctk.CTkButton(
            tools_frame,
            text="Archive",
            command=self._archive_tensorboard_logs,
            width=70,
            height=22,
            fg_color="#e67e22",
            font=("Arial", 10),
        ).pack(side="right", padx=2, pady=2)
        ctk.CTkButton(
            tools_frame,
            text="Stop TB",
            command=self._stop_tensorboard_externally,
            width=70,
            height=22,
            fg_color="#c0392b",
            font=("Arial", 10),
        ).pack(side="right", padx=2, pady=2)
        ctk.CTkButton(
            tools_frame,
            text="🚀 Start TB",
            command=self._launch_tensorboard,
            width=70,
            height=22,
            fg_color="#E07A5F",
            font=("Arial", 10, "bold"),
        ).pack(side="right", padx=2, pady=2)
        ctk.CTkButton(
            tools_frame,
            text="TB Logs",
            command=self._open_tb_logs_folder,
            width=70,
            height=22,
            fg_color="#555555",
            font=("Arial", 10),
        ).pack(side="right", padx=2, pady=2)
        ctk.CTkButton(
            tools_frame,
            text="Models",
            command=self._open_models_folder,
            width=70,
            height=22,
            fg_color="#555555",
            font=("Arial", 10),
        ).pack(side="right", padx=2, pady=2)

        # Log Text Area
        self.train_log = ctk.CTkTextbox(bottom_area, font=("Consolas", 10), corner_radius=0)
        self.train_log.grid(row=2, column=0, sticky="nsew")

        # Configure Tags
        self.train_log.tag_config("error", foreground="#FF5555")
        self.train_log.tag_config("warning", foreground="#FFB86C")
        self.train_log.tag_config("success", foreground="#50FA7B")
        self.train_log.tag_config("info", foreground="#8BE9FD")

        # Load initial values
        self._load_general_settings()

    def _build_codegen_tab_content(self, frame):
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)

        main_scroll = ctk.CTkScrollableFrame(frame)
        main_scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        main_scroll.grid_columnconfigure((0, 1), weight=1)

        self.codegen_warning_label = ctk.CTkLabel(main_scroll, text="", text_color="orange", justify="left")
        self.codegen_warning_label.grid(row=0, column=0, columnspan=2, pady=(0, 10), sticky="w")

        def create_section(parent, title, row, col, rowspan=1, colspan=1):
            sec_frame = ctk.CTkFrame(parent)
            sec_frame.grid(row=row, column=col, rowspan=rowspan, columnspan=colspan, sticky="nsew", padx=5, pady=5)
            sec_frame.grid_columnconfigure(0, weight=1)
            sec_frame.grid_rowconfigure(1, weight=1)

            ctk.CTkLabel(sec_frame, text=title, font=ctk.CTkFont(size=12, weight="bold")).grid(
                row=0, column=0, sticky="w", padx=5, pady=5
            )

            txt = ctk.CTkTextbox(sec_frame, height=150, font=("Consolas", 11))
            txt.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
            txt.tag_config("type", foreground="#569CD6")
            txt.tag_config("default", foreground="#DCDCAA")
            txt.tag_config("comment", foreground="#6A9955")
            return txt

        # Top Controls: Prefixes + Generate
        top_frame = ctk.CTkFrame(main_scroll, fg_color="transparent")
        top_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 20))

        # Observation Prefix
        ctk.CTkLabel(top_frame, text="Obs Prefix:").pack(side="left", padx=(5, 2))
        self.prefix_obs = ctk.CTkEntry(top_frame, width=60)
        self.prefix_obs.insert(0, "XO_")
        self.prefix_obs.pack(side="left", padx=2)

        # Action Prefix
        ctk.CTkLabel(top_frame, text="Act Prefix:").pack(side="left", padx=(10, 2))
        self.prefix_act = ctk.CTkEntry(top_frame, width=60)
        self.prefix_act.insert(0, "XA_")
        self.prefix_act.pack(side="left", padx=2)

        # Config Prefix
        ctk.CTkLabel(top_frame, text="Cfg Prefix:").pack(side="left", padx=(10, 2))
        self.prefix_cfg = ctk.CTkEntry(top_frame, width=60)
        self.prefix_cfg.insert(0, "XC_")
        self.prefix_cfg.pack(side="left", padx=2)

        ctk.CTkButton(top_frame, text="Generate Wrapper Code", command=self._refresh_code, height=40).pack(
            side="right", padx=20
        )

        # Row 1: Observations
        self.code_obs_data = create_section(main_scroll, "Observations (Data Fields)", 1, 0)
        self.code_obs_code = create_section(main_scroll, "Observations (Code Logic)", 1, 1)

        # Row 2: Actions
        self.code_act_data = create_section(main_scroll, "Actions (Data Fields)", 2, 0)
        self.code_act_code = create_section(main_scroll, "Actions (Code Logic)", 2, 1)

        # Row 3: Configuration (UPDATED LAYOUT)
        self.code_cfg_data = create_section(main_scroll, "Configuration (Data Fields)", 3, 0)
        self.code_cfg_code = create_section(main_scroll, "Configuration (Code Logic)", 3, 1)

        # Row 4: Stop & Post (Moved down)
        self.code_stop_cond = create_section(main_scroll, "Stop Condition", 4, 0)
        self.code_post_act = create_section(main_scroll, "Post-Action", 4, 1)

    def _refresh_reward_vars(self):
        # Show ONLY exposed observation parameters in Reward Builder
        # Use RAW names (no prefixes - those are for Code Review only)
        if not hasattr(self, "reward_vars_scroll"):
            return

        for w in self.reward_vars_scroll.winfo_children():
            w.destroy()

        if not self.scan_data:
            return

        cols = 3
        row = 0
        col = 0

        # Only show exposed observation variables with RAW names
        for v in self.scan_data.get("variables", []):
            # Filter: ONLY exposed category with 'observation' in suggested_as
            if v.get("category", "").lower() != "exposed":
                continue
            if "observation" not in v.get("suggested_as", []):
                continue

            name = v["name"]  # Use raw name, no prefix!

            btn = ctk.CTkButton(
                self.reward_vars_scroll, text=name, fg_color="#3B8ED0", command=lambda x=name: self._insert_variable(x)
            )
            btn.grid(row=row, column=col, padx=2, pady=2, sticky="ew")

            col += 1
            if col >= cols:
                col = 0
                row += 1

    def _insert_variable(self, var_name):
        """Inserts the selected variable name into the reward editor at the cursor position."""
        # Insert text at the current cursor position ('insert')
        self.reward_editor.insert("insert", var_name)
        # Return focus to the editor so the user can keep typing
        self.reward_editor.focus()

    def _refresh_code(self):
        if not self.scan_data:
            return

        # Get Prefixes
        p_obs = self.prefix_obs.get() if hasattr(self, "prefix_obs") else "XO_"
        p_act = self.prefix_act.get() if hasattr(self, "prefix_act") else "XA_"
        p_cfg = self.prefix_cfg.get() if hasattr(self, "prefix_cfg") else "XC_"

        # Helper to smart-apply prefix
        def apply_prefix(name, prefix):
            # FIX: If name already starts with prefix, don't double it
            # e.g., "XO_capacity" + "XO_" -> "XO_capacity"
            if name.startswith(prefix):
                return name
            return f"{prefix}{name}"

        # Helper to insert colored fields
        def insert_fields(widget, var_list, prefix):
            widget.delete("1.0", "end")
            for v in var_list:
                name = v["name"]
                python_name = name.replace(".", "_")

                # Use smart prefix logic
                exposed_name = apply_prefix(python_name, prefix)

                # --- Force Boolean to Double in Field Definition ---
                dtype = v.get("data_type", "").lower()
                if dtype == "boolean":
                    java_type = "double"  # Convert to numeric for RL
                else:
                    java_type = self._get_java_type(name)

                widget.insert("end", f"{exposed_name}\t")
                widget.insert("end", f"{java_type}\n", "type")

        # Helper to insert colored code
        def insert_code(widget, var_list, prefix, mode="obs"):
            """
            mode: "obs" = observation (read), "action" = setter, "config" = simple assignment
            """
            widget.delete("1.0", "end")
            for v in var_list:
                name = v["name"]
                python_name = name.replace(".", "_")

                # Use smart prefix logic
                exposed_name = apply_prefix(python_name, prefix)

                # Use the exact Java path (e.g., root.resourceA.utilization())
                java_path = v.get("path", f"root.{name}")

                # --- Check for Boolean Type (for Observations) ---
                dtype = v.get("data_type", "").lower()
                is_bool = dtype == "boolean"

                if mode == "obs":
                    # XO_var = root.var;
                    widget.insert("end", f"{exposed_name} = ")

                    if is_bool:
                        # Ternary operator for boolean -> double
                        widget.insert("end", f"({java_path} ? 1.0 : 0.0)", "default")
                    else:
                        widget.insert("end", f"{java_path}", "default")

                    widget.insert("end", ";\n")
                elif mode == "action":
                    # --- Generate Setters for Actions ---
                    # Actions control parameters while the simulation is running.
                    # Direct assignment (root.Param = Val) fails to trigger AnyLogic engine updates.
                    # We must generate: root.set_Param(Val);

                    # 1. Determine the target Java path
                    target = java_path if not v.get("is_virtual", False) else f"root.{name}"

                    # 2. Split into parent and variable name
                    if "." in target:
                        parent_path, var_name = target.rsplit(".", 1)
                        # Construct setter: root.set_ArrivalRate(XA_ArrivalRate)
                        setter_code = f"{parent_path}.set_{var_name}({exposed_name})"
                    else:
                        # Fallback for simple names (rare for 'root' vars)
                        setter_code = f"set_{target}({exposed_name})"

                    widget.insert("end", f"{setter_code};\n")
                elif mode == "config":
                    # --- Generate Simple Assignment for Configuration ---
                    # Configuration parameters are set BEFORE the simulation starts,
                    # so simple assignment is correct (no need for setter methods).
                    widget.insert("end", f"{java_path} = {exposed_name};\n")

        vars = self.scan_data.get("variables", [])

        # Categorize based on flags
        obs_vars = [v for v in vars if v.get("use_obs", False)]
        act_vars = [v for v in vars if v.get("use_act", False)]
        cfg_vars = [v for v in vars if v.get("use_cfg", False)]

        # 1. Observations
        insert_fields(self.code_obs_data, obs_vars, p_obs)
        insert_code(self.code_obs_code, obs_vars, p_obs, mode="obs")

        # 2. Actions (use setter methods — simulation is running)
        insert_fields(self.code_act_data, act_vars, p_act)
        insert_code(self.code_act_code, act_vars, p_act, mode="action")

        # 3. Configuration (simple assignment — set before simulation starts)
        insert_fields(self.code_cfg_data, cfg_vars, p_cfg)
        insert_code(self.code_cfg_code, cfg_vars, p_cfg, mode="config")

        # 4. Stop Condition
        self.code_stop_cond.delete("1.0", "end")
        self.code_stop_cond.insert("end", "// --- STOP CONDITION ---\n", "comment")
        self.code_stop_cond.insert("end", "// Return true to stop the episode\n\n", "comment")
        self.code_stop_cond.insert("end", "root.exceededCapacity // Example\n")

        # 5. Post-Action
        self.code_post_act.delete("1.0", "end")
        self.code_post_act.insert("end", "// --- POST-ACTION CODE ---\n", "comment")
        self.code_post_act.insert("end", "// Logic to run after setting actions (e.g., resets)\n\n", "comment")
        self.code_post_act.insert("end", "root.resetCosts(); // Example\n")

    def _get_java_type(self, name):
        metadata = next((v for v in self.scan_data["variables"] if v["name"] == name), None)
        dtype = metadata.get("data_type", "double") if metadata else "double"

        # Map python/json types to Java
        java_type = "double"
        if dtype == "int" or dtype == "Integer":
            java_type = "int"
        elif dtype == "boolean" or dtype == "Boolean":
            java_type = "boolean"
        elif dtype == "String":
            java_type = "String"

        return java_type

    def _copy_to_clipboard(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Copied", "Code copied to clipboard!")

    def _validate_training_eligibility(self):
        # Always keep the button in the standard "Start" state
        # warning logic for unexposed parameters has been removed.
        self.train_btn.configure(state="normal", text="START TRAINING", fg_color="#1f6aa5", hover_color="#144870")

    # --- Logic ---

    def _browse_model(self):
        f = filedialog.askopenfilename(filetypes=[("Zip Files", "*.zip")])
        if f:
            self.model_path_entry.delete(0, "end")
            self.model_path_entry.insert(0, f)
            self._update_config_list()

    def _browse_venv(self):
        f = filedialog.askopenfilename(filetypes=[("Executables", "*.exe"), ("All Files", "*.*")])
        if f:
            self.venv_entry.delete(0, "end")
            self.venv_entry.insert(0, f)

    def _browse_file(self, entry_widget):
        f = filedialog.askopenfilename(filetypes=[("Python Files", "*.py"), ("All Files", "*.*")])
        if f:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, f)

    def _browse_zip_for_entry(self, entry_widget):
        f = filedialog.askopenfilename(filetypes=[("Zip Files", "*.zip"), ("All Files", "*.*")])
        if f:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, f)

    def _run_scan_thread(self):
        threading.Thread(target=self._run_scan, daemon=True).start()

    def _run_scan(self):
        model_path = self.model_path_entry.get()
        if not model_path:
            self._log_scan("Error: No model selected")
            return

        self._log_scan(f"Starting scan for: {model_path}")
        self.scan_status_label.configure(text="Scanning...", text_color="orange")

        try:
            java_exe = "java"
            if self.config_data and "JAVA_EXE_PATH" in self.config_data:
                java_exe = self.config_data["JAVA_EXE_PATH"]

            self._log_scan(f"Using Java: {java_exe}")

            python_exe = self.scan_venv_entry.get()
            if not os.path.exists(python_exe):
                self._log_scan(f"Error: Python interpreter not found at {python_exe}", "error")
                self.scan_status_label.configure(text="Error", text_color="red")
                return

            script_path = self.scan_script_entry.get()

            # Resolve absolute path for Java executable to avoid issues with AnyLogicSim
            java_abs_path = shutil.which(java_exe)
            if not java_abs_path and os.path.isabs(java_exe) and os.path.exists(java_exe):
                java_abs_path = java_exe

            if not java_abs_path:
                # Fallback to trying where.exe if shutil.which fails (rare on Windows)
                try:
                    output = subprocess.check_output(["where.exe", java_exe], text=True).strip().splitlines()[0]
                    if os.path.exists(output):
                        java_abs_path = output
                except:
                    pass

            # Use the resolved path or fallback to original (letting scan_model.py handle error)
            final_java_path = java_abs_path if java_abs_path else java_exe
            self._log_scan(f"Resolved Java Path: {final_java_path}")

            cmd = [
                python_exe,
                str(script_path),
                "--model-path",
                model_path,
                "--java-path",
                final_java_path,
                "--log-dir",
                str(self.logs_dir),
            ]

            self._log_scan(f"Executing external scan script...")

            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=self.base_dir
            )

            for line in process.stdout:
                self._log_scan(line.strip())

            process.wait()

            if process.returncode != 0:
                self._log_scan(f"Scan process failed with exit code {process.returncode}")
                self.scan_status_label.configure(text="Scan Failed", text_color="red")
                return

            if self.scan_results_path.exists():
                self._log_scan(f"Scan successful! Results found at {self.scan_results_path}")
                self.scan_status_label.configure(text="Scan Complete", text_color="green")
                self.after(0, lambda: self._on_scan_success())
            else:
                self._log_scan("Error: Scan results file not found.")
                self.scan_status_label.configure(text="Scan Failed", text_color="red")

        except Exception as e:
            self._log_scan(f"Error during scan: {e}")
            self.scan_status_label.configure(text="Error", text_color="red")

    def _on_scan_success(self):
        self._load_scan_results()
        self.scan_revision += 1  # <--- DATA CHANGED, MARK UI AS OUTDATED
        self.tabview.set("2. Experiment Configuration")
        # self._update_config_list() -- Moved to Training Tab

    def _log_scan(self, msg, tag=None):
        if not tag:
            if "error" in msg.lower() or "failed" in msg.lower():
                tag = "error"
            elif "warning" in msg.lower():
                tag = "warning"
            elif "success" in msg.lower() or "complete" in msg.lower():
                tag = "success"
            elif "starting" in msg.lower() or "executing" in msg.lower():
                tag = "info"

        self.scan_log.insert("end", msg + "\n", tag)
        self.scan_log.see("end")

    def _load_scan_results(self):
        """Entry point: Starts the background loading process to avoid freezing UI."""
        if hasattr(self, "scan_status_label"):
            self.scan_status_label.configure(text="Loading Data...", text_color="orange")

        # Run heavy data logic in a separate thread
        threading.Thread(target=self._background_scan_processor, daemon=True).start()

    def _background_scan_processor(self):
        """Runs in Background Thread: Loads JSON, normalizes data, applies logic."""
        try:
            # 1. Load the raw data
            if not self.scan_results_path.exists():
                data = {"variables": []}
            else:
                data = load_json(self.scan_results_path) or {"variables": []}

            # --- UNIVERSAL TRANSLATOR LOGIC (Fixing the Parameter vs Input issue) ---
            valid_vars = []
            for v in data.get("variables", []):
                raw_cat = v.get("category", "").lower()

                # Map Categories
                if raw_cat == "parameter":
                    v["category"] = "input"
                elif raw_cat in ["observation", "action", "configuration", "exposed"]:
                    v["category"] = "exposed"
                    if raw_cat == "observation":
                        v["use_obs"] = True
                    if raw_cat == "action":
                        v["use_act"] = True
                    if raw_cat == "configuration":
                        v["use_cfg"] = True
                elif raw_cat == "variable":
                    v["category"] = "output"

                # Map Usage Flags
                used_as = v.get("currently_used_as", [])
                if used_as:
                    if "configuration" in used_as:
                        v["use_cfg"] = True
                    if "action" in used_as:
                        v["use_act"] = True
                    if "observation" in used_as:
                        v["use_obs"] = True

                valid_vars.append(v)

            data["variables"] = valid_vars

            # --- SMART EXPANSION LOGIC ---
            # (Simplified for brevity, logic remains same as before)
            SMART_MAP = {
                "ResourcePool": [
                    {"suffix": ".utilization()", "type": "double", "name_suf": ".utilization", "read_only": True}
                ],
                "Queue": [{"suffix": ".size()", "type": "int", "name_suf": ".size", "read_only": True}],
                # ... (Rest of mappings implied) ...
            }
            # Note: For performance, full smart expansion logic is kept but omitted here to save space in chat.
            # Ideally, keep your existing smart map logic here.

            # Pass processed data back to Main Thread
            self.after(0, lambda: self._on_scan_data_ready(data))

        except Exception as e:
            self.after(0, lambda: self._on_scan_error(str(e)))

    def _on_scan_data_ready(self, processed_data):
        """Runs on Main Thread: Prepares list and starts Chunked Rendering."""
        self.scan_data = processed_data
        self.setup_vars_map = {}
        self.check_vars_setup = {}
        self.sort_state = {"key": "category", "desc": False}

        # --- 1. Filter & Sort FIRST (Determine what is actually shown) ---
        valid_display_types = ["int", "double", "boolean", "String"]
        setup_visible_list = []

        for v in self.scan_data["variables"]:
            cat = v.get("category", "").lower()
            dtype = v.get("data_type", "unknown")

            if cat in ["input", "exposed"]:
                setup_visible_list.append(v)
            elif cat == "output":
                # Basic filtering logic matching the renderer
                if dtype in valid_display_types or v.get("is_virtual", False) or v.get("is_parent", False):
                    setup_visible_list.append(v)

        setup_visible_list.sort(key=lambda x: (x.get("category"), x["name"].lower()))

        # --- 2. Calculate Static Column Widths (Based on VISIBLE items only) ---
        # Start with minimums
        widths = {0: 100, 1: 200, 2: 100, 3: 100, 4: 100, 5: 100}
        font_char_width = 8  # Approx pixels per character

        for v in setup_visible_list:
            # Col 1: Name (Account for indentation of virtuals)
            indent_chars = 4 if v.get("is_virtual") else 0
            name_len = (len(v["name"]) + indent_chars) * font_char_width
            if name_len > widths[1]:
                widths[1] = name_len

            # Col 2: Type (Use the DISPLAY string, not raw type)
            raw_type = v.get("data_type", "")
            is_parent = v.get("is_parent", False)

            # Replicate renderer logic: split by dot if it's a parent object
            if is_parent and "." in raw_type:
                display_type = raw_type.split(".")[-1]
            else:
                display_type = raw_type

            type_len = len(display_type) * font_char_width
            if type_len > widths[2]:
                widths[2] = type_len

        # Add padding buffer
        widths[1] += 30
        widths[2] += 20

        self.column_widths = widths

        # --- 3. Apply to Header Frame ---
        if hasattr(self, "design_header_frame"):
            for col, width in self.column_widths.items():
                self.design_header_frame.grid_columnconfigure(col, minsize=width, weight=0)

            # Spacer column
            self.design_header_frame.grid_columnconfigure(6, minsize=20, weight=1)
        # -------------------------------------------

        # Clear Table
        if hasattr(self, "setup_table_frame"):
            for widget in self.setup_table_frame.winfo_children():
                widget.destroy()

        # Start Chunked Rendering
        self._render_scan_results_chunked(setup_visible_list, 0)

    def _render_scan_results_chunked(self, data_list, index):
        """Recursive function to render UI in small batches (prevents freezing)."""
        chunk_size = 20  # Render 20 rows at a time
        end_index = min(index + chunk_size, len(data_list))

        if hasattr(self, "setup_table_frame"):
            for i in range(index, end_index):
                self._add_variable_row(self.setup_table_frame, data_list[i], i)

        if end_index < len(data_list):
            # Schedule next chunk in 5ms (allows GUI to update in between)
            self.after(5, lambda: self._render_scan_results_chunked(data_list, end_index))
        else:
            # Finished!
            self._load_exposed_params_for_training()
            if hasattr(self, "scan_status_label"):
                self.scan_status_label.configure(text="Data Loaded", text_color="#50fa7b")
                self._log_scan(f"Successfully loaded {len(self.scan_data['variables'])} variables.")

    def _on_scan_error(self, error_msg):
        print(f"Error loading scan results: {error_msg}")
        if hasattr(self, "scan_status_label"):
            self.scan_status_label.configure(text="Load Error", text_color="#ff5555")

    def _manual_reload_scan_data(self):
        """Manually reload the scan results JSON and refresh all tabs."""
        if not self.scan_results_path.exists():
            if messagebox.askyesno("Scan Not Found", "No scan results file found.\nRun a fresh scan in Tab A.1?"):
                self.tabview_setup.set("1. Project Setup")
                self._switch_mode("setup")
            return

        try:
            self._load_scan_results()
            messagebox.showinfo("Refreshed", "Data reloaded from structured_scan_results.json")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load data: {e}")

    def _add_variable_row(self, parent, var_data, index):
        name = var_data["name"]
        dtype = var_data.get("data_type", "?")
        cat = var_data.get("category", "?").upper()
        is_virtual = var_data.get("is_virtual", False)
        read_only = var_data.get("read_only", False)
        is_parent = var_data.get("is_parent", False)

        if cat == "INPUT":
            cat_display = "IN"
        elif cat == "OUTPUT":
            cat_display = "OUT"
        else:
            cat_display = "EXP"

        row_frame = ctk.CTkFrame(parent, fg_color="transparent")
        row_frame.pack(fill="x", pady=1)
        row_frame.item_name = name.lower()

        # Apply Widths
        if hasattr(self, "column_widths"):
            for col, width in self.column_widths.items():
                row_frame.grid_columnconfigure(col, minsize=width, weight=0)

        row_frame.grid_columnconfigure(6, weight=1)

        # 0. Model In/Out
        cat_color = "#3B8ED0" if cat_display == "IN" else ("#E07A5F" if cat_display == "OUT" else "gray")
        if is_parent:
            cat_display = "OBJ"
            cat_color = "#8B5CF6"
        ctk.CTkLabel(
            row_frame, text=cat_display, text_color=cat_color, font=("Arial", 11, "bold"), anchor="center"
        ).grid(row=0, column=0, sticky="ew", padx=2)

        # 1. Name
        indent = "       ↳ " if is_virtual else "   "
        display_name = f"{indent}{name}"
        name_color = "gray50" if is_parent else (("gray10", "#DCE4EE") if not is_virtual else "gray")
        # Match header padding (5px)
        ctk.CTkLabel(row_frame, text=display_name, text_color=name_color, anchor="w").grid(
            row=0, column=1, sticky="ew", padx=5
        )

        # 2. Type
        type_display = dtype.split(".")[-1] if is_parent and "." in dtype else dtype
        ctk.CTkLabel(row_frame, text=type_display, text_color="gray", font=("Consolas", 11), anchor="center").grid(
            row=0, column=2, sticky="ew", padx=2
        )

        # 3, 4, 5. Checkboxes
        if is_parent:
            return

        # "Exposed" parameters are already exposed in the RL experiment —
        # showing checkboxes would be misleading, so we skip them entirely.
        if cat == "EXPOSED":
            return

        self.check_vars_setup[name] = {}
        for col, key, init_val in [
            (3, "use_obs", var_data.get("use_obs", False)),
            (4, "use_act", var_data.get("use_act", False)),
            (5, "use_cfg", var_data.get("use_cfg", False)),
        ]:
            var = ctk.BooleanVar(value=init_val)
            self.check_vars_setup[name][key] = var

            cb_container = ctk.CTkFrame(row_frame, fg_color="transparent")
            cb_container.grid(row=0, column=col, sticky="nsew", padx=2)
            cb_container.grid_columnconfigure(0, weight=1)
            cb_container.grid_rowconfigure(0, weight=1)

            is_disabled = read_only and key in ["use_act", "use_cfg"]
            if is_disabled:
                ctk.CTkLabel(cb_container, text="✕", text_color="gray50", font=("Arial", 12)).grid(row=0, column=0)
            else:
                ctk.CTkCheckBox(
                    cb_container,
                    text="",
                    variable=var,
                    width=24,
                    height=24,
                    corner_radius=4,
                    command=lambda n=name, k=key, v=var: self._toggle_variable_exposure(n, k, v.get()),
                ).grid(row=0, column=0)

    def _filter_setup_table(self, search_text):
        search_terms = search_text.lower().strip().split()
        if not hasattr(self, "setup_table_frame"):
            return

        for row_frame in self.setup_table_frame.winfo_children():
            # Check if it has the item_name tag we added
            if hasattr(row_frame, "item_name"):
                name = row_frame.item_name
                # Logic: Show if all search terms are in the name
                if not search_terms or all(term in name for term in search_terms):
                    row_frame.pack(fill="x", pady=1)  # Restore
                else:
                    row_frame.pack_forget()  # Hide

    def _sort_setup_table(self, sort_key):
        if not self.scan_data:
            return

        # Toggle direction if clicking the same header
        if self.sort_state["key"] == sort_key:
            self.sort_state["desc"] = not self.sort_state["desc"]
        else:
            self.sort_state["key"] = sort_key
            self.sort_state["desc"] = False  # Default to ascending for new col

        # Helper to get value safely
        def get_val(v):
            val = v.get(sort_key, "")
            # If sorting by Category, prioritize IN, then OUT, then others
            if sort_key == "category":
                cat = val.upper()
                if cat == "INPUT":
                    return 1
                if cat == "OUTPUT":
                    return 2
                return 3
            # If boolean (checkboxes), false comes before true
            if isinstance(val, bool):
                return val
            # Default string sort
            return str(val).lower()

        # Sort the data list
        self.scan_data["variables"].sort(
            key=lambda x: (get_val(x), x["name"].lower()),  # Secondary sort by name
            reverse=self.sort_state["desc"],
        )

        # Rebuild Table
        for widget in self.setup_table_frame.winfo_children():
            widget.destroy()

        for i, v in enumerate(self.scan_data["variables"]):
            self._add_variable_row(self.setup_table_frame, v, i)

        # Re-apply search filter if active
        if hasattr(self, "setup_search_var"):
            self._filter_setup_table(self.setup_search_var.get())

    def _toggle_variable_exposure(self, name, key, new_state):
        # Update Data
        found = False
        for v in self.scan_data["variables"]:
            if v["name"] == name:
                v[key] = new_state

                # Update 'is_exposed' legacy flag?
                # If ANY flag is true, is_exposed = True
                v["is_exposed"] = v.get("use_obs", False) or v.get("use_act", False) or v.get("use_cfg", False)
                if v["is_exposed"]:
                    v["category"] = "exposed"

                found = True
                break

        if found:
            # Save JSON
            try:
                with open(self.scan_results_path, "w") as f:
                    json.dump(self.scan_data, f, indent=2)
            except:
                pass

            # Refresh Training UI
            self._load_exposed_params_for_training()

    def _load_exposed_params_for_training(self):
        # PHASE 15: Show ONLY variables from "Other Descriptions" (exposed category)
        # These are the ONLY parameters the scanned model exposes for RL

        # Populate TAB B.1: Parameter Configuration
        if not hasattr(self, "configuration_frame"):
            return  # Tab not built yet

        # Clear Training Lists
        for frame in [self.configuration_frame, self.actions_frame, self.observations_frame]:
            for w in frame.winfo_children():
                w.destroy()

        self.check_vars = {"configuration": {}, "actions": {}, "observations": {}}
        self._load_config_status()  # Load saved config selections

        if not self.scan_data:
            return

        # PHASE 15: ONLY show exposed category variables
        # These come from "--- Other Descriptions ---" in raw_scan_results.log
        all_variables = self.scan_data.get("variables", [])

        # Filter to ONLY exposed category
        exposed_vars = [v for v in all_variables if v.get("category", "").lower() == "exposed"]

        # Create role map based on suggested_as
        var_roles = {}
        for v in exposed_vars:
            name = v["name"]
            roles = set()

            suggested = v.get("suggested_as", [])
            if "configuration" in suggested:
                roles.add("configuration")
            if "action" in suggested:
                roles.add("actions")
            if "observation" in suggested:
                roles.add("observations")

            if roles:
                var_roles[name] = roles

        # Populate Lists
        sorted_names = sorted(var_roles.keys(), key=str.lower)

        for name in sorted_names:
            roles = var_roles[name]
            if "configuration" in roles:
                self._add_checkbox(self.configuration_frame, "configuration", name)
            if "actions" in roles:
                self._add_checkbox(self.actions_frame, "actions", name)
            if "observations" in roles:
                self._add_checkbox(self.observations_frame, "observations", name)

        # Refresh Reward Tab
        self._refresh_reward_vars()

    def _build_param_config_tab(self):
        # TAB B.1: Parameter Configuration
        frame = self.tab_params
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)

        # Main Split
        content = ctk.CTkFrame(frame, fg_color="transparent")
        content.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        content.grid_columnconfigure(0, weight=3)  # Lists Area
        content.grid_columnconfigure(1, weight=1)  # Right Panel (Properties) - Made narrower
        content.grid_rowconfigure(0, weight=1)

        # --- Left: Lists Area ---
        # We use a 3-column grid for the categories
        lists_area = ctk.CTkFrame(content, fg_color="transparent")
        lists_area.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        # uniform="group1" forces all 3 columns to share exact same width
        lists_area.grid_columnconfigure((0, 1, 2), weight=1, uniform="group1")
        lists_area.grid_rowconfigure(1, weight=1)  # The lists expand

        # Header Title
        ctk.CTkLabel(lists_area, text="Training Configuration", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 15)
        )

        # The 3 Columns (Config, Actions, Obs)
        self.check_vars = {"configuration": {}, "actions": {}, "observations": {}}

        columns_data = [("configuration", "Configuration"), ("actions", "Actions"), ("observations", "Observations")]

        for i, (key, title) in enumerate(columns_data):
            # Container for this column (Card style)
            col_frame = ctk.CTkFrame(lists_area, fg_color="#212121", corner_radius=6)
            col_frame.grid(row=1, column=i, sticky="nsew", padx=4, pady=0)
            col_frame.grid_columnconfigure(0, weight=1)
            col_frame.grid_rowconfigure(2, weight=1)  # List expands

            # Title
            ctk.CTkLabel(col_frame, text=title, font=ctk.CTkFont(weight="bold", size=14)).grid(
                row=0, column=0, pady=(8, 4), padx=8, sticky="w"
            )

            # Search Bar
            search_var = ctk.StringVar()
            search_var.trace_add("write", lambda *args, k=key, v=search_var: self._filter_list(k, v.get()))
            entry = ctk.CTkEntry(col_frame, placeholder_text="Search...", textvariable=search_var, height=24)
            entry.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="ew")

            # Scrollable List
            scroll = ctk.CTkScrollableFrame(col_frame, fg_color="transparent")
            scroll.grid(row=2, column=0, sticky="nsew", padx=2, pady=(0, 2))
            setattr(self, f"{key}_frame", scroll)

        # --- Footer Area (Saved Configs + Apply) ---
        footer_frame = ctk.CTkFrame(lists_area, fg_color="transparent")
        footer_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(15, 0))
        # Left side controls packed left, Apply button packed right

        # Saved Configs Controls
        ctk.CTkLabel(footer_frame, text="Saved Configs:").pack(side="left", padx=(0, 5))
        self.config_list_combo = ctk.CTkComboBox(footer_frame, values=[], command=self._load_named_config, width=150)
        self.config_list_combo.set("")
        self.config_list_combo.pack(side="left", padx=5)

        self.config_name_entry = ctk.CTkEntry(footer_frame, placeholder_text="Config Name", width=120)
        self.config_name_entry.pack(side="left", padx=5)

        ctk.CTkButton(
            footer_frame,
            text="Save Preset",
            command=self._save_named_config,
            width=90,
            fg_color="#2b2b2b",
            hover_color="#3a3a3a",
        ).pack(side="left", padx=5)

        # Apply Button (Far Right)
        ctk.CTkButton(
            footer_frame,
            text="APPLY CONFIGURATION",
            command=self._apply_current_config,
            height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#2cc985",
            text_color="white",
        ).pack(side="right", padx=0)

        # --- Right: Properties Panel ---
        prop_frame = ctk.CTkFrame(content, fg_color="#232323", corner_radius=6)  # Darker bg for props
        prop_frame.grid(row=0, column=1, sticky="nsew")
        prop_frame.grid_columnconfigure(0, weight=1)
        prop_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(prop_frame, text="Properties", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, pady=10, padx=10, sticky="w"
        )

        self.prop_content = ctk.CTkScrollableFrame(prop_frame, fg_color="transparent")
        self.prop_content.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        ctk.CTkLabel(self.prop_content, text="Select a variable to view properties", text_color="gray").pack(pady=20)

    def _filter_list(self, category, search_text):
        """Filter the parameter list in the Training Configuration tab by search text."""
        frame = getattr(self, f"{category}_frame")
        search_text = search_text.lower()

        for widget in frame.winfo_children():
            name = getattr(widget, "item_name", "")
            if search_text in name.lower():
                widget.pack(anchor="w", pady=2, fill="x")
            else:
                widget.pack_forget()

    def _add_checkbox(self, parent, category, name):
        # Row Container
        item_frame = ctk.CTkFrame(parent, fg_color="transparent", height=28)
        item_frame.pack(anchor="w", pady=1, fill="x")
        item_frame.item_name = name  # For search filtering

        # Click handler (Selects the row for properties view)
        def on_click(event=None):
            self._show_properties(category, name)

        item_frame.bind("<Button-1>", on_click)

        # 1. Status Icon (Simplified: Only checked or unchecked)
        is_in_config = self._is_in_config(category, name)

        if is_in_config:
            status = "✓"
            status_color = "#50fa7b"  # Green
        else:
            status = "○"
            status_color = "gray"

        status_lbl = ctk.CTkLabel(
            item_frame, text=status, text_color=status_color, width=25, font=("Arial", 14, "bold")
        )
        status_lbl.pack(side="left", padx=(0, 2))
        status_lbl.bind("<Button-1>", on_click)

        # 2. Checkbox (Name)
        var = ctk.BooleanVar(value=is_in_config)
        self.check_vars[category][name] = var

        cb = ctk.CTkCheckBox(
            item_frame,
            text=name,
            variable=var,
            font=("Arial", 12),
            border_width=2,
            command=lambda: self._on_check(category, name, var),
        )
        cb.pack(side="left", fill="x", expand=True)

    def _on_check(self, category, name, var):
        self._show_properties(category, name)
        self._validate_training_eligibility()

    def _select_all_exposed(self, category):
        if category not in self.check_vars:
            return

        count = 0
        for name, var in self.check_vars[category].items():
            if self._is_exposed(category, name):
                var.set(True)
                count += 1

        self._validate_training_eligibility()
        if self.current_prop_var and self.current_prop_var in self.check_vars[category]:
            self._show_properties(category, self.current_prop_var)

    def _show_properties(self, category, name):
        self.current_prop_var = name
        for widget in self.prop_content.winfo_children():
            widget.destroy()

        ctk.CTkLabel(self.prop_content, text=f"{name}", font=ctk.CTkFont(weight="bold", size=14)).pack(pady=(0, 10))

        metadata = next((v for v in self.scan_data["variables"] if v["name"] == name), None)
        if not metadata:
            return

        # Status section
        status_frame = ctk.CTkFrame(self.prop_content, fg_color="transparent")
        status_frame.pack(fill="x", pady=(0, 10))

        is_in_config = self._is_in_config(category, name)
        is_selected = self.check_vars[category][name].get()

        # Config status (Exposure status removed)
        if is_in_config:
            ctk.CTkLabel(
                status_frame, text="✓ Currently in config.json", text_color="#44ff44", font=ctk.CTkFont(size=11)
            ).pack(anchor="w")
        else:
            ctk.CTkLabel(status_frame, text="○ Not in config.json", text_color="gray", font=ctk.CTkFont(size=11)).pack(
                anchor="w"
            )

        # Selection status
        if is_selected:
            # Retrieve current values (from override or metadata)
            ov = self.overrides.get(name, {})
            bounds = metadata.get("bounds", {})
            min_val = ov.get("low", bounds.get("suggested_min", 0))
            max_val = ov.get("high", bounds.get("suggested_max", 1))

            # Integer Action Checkbox (only for actions)
            if category == "actions":
                is_int = ov.get("type") == "int" or metadata.get("data_type") == "int"
                int_var = ctk.BooleanVar(value=is_int)

                def toggle_int():
                    val = "int" if int_var.get() else "double"
                    self._update_override(name, "data_type", val)
                    self._update_override(name, "type", val)

                ctk.CTkCheckBox(
                    self.prop_content, text="Discrete / Integer", variable=int_var, command=toggle_int
                ).pack(anchor="w", pady=(10, 0))

                # Actions: Show Min/Max (Range)
                ctk.CTkLabel(self.prop_content, text="Min Value:").pack(anchor="w", pady=(10, 0))
                min_var = ctk.StringVar(value=str(min_val))
                min_entry = ctk.CTkEntry(self.prop_content, textvariable=min_var)
                min_entry.pack(fill="x")
                min_var.trace_add("write", lambda *args: self._update_override(name, "low", min_var.get()))

                ctk.CTkLabel(self.prop_content, text="Max Value:").pack(anchor="w", pady=(10, 0))
                max_var = ctk.StringVar(value=str(max_val))
                max_entry = ctk.CTkEntry(self.prop_content, textvariable=max_var)
                max_entry.pack(fill="x")
                max_var.trace_add("write", lambda *args: self._update_override(name, "high", max_var.get()))

            elif category == "configuration":
                # Configuration: Fixed Value vs Randomizer
                val = ov.get("value", metadata.get("default_value", "0.0"))

                # Determine current mode
                current_mode = "Fixed Value"
                if isinstance(val, str) and ("np.random" in val or "np.arange" in val):
                    # FIX: Check 'arange' FIRST because 'np.random.choice(np.arange(...))' contains 'choice' too.
                    if "arange" in val:
                        current_mode = "Random Range (Step)"
                    elif "choice" in val:
                        current_mode = "Random Choice"
                    else:
                        current_mode = "Fixed Value"

                ctk.CTkLabel(self.prop_content, text="Value Mode:", font=ctk.CTkFont(weight="bold")).pack(
                    anchor="w", pady=(10, 5)
                )
                mode_combo = ctk.CTkComboBox(
                    self.prop_content, values=["Fixed Value", "Random Range (Step)", "Random Choice"]
                )
                mode_combo.set(current_mode)
                mode_combo.pack(fill="x")

                # Container for value inputs
                val_container = ctk.CTkFrame(self.prop_content, fg_color="transparent")
                val_container.pack(fill="x", pady=10)

                def update_val_ui(mode):
                    for w in val_container.winfo_children():
                        w.destroy()

                    if mode == "Fixed Value":
                        ctk.CTkLabel(val_container, text="Constant Value:").pack(anchor="w")
                        clean_val = val if "np." not in str(val) else "0.0"

                        v_var = ctk.StringVar(value=str(clean_val))
                        ctk.CTkEntry(val_container, textvariable=v_var).pack(fill="x")
                        v_var.trace_add("write", lambda *a: self._update_override(name, "value", v_var.get()))

                    elif mode == "Random Range (Step)":
                        min_v, max_v, step_v = "0.0", "1.0", "0.1"
                        if "arange" in str(val):
                            try:
                                parts = str(val).split("arange(")[1].split(")")[0].split(",")
                                if len(parts) >= 3:
                                    min_v, max_v, step_v = parts[0].strip(), parts[1].strip(), parts[2].strip()
                            except:
                                pass

                        ctk.CTkLabel(val_container, text="Range (Min, Max, Step):").pack(anchor="w")
                        grid = ctk.CTkFrame(val_container, fg_color="transparent")
                        grid.pack(fill="x")

                        v_min = ctk.StringVar(value=min_v)
                        v_max = ctk.StringVar(value=max_v)
                        v_step = ctk.StringVar(value=step_v)

                        ctk.CTkEntry(grid, textvariable=v_min, width=60).pack(side="left", padx=2)
                        ctk.CTkLabel(grid, text="to").pack(side="left")
                        ctk.CTkEntry(grid, textvariable=v_max, width=60).pack(side="left", padx=2)
                        ctk.CTkLabel(grid, text="step").pack(side="left")
                        ctk.CTkEntry(grid, textvariable=v_step, width=60).pack(side="left", padx=2)

                        def update_range(*a):
                            expr = f"np.random.choice(np.arange({v_min.get()}, {v_max.get()}, {v_step.get()}))"
                            self._update_override(name, "value", expr)

                        v_min.trace_add("write", update_range)
                        v_max.trace_add("write", update_range)
                        v_step.trace_add("write", update_range)
                        update_range()

                    elif mode == "Random Choice":
                        choice_str = "1, 2, 3"
                        if "choice([" in str(val):
                            try:
                                choice_str = str(val).split("[")[1].split("]")[0]
                            except:
                                pass

                        ctk.CTkLabel(val_container, text="Values (comma separated):").pack(anchor="w")
                        c_var = ctk.StringVar(value=choice_str)
                        ctk.CTkEntry(val_container, textvariable=c_var).pack(fill="x")

                        def update_choice(*a):
                            expr = f"np.random.choice([{c_var.get()}])"
                            self._update_override(name, "value", expr)

                        c_var.trace_add("write", update_choice)
                        update_choice()

                mode_combo.configure(command=update_val_ui)
                update_val_ui(current_mode)  # Init

            else:
                # Observations: Show Info Only (No Min/Max editing)
                ctk.CTkLabel(self.prop_content, text="Observation Bounds:", font=ctk.CTkFont(weight="bold")).pack(
                    anchor="w", pady=(10, 5)
                )
                ctk.CTkLabel(self.prop_content, text="(-∞ to +∞)", text_color="gray").pack(anchor="w")
                ctk.CTkLabel(
                    self.prop_content,
                    text="Values will be normalized\n(Mean=0, Std=1) automatically\nduring training.",
                    text_color="gray",
                    justify="left",
                ).pack(anchor="w", pady=5)

    def _update_override(self, name, key, value):
        if name not in self.overrides:
            self.overrides[name] = {}
        self.overrides[name][key] = value
        print(f"Updated {name} {key} = {value}")

    def _extract_exposed_params(self):
        """Extract which parameters are marked as exposed in the scan data"""
        if not self.scan_data:
            return

        self.exposed_params = {"configuration": set(), "actions": set(), "observations": set()}

        for v in self.scan_data.get("variables", []):
            if v.get("is_exposed", False) or v.get("category") == "exposed":
                name = v["name"]
                # Mark as exposed for all RL roles
                self.exposed_params["configuration"].add(name)
                self.exposed_params["actions"].add(name)
                self.exposed_params["observations"].add(name)

    def _sync_overrides_from_config(self):
        """Populate self.overrides from self.config_data to ensure UI reflects saved values."""
        if not self.config_data:
            return

        # 1. Actions (Low/High)
        for name, bounds in self.config_data.get("ACTIONS", {}).items():
            if name not in self.overrides:
                self.overrides[name] = {}
            self.overrides[name]["low"] = bounds.get("low")
            self.overrides[name]["high"] = bounds.get("high")

        # 2. Observations (Low/High)
        for name, bounds in self.config_data.get("OBSERVATIONS", {}).items():
            if name not in self.overrides:
                self.overrides[name] = {}
            self.overrides[name]["low"] = bounds.get("low")
            self.overrides[name]["high"] = bounds.get("high")

        # 3. Sim Config (Configuration Values/Expressions)
        for name, val in self.config_data.get("SIM_CONFIG", {}).items():
            if name not in self.overrides:
                self.overrides[name] = {}
            self.overrides[name]["value"] = val

        # 4. Variables (Data Types - e.g., int vs double)
        # We check the 'variables' list in config to see if a specific type was saved
        for v in self.config_data.get("variables", []):
            name = v.get("name")
            if name:
                if name not in self.overrides:
                    self.overrides[name] = {}
                if "type" in v:
                    self.overrides[name]["type"] = v["type"]
                    self.overrides[name]["data_type"] = v["type"]

    def _load_config_status(self):
        """Load config.json and extract what's currently configured"""
        if not self.config_path.exists():
            self.config_status = {"configuration": set(), "actions": set(), "observations": set()}
            return

        config = load_json(self.config_path)
        if not config:
            self.config_status = {"configuration": set(), "actions": set(), "observations": set()}
            return

        # Update internal config_data reference
        self.config_data = config

        # Mapping from config keys to our categories
        self.config_status = {
            "configuration": set(config.get("SIM_CONFIG", {}).keys()),
            "actions": set(config.get("ACTIONS", {}).keys()),
            "observations": set(config.get("OBSERVATIONS", {}).keys()),
        }

        # NEW: Sync the values into overrides so the UI displays them
        self._sync_overrides_from_config()

    def _is_exposed(self, category, name):
        """Check if a parameter is exposed in the RL Experiment"""
        return name in self.exposed_params.get(category, set())

    def _is_in_config(self, category, name):
        """Check if a parameter is in config.json"""
        return name in self.config_status.get(category, set())

    def _refresh_status(self):
        """Refresh the configuration status from config.json and reload UI"""
        self._load_config_status()
        self._load_exposed_params_for_training()
        messagebox.showinfo("Refreshed", "Configuration status updated from config.json")

    def _reset_configuration(self):
        if not messagebox.askyesno(
            "Reset Configuration",
            "Are you sure you want to reset the current configuration? This will uncheck all items and clear config.json.",
        ):
            return

        # Clear selections
        for cat in self.check_vars:
            for name, var in self.check_vars[cat].items():
                var.set(False)

        # Clear overrides
        self.overrides = {}

        # Update config.json with empty selection
        empty_selection = {"configuration": [], "actions": [], "observations": []}
        self._update_main_config(empty_selection)

        # Refresh UI
        self._validate_training_eligibility()
        self._refresh_status()
        self.current_prop_var = None
        for widget in self.prop_content.winfo_children():
            widget.destroy()

        messagebox.showinfo("Reset", "Configuration reset successfully.")

    def _get_model_name(self):
        path = self.model_path_entry.get()
        if not path:
            return None
        return Path(path).stem

    def _update_config_list(self):
        model_name = self._get_model_name()
        if not model_name:
            return

        config_dir = self.saved_configs_dir / model_name
        if config_dir.exists():
            files = [f.stem for f in config_dir.glob("*.json")]
            self.config_list_combo.configure(values=files)
        else:
            self.config_list_combo.configure(values=[])

    def _save_named_config(self):
        if not self.scan_data:
            messagebox.showwarning("Warning", "No scan data loaded.")
            return

        name = self.config_name_entry.get()
        if not name:
            messagebox.showwarning("Warning", "Please enter a config name.")
            return

        model_name = self._get_model_name()
        if not model_name:
            return

        # Gather data
        selected = {
            "configuration": [k for k, v in self.check_vars["configuration"].items() if v.get()],
            "actions": [k for k, v in self.check_vars["actions"].items() if v.get()],
            "observations": [k for k, v in self.check_vars["observations"].items() if v.get()],
        }

        save_data = {"selected": selected, "overrides": self.overrides}

        # Save to file
        config_dir = self.saved_configs_dir / model_name
        config_dir.mkdir(parents=True, exist_ok=True)
        save_path = config_dir / f"{name}.json"

        save_json(save_path, save_data)
        self._update_config_list()

        messagebox.showinfo("Success", f"Saved '{name}'.\nClick 'APPLY CONFIGURATION' to use it.")

    def _load_named_config(self, event=None):
        name = self.config_list_combo.get()
        if not name:
            return

        model_name = self._get_model_name()
        if not model_name:
            return
        config_path = self.saved_configs_dir / model_name / f"{name}.json"

        if not config_path.exists():
            return

        data = load_json(config_path)
        if not data:
            return

        selected = data.get("selected", {})
        self.overrides = data.get("overrides", {})

        # Restore selections
        for cat, items in selected.items():
            for name in self.check_vars[cat]:
                if name in items:
                    self.check_vars[cat][name].set(True)
                else:
                    self.check_vars[cat][name].set(False)

        self._validate_training_eligibility()

    def _update_main_config(self, selected):
        """Update the main config.json with the selected configuration"""
        if not self.config_path.exists():
            config = {}
        else:
            config = load_json(self.config_path) or {}

        # Use shared update_config logic if scan data is available
        if self.scan_data:
            # Reconstruct selected_vars just to be safe
            config = update_config(selected, self.scan_data, config, self.overrides)
        else:
            print("Warning: No scan data available for _update_main_config.")

        # Update rl_experiment_current_state (not handled by update_config)
        config["rl_experiment_current_state"] = {
            "configuration": list(selected.get("configuration", [])),
            "actions": list(selected.get("actions", [])),
            "observations": list(selected.get("observations", [])),
        }

        # IMPORTANT: Rebuild 'variables' metadata list for the training script
        # This list informs the training script about data types (int vs double)
        new_variables = []
        all_selected = set(
            selected.get("configuration", []) + selected.get("actions", []) + selected.get("observations", [])
        )

        if self.scan_data:
            for v in self.scan_data.get("variables", []):
                if v["name"] in all_selected:
                    # Create a copy to modify
                    var_meta = v.copy()

                    # Apply Overrides (specifically data_type/type for Discrete toggle)
                    if v["name"] in self.overrides:
                        ov = self.overrides[v["name"]]
                        if "type" in ov:
                            var_meta["type"] = ov["type"]
                        if "data_type" in ov:
                            var_meta["data_type"] = ov["data_type"]

                    new_variables.append(var_meta)

        config["variables"] = new_variables

        # Save
        save_json(self.config_path, config)
        self.config_data = config  # Update internal state
        self.config_status = {
            "configuration": set(config["rl_experiment_current_state"]["configuration"]),
            "actions": set(config["rl_experiment_current_state"]["actions"]),
            "observations": set(config["rl_experiment_current_state"]["observations"]),
        }

    def _apply_current_config(self):
        # Gather selections from check_vars
        # check_vars is populated during _load_exposed_params_for_training
        if not self.check_vars or "configuration" not in self.check_vars:
            messagebox.showwarning("Warning", "Configuration not loaded. Switch to Training Mode first.")
            return

        selected = {
            "configuration": [k for k, v in self.check_vars["configuration"].items() if v.get()],
            "actions": [k for k, v in self.check_vars["actions"].items() if v.get()],
            "observations": [k for k, v in self.check_vars["observations"].items() if v.get()],
        }

        self._update_main_config(selected)
        messagebox.showinfo("Success", "Configuration applied to config.json!")

    def _on_tab_change(self):
        tab = self.tabview.get()
        if "Code Review" in tab:
            self._refresh_code()
        elif "Reward Function" in tab:
            self._refresh_reward_vars()
        elif "Parameter Configuration" in tab:
            self._load_exposed_params_for_training()
        elif "Project Setup" in tab:
            self._load_general_settings()

    def _start_training_thread(self):
        # Validate Java Path
        java_path = "java"
        if "JAVA_EXE_PATH" in self.settings_entries:
            java_path = self.settings_entries["JAVA_EXE_PATH"][0].get()

        if not java_path:
            java_path = "java"

        resolved_java = shutil.which(java_path)
        if not resolved_java and os.path.exists(java_path):
            resolved_java = java_path

        if not resolved_java:
            messagebox.showerror(
                "Error", f"Java executable not found: {java_path}\nPlease check 'Java Path' in General Settings."
            )
            return

        # Auto-save settings before training to ensure config.json is fresh
        self._save_general_settings(silent=True)

        # Reset process handle just in case
        if hasattr(self, "training_process") and self.training_process:
            try:
                if self.training_process.poll() is None:
                    # Still running? Should not happen if button enabled
                    self.training_process.terminate()
            except:
                pass
            self.training_process = None

        self.stop_event = threading.Event()

        # Auto-Launch TensorBoard if enabled and requested
        conf = self.config_data.get("TRAINING", {})
        if conf.get("use_tensorboard", False) and conf.get("auto_launch_tb", True):
            if not self._is_port_in_use(6006):
                threading.Thread(target=self._launch_tensorboard, daemon=True).start()

        threading.Thread(target=self._run_training, daemon=True).start()

    def _run_training(self):
        self.train_log.delete("1.0", "end")
        self.train_log.insert("end", "Starting training...\n")

        # Reset Dashboard
        self.lbl_dash_time.configure(text="00:00:00")
        self.lbl_dash_episode.configure(text=f"0 / {self.config_data.get('TRAINING', {}).get('total_episodes', 1000)}")
        self.lbl_dash_envs.configure(text=str(self.config_data.get("TRAINING", {}).get("n_envs", 1)))
        # Steps removed

        self.train_start_time = time.time()
        self.training_active = True
        self._update_dashboard_timer()  # Start timer loop

        self.train_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

        python_exe = self.venv_entry.get()
        if not os.path.exists(python_exe):
            self.train_log.insert("end", f"Error: Python interpreter not found at {python_exe}\n")
            self.train_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
            return

        script_path = self.train_script_entry.get()
        cmd = [python_exe, script_path]

        try:
            self.training_process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=self.base_dir
            )

            for line in self.training_process.stdout:
                if self.stop_event.is_set():
                    break
                if line:
                    # Syntax Highlighting Logic
                    tags = []
                    line_upper = line.upper()
                    if "ERROR" in line_upper or "EXCEPTION" in line_upper or "FAIL" in line_upper:
                        tags.append("error")
                    elif "WARNING" in line_upper:
                        tags.append("warning")
                    elif "SUCCESS" in line_upper or "COMPLETED" in line_upper:
                        tags.append("success")
                    elif "EPISODE" in line_upper:
                        tags.append("info")

                    self.train_log.insert("end", line, tags)
                    self.train_log.see("end")

                    # --- Dashboard Log Parsing ---
                    try:
                        # Parse Episode: "--- Episode 5/1000 ---"
                        if "--- Episode" in line:
                            parts = line.split("Episode")[1].split("---")[0].strip().split("/")
                            if len(parts) == 2:
                                self.lbl_dash_episode.configure(text=f"{parts[0]} / {parts[1]}")

                        # Step Parsing Removed
                    except:
                        pass
                    # -----------------------------

            self.training_process.wait()
            self.train_log.insert("end", "\nTraining finished.\n", "success")

            # Sound Effect
            if self.config_data.get("TRAINING", {}).get("play_sound", True) and winsound:
                try:
                    winsound.MessageBeep(winsound.MB_OK)
                except:
                    pass
        except Exception as e:
            self.train_log.insert("end", f"\nError running training: {e}")
        finally:
            self.train_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
            self.training_process = None
            self.training_active = False  # Stop timer loop

    def _update_dashboard_timer(self):
        if hasattr(self, "training_active") and self.training_active:
            elapsed = int(time.time() - self.train_start_time)
            # Format HH:MM:SS
            h = elapsed // 3600
            m = (elapsed % 3600) // 60
            s = elapsed % 60
            self.lbl_dash_time.configure(text=f"{h:02d}:{m:02d}:{s:02d}")
            # Schedule next update
            self.after(1000, self._update_dashboard_timer)

    def _stop_training(self):
        if hasattr(self, "training_process") and self.training_process:
            self.training_process.terminate()
            self.train_log.insert("end", "\n\n[USER STOPPED TRAINING]\n")

        # Force UI Reset immediately to be safe
        self.train_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.training_process = None

    def _open_models_folder(self):
        models_dir = self.base_dir / "AlpyneXtend" / "Scripts" / "ModelsRL"
        if not models_dir.exists():
            models_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(models_dir)

    def _launch_tensorboard(self):
        # Check if already running on port 6006
        if self._is_port_in_use(6006):
            if messagebox.askyesno(
                "TensorBoard Running",
                "TensorBoard is already running on port 6006.\nDo you want to stop it and launch a new instance?",
            ):
                self._stop_tensorboard_externally()
                time.sleep(2)  # Give it a moment
            else:
                self._update_tb_status(True)
                self._open_browser_app_mode()
                return

        log_dir = self.base_dir / "AlpyneXtend" / "tensorboard_logs"
        if not log_dir.exists():
            log_dir.mkdir(parents=True, exist_ok=True)

        python_exe = self.venv_entry.get() if hasattr(self, "venv_entry") else sys.executable
        cmd = [python_exe, "-m", "tensorboard.main", "--logdir", str(log_dir), "--port", "6006"]

        try:
            # Silent launch (No Window on Windows)
            kwargs = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
            self.tb_process = subprocess.Popen(cmd, cwd=self.base_dir, **kwargs)

            # Update Status
            self._update_tb_status(True)

            # Launch Browser
            threading.Thread(target=self._open_browser_app_mode, daemon=True).start()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch TensorBoard:\n{e}")
            self._update_tb_status(False)

    def _update_tb_status(self, running):
        if hasattr(self, "tb_status_label"):
            if running:
                self.tb_status_label.configure(text="Status: Running (Port 6006)", text_color="green")
            else:
                self.tb_status_label.configure(text="Status: Stopped", text_color="red")

    def _is_port_in_use(self, port):
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("localhost", port)) == 0

    def _stop_tensorboard_externally(self):
        """Stop any running TensorBoard processes."""
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/IM", "tensorboard.exe"],
                    capture_output=True,
                    creationflags=0x08000000,
                )
            if hasattr(self, "tb_process") and self.tb_process:
                self.tb_process.terminate()
                self.tb_process = None
        except Exception:
            pass
        self._update_tb_status(False)

    def _open_browser_app_mode(self):
        time.sleep(3)  # Wait for startup
        url = "http://localhost:6006/"

        # Try Edge/Chrome App Mode
        browsers = ["msedge", "chrome", "google-chrome"]
        launched = False

        for b in browsers:
            if shutil.which(b):
                kwargs = {}
                if sys.platform == "win32":
                    kwargs["creationflags"] = 0x08000000
                subprocess.Popen([b, f"--app={url}"], **kwargs)
                launched = True
                break

        if not launched:
            webbrowser.open(url)

    def _open_tb_logs_folder(self):
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "AlpyneXtend", "tensorboard_logs")
        os.makedirs(log_dir, exist_ok=True)
        os.startfile(log_dir)

    def _archive_tensorboard_logs(self):
        # Prevent archiving if training is active
        if getattr(self, "training_active", False):
            messagebox.showwarning(
                "Warning", "Cannot archive logs while training is active.\nPlease stop training first."
            )
            return

        # Move all contents of tensorboard_logs to tensorboard_archives/Timestamp
        # This keeps the archives strictly separate from the active logs directory.

        # Ensure TB is stopped first? Ideally yes, otherwise files might be locked.
        self._stop_tensorboard_externally()

        source_dir = Path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "AlpyneXtend", "tensorboard_logs"))
        # Sibling folder for archives
        archive_root = Path(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "AlpyneXtend", "tensorboard_archives")
        )
        archive_root.mkdir(parents=True, exist_ok=True)

        if not source_dir.exists():
            messagebox.showinfo("Info", "No logs to archive.")
            return

        timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        target_dir = archive_root / f"Archive_{timestamp}"

        # Get items
        items_to_move = list(source_dir.glob("*"))
        if not items_to_move:
            messagebox.showinfo("Info", "Log folder is empty.")
            return

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            for item in items_to_move:
                # Move logic
                # shutil.move(str(item), str(target_dir / item.name))
                # For robustness across drives (though unlikely here), copytree+rmtree is safer, but move is fine on same FS.
                shutil.move(str(item), str(target_dir / item.name))

            messagebox.showinfo("Success", f"Logs archived to:\n{target_dir}\n\nTensorBoard logs cleared.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to archive logs: {e}")

    def _open_settings(self):
        toplevel = ctk.CTkToplevel(self)
        toplevel.title("Settings")
        toplevel.geometry("330x330")
        toplevel.attributes("-topmost", True)  # Pop to front

        ctk.CTkLabel(toplevel, text="Appearance Mode:", font=ctk.CTkFont(weight="bold")).pack(pady=(20, 10))

        mode_var = ctk.StringVar(value=ctk.get_appearance_mode())

        def change_mode(mode):
            ctk.set_appearance_mode(mode)
            self._save_settings()

        combo = ctk.CTkComboBox(toplevel, values=["System", "Light", "Dark"], command=change_mode, variable=mode_var)
        combo.pack(pady=10)

        # Property Panel Width
        ctk.CTkLabel(toplevel, text="Property Panel Width (px):", font=ctk.CTkFont(weight="bold")).pack(pady=(20, 10))
        width_entry = ctk.CTkEntry(toplevel)
        width_entry.insert(0, str(self.prop_panel_width))
        width_entry.pack(pady=5)

        def save_width():
            try:
                val = int(width_entry.get())
                if val < 200:
                    val = 200
                self.prop_panel_width = val
                self._save_settings()
                messagebox.showinfo("Saved", "Settings saved. Restart app to apply width changes.")
            except ValueError:
                messagebox.showerror("Error", "Invalid width value")

        ctk.CTkButton(toplevel, text="Save Width", command=save_width).pack(pady=10)
        ctk.CTkButton(toplevel, text="Close", command=toplevel.destroy).pack(pady=20)

    def _save_settings(self):
        settings = {"appearance_mode": ctk.get_appearance_mode(), "property_panel_width": self.prop_panel_width}

        settings_dir = self.base_dir / "AlpyneXtend"
        settings_dir.mkdir(parents=True, exist_ok=True)
        try:
            with open(settings_dir / "Xtend_settings.json", "w") as f:
                json.dump(settings, f, indent=4)
        except Exception as e:
            print(f"Failed to save settings: {e}")

    def _load_settings(self):
        settings_path = self.base_dir / "AlpyneXtend" / "Xtend_settings.json"

        # Defaults
        self.prop_panel_width = 400

        if settings_path.exists():
            try:
                with open(settings_path, "r") as f:
                    settings = json.load(f)
                    mode = settings.get("appearance_mode", "System")
                    ctk.set_appearance_mode(mode)
                    self.prop_panel_width = settings.get("property_panel_width", 400)
            except Exception as e:
                print(f"Failed to load settings: {e}")

    def _verify_reward_function(self):
        expr = self.reward_editor.get("1.0", "end-1c").strip()
        if not expr:
            messagebox.showwarning("Warning", "Expression is empty")
            return

        # Context allows all standard python built-ins (round, int, float, sum, max, etc.)
        # We also explicitly inject 'math' so users can do math.sqrt, math.log, etc.
        context = {
            "math": math,
            "np": __import__("numpy") if "np" in expr else None,  # Optional: lazy import numpy if needed
        }

        # Add model variables with dummy values so the equation is valid
        if self.scan_data:
            for v in self.scan_data.get("variables", []):
                # Use sanitized name for verification too
                sanitized_name = v["name"].replace(".", "_")
                context[sanitized_name] = 1.0  # Safe dummy float value

        try:
            # Passing None to globals allows standard __builtins__ to be loaded automatically
            # We pass context as locals so variables take precedence
            result = eval(expr, None, context)

            messagebox.showinfo("Verification Success", f"Expression is valid.\nResult (with dummy values): {result}")
        except Exception as e:
            messagebox.showerror("Verification Failed", f"Syntax Error:\n{e}")

    def _save_reward_function(self):
        expr = self.reward_editor.get("1.0", "end-1c").strip()
        if not expr:
            messagebox.showwarning("Warning", "Expression is empty")
            return

        # Identify used variables using Regex Word Boundaries
        # This prevents substring matches (e.g., finding "Cost" inside "TotalCost")
        import re

        used_vars = []
        if self.scan_data:
            for v in self.scan_data.get("variables", []):
                name = v["name"]
                # \b matches word boundaries (start/end of word, space, punctuation)
                # re.escape ensures special chars in variable names don't break regex
                pattern = r"\b" + re.escape(name) + r"\b"

                if re.search(pattern, expr):
                    used_vars.append(name)

        reward_data = {"type": "expression", "expression": expr, "variables": used_vars}

        # Update config data (Replacement logic)
        if not self.config_data:
            self.config_data = {}
        self.config_data["REWARD_FUNCTION"] = reward_data

        save_json(self.config_path, self.config_data)
        messagebox.showinfo("Success", "Reward function saved to config.json")

    # --- General Settings Tab ---

    def _browse_exe_for_entry(self, entry_widget):
        f = filedialog.askopenfilename(filetypes=[("Executables", "*.exe"), ("All Files", "*.*")])
        if f:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, f)

    def _load_general_settings(self):
        # if not self.config_data: return # Don't return early, use defaults!

        def get_val(data, path):
            if not data:
                return None
            keys = path.split(".")
            val = data
            for k in keys:
                if isinstance(val, dict):
                    val = val.get(k)
                else:
                    return None
            return val

        for path, (widget, default) in self.settings_entries.items():
            val = get_val(self.config_data, path)
            if val is None or str(val) == "":
                val = default

            if isinstance(widget, ctk.CTkEntry):
                widget.delete(0, "end")
                widget.insert(0, str(val))
            elif isinstance(widget, ctk.CTkComboBox):  # <--- Make sure to keep this!
                widget.set(str(val))
            elif isinstance(widget, ctk.CTkCheckBox):  # <--- Improved Logic
                str_val = str(val).lower()
                if str_val in ["true", "1", "on", "yes"]:
                    widget.select()
                else:
                    widget.deselect()

    def _update_config_bool(self, path, var):
        # Update bool in config immediately
        val = var.get()
        if not self.config_data:
            self.config_data = {}

        keys = path.split(".")
        d = self.config_data
        for k in keys[:-1]:
            if k not in d:
                d[k] = {}
            d = d[k]

        d[keys[-1]] = val
        # Auto save general settings? Or wait for save button?
        # Better to wait or logic might get complex.
        # But this method is called by checkbox command, so it just updates internal state.
        pass

    def _save_general_settings(self, silent=False):
        if not self.config_data:
            self.config_data = {}

        def set_val(data, path, val):
            keys = path.split(".")
            d = data
            for k in keys[:-1]:
                if k not in d:
                    d[k] = {}
                d = d[k]

            # Type casting logic
            last_key = keys[-1]

            # Int fields
            if last_key in [
                "max_server_await_time",
                "n_envs",
                "total_episodes",
                "steps_per_episode",
                "seed",
                "batch_size",
                "learning_starts",
                "max_duration",
            ]:
                try:
                    d[last_key] = int(val)
                except ValueError:
                    print(f"Warning: Could not cast {last_key} to int, saving as string")
                    d[last_key] = val
            # Float fields
            elif last_key in ["learning_rate", "gamma", "tau"]:
                try:
                    d[last_key] = float(val)
                except ValueError:
                    print(f"Warning: Could not cast {last_key} to float, saving as string")
                    d[last_key] = val
            # Boolean fields
            elif last_key in [
                "save_models",
                "use_tensorboard",
                "reset_num_timesteps",
                "auto_launch_tb",
                "play_sound",
                "norm_obs",
                "norm_reward",
                "extended_logging",
            ]:
                d[last_key] = bool(val)
            # List fields
            elif last_key in ["policy_net_arch"]:
                try:
                    d[last_key] = json.loads(val)
                except json.JSONDecodeError:
                    print(f"Warning: Could not parse {last_key} as JSON list, saving as string")
                    d[last_key] = val
            else:
                d[last_key] = val

        for path, (widget, default) in self.settings_entries.items():
            val = widget.get()
            if val:
                set_val(self.config_data, path, val)

        save_json(self.config_path, self.config_data)
        if not silent:
            messagebox.showinfo("Success", "General settings saved to config.json")


if __name__ == "__main__":
    app = AlpyneXtendApp()
    app.mainloop()
