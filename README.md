# Alpyne-Xtend

**A GUI-driven extension for [Alpyne](https://github.com/the-anylogic-company/Alpyne) that bridges AnyLogic simulation models with Reinforcement Learning frameworks — without writing boilerplate code.**

---

## What This Is

[Alpyne](https://github.com/the-anylogic-company/Alpyne) (the **A**ny**L**ogic-**Py**thon con**ne**ctor) allows Python to interact with simulation models exported from AnyLogic's RL Experiment. It is a powerful library, but connecting a model to a training pipeline requires significant manual work: defining observation/action spaces, writing reward functions, configuring hyperparameters, and producing the Java glue code for the RL Experiment fields.

**Alpyne-Xtend** automates this workflow through a desktop application that:

1. **Scans** your exported AnyLogic model to discover all available variables, parameters, and their types.
2. **Lets you configure** which variables serve as observations, actions, and configuration — via point-and-click selection.
3. **Generates** the Java code snippets to paste into AnyLogic's RL Experiment fields.
4. **Builds** the `config.json` that drives the training scripts (reward function, hyperparameters, spaces, bounds).
5. **Runs** SAC-based RL training with [Stable Baselines3](https://github.com/DLR-RM/stable-baselines3), including TensorBoard integration, model checkpointing, and parallel environments.
6. **Evaluates** trained models against the simulation.

The project also includes a **modified Alpyne server JAR** (`Library-Release/`) that extends the original with model scanning capabilities used by the GUI.

---

## Repository Structure

```
Software/
├── App/                            # The Alpyne-Xtend application
│   ├── AlpyneXtend_App.py         # Main GUI application (CustomTkinter)
│   ├── AlpyneXtend_PyQt6.py       # Alternative GUI (PyQt6, incomplete)
│   ├── requirements.txt           # Python dependencies
│   └── AlpyneXtend/
│       ├── config.json            # Generated training configuration
│       ├── Configs/               # Saved configuration presets for example models
│       └── Scripts/
│           ├── train_agent.py     # SAC training script
│           ├── test_agent.py      # Model evaluation script
│           ├── train_bayes_opt.py # Bayesian Optimization script
│           ├── scan_server.py     # Model scanning (with log parsing)
│           ├── diagnostic_scan.py # Unfiltered diagnostic scan
│           ├── generate_rl_code.py# Java/Python code generation
│           └── config_utils.py    # Configuration file utilities
│
├── Library-Dev/                   # Modified Alpyne server (Java source)
│   ├── src/                       # Decompiled + modified Java sources
│   └── pom.xml                    # Maven build file
│
└── Library-Release/               # Modified Alpyne Python library
    ├── alpyne/                    # Python library (patched for Xtend)
    │   └── resources/
    │       ├── alpyne-1.2.0.jar   # Compiled modified server JAR
    │       └── alpyne_lib/        # Server dependencies
    └── setup.py
```

---

## Prerequisites

- **AnyLogic** 8.8.6+ (PLE, University, or Professional edition)
- **Java** 17+ (the JRE bundled with AnyLogic works — typically at `<AnyLogic>/jre/bin/java.exe`)
- **Python** 3.10+

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/AhmetAkyuez/alpyne-xtend.git
cd alpyne-xtend/Software
```

### 2. Install Python Dependencies

> **Note:** If you are familiar with Python virtual environments, it is recommended to create one first (`python -m venv .venv`) and activate it before proceeding. If you are unsure what that means, you can skip this and install directly — it will work fine.

Install the modified Alpyne library (this replaces the official `anylogic-alpyne` package):

```bash
pip install ./Library-Release
```

Then install the remaining dependencies:

```bash
pip install stable-baselines3[extra] customtkinter bayesian-optimization
```

This installs:

- **Stable Baselines3** — RL algorithms (SAC, PPO, DQN) with TensorBoard support
- **CustomTkinter** — Modern GUI framework for the application
- **bayesian-optimization** — For the Bayesian Optimization training mode

### 3. Verify Installation

```bash
python -c "import alpyne; import stable_baselines3; import customtkinter; print('All dependencies OK')"
```

---

## Usage

### Preparing Your AnyLogic Model

Before using Alpyne-Xtend, you need to prepare your AnyLogic model. If you have never used Alpyne before, here is what you need to know:

1. **Add an RL Experiment** to your AnyLogic model. In the AnyLogic IDE, right-click your model in the Projects panel → _New_ → _Experiment_ → _Reinforcement Learning_. This creates a special experiment type that Alpyne uses to communicate with the simulation.

2. **Add a `takeAction` call** somewhere in your model logic. This is the moment where the simulation pauses and asks the RL agent: _"What should I do now?"_. Place it at a decision point that makes sense for your problem — for example, in an event that fires periodically, or in an `On exit` action of a flowchart block. Without this call, the simulation will run to completion without ever consulting the agent.

   ```java
   // Example: inside a cyclic event or flowchart block
   get_Main().takeAction();
   ```

3. **Define a stop condition** in the RL Experiment properties. This tells the simulation when an episode ends — typically a time limit (e.g., `time() >= 480` for an 8-hour shift) or a model condition (e.g., `root.allOrdersCompleted`).

4. **Export the model**: In the RL Experiment properties, click the export button at the top. Save the resulting `.zip` file somewhere accessible. You do **not** need to fill in the Configuration, Observation, or Action fields yet — Alpyne-Xtend will help you generate those.

> For more background on preparing AnyLogic models for RL, see the [official Alpyne documentation](https://the-anylogic-company.github.io/Alpyne/components-rlready-model.html).

### Launching the Application

```bash
cd Software/App
python AlpyneXtend_App.py
```

The application is organized in three phases: **Setup → Training → Testing**.

### Phase A: Setup

This phase is a two-pass process. You scan the model once to discover its variables, configure the RL interface in Alpyne-Xtend, paste the generated code back into AnyLogic, and then re-export and re-scan.

1. **Project Setup** (Tab A.1)

   - **Model Path**: Point the application to the `.zip` file you exported from AnyLogic (see above).
   - **Java Executable**: Set the path to a Java 17+ installation. The easiest option is the JRE bundled with AnyLogic, typically found at `C:/Program Files/AnyLogic <version>/jre/bin/java.exe` on Windows.
   - Click **Run Model Scan**. The application starts the AnyLogic model in the background, introspects all available variables (parameters, statistics, resource pools, etc.), and presents them in the next tab.

2. **Experiment Configuration** (Tab A.2)

   - The scan results appear as a table listing every discovered variable with its name, type, and origin (model input, output, or already exposed in the RL Experiment).
   - For each variable, check whether it should serve as:
     - **Observation** — values the agent can _see_ (e.g., queue lengths, utilization, time).
     - **Action** — values the agent can _control_ (e.g., processing times, resource counts).
     - **Configuration** — values set once at the start of each episode (e.g., arrival rates, random seeds).
   - A variable can be assigned to multiple roles if needed.

3. **Code Review** (Tab A.3)
   - Based on your selection, the application generates Java code snippets for each section of the AnyLogic RL Experiment: the data field definitions and the logic code for Configuration, Observation, and Action.
   - Open your AnyLogic model, navigate to the RL Experiment properties, and paste each snippet into the corresponding field.
   - **Re-export** the model from AnyLogic — this second export now contains the RL interface you just defined.
   - Back in Alpyne-Xtend, point Tab A.1 to the new `.zip` and run the scan again. The application will now recognize the exposed parameters and unlock the Training phase.

### Phase B: Training

1. **Parameter Configuration** (Tab B.1)

   - Select which exposed parameters to include in training.
   - Set bounds (min/max) for actions and observations.
   - Optionally set static or randomized initial values for configuration parameters.

2. **Reward Function** (Tab B.2)

   - Write a Python expression that defines the agent's objective.
   - Click variable names to insert them into the expression.
   - Example: `throughput - (waiting_time * 0.5)`

3. **Training Dashboard** (Tab B.3)
   - Configure hyperparameters (learning rate, network architecture, batch size, etc.).
   - Set the number of parallel environments, episodes, and time limits.
   - Click **Start Training** to launch the SAC agent.
   - Monitor progress via the built-in log or TensorBoard.

### Phase C: Testing

- Select a trained model (`.zip`) and run evaluation episodes.
- View per-episode rewards and average action values.

### Running Scripts Directly

The training and evaluation scripts can also be used independently of the GUI:

```bash
# Training (reads config.json)
cd Software/App/AlpyneXtend/Scripts
python train_agent.py

# Evaluation
python test_agent.py --model ./ModelsRL/model_final.zip --episodes 10

# Bayesian Optimization
python train_bayes_opt.py
python train_bayes_opt.py --dry-run  # Validate config without running

# Diagnostic scan
python diagnostic_scan.py --model-path /path/to/model.zip --java-path java
```

---

## How It Works

### Modified Alpyne Server

The standard Alpyne server (`alpyne-1.2.0.jar`) acts as a bridge between Python and the AnyLogic simulation engine via a local HTTP server. The modified version in this repository extends the server with an **endpoint scanner** that introspects the model's Java classes at startup and writes a `raw_scan_results.log` containing all discoverable parameters, their types, and default values.

The Java source for these modifications is in `Library-Dev/src/`. To rebuild the JAR after making changes:

```bash
cd Library-Dev
mvn package
# Copy the output JAR to the release location:
cp target/alpyne-1.2.0.jar ../Library-Release/alpyne/resources/
```

### Configuration Flow

```
AnyLogic Model (.zip)
        │
        ▼
   Model Scan ──► raw_scan_results.log ──► structured_scan_results.json
        │
        ▼
   GUI Selection (Obs / Act / Config)
        │
        ▼
   config.json  ◄── Reward Function, Hyperparameters, Bounds
        │
        ├──► train_agent.py    (SAC with Stable Baselines3)
        ├──► train_bayes_opt.py (Bayesian Optimization)
        └──► test_agent.py     (Evaluation)
```

---

## Known Limitations & Unfinished Work

### PyQt6 GUI (`AlpyneXtend_PyQt6.py`)

An alternative GUI implementation using PyQt6 was started but is **incomplete**. It covers the basic layout but lacks most of the functionality of the CustomTkinter version. It exists as a starting point for future migration.

### Bayesian Optimization (`train_bayes_opt.py`)

The Bayesian Optimization script is functional but has limitations:

- Only supports parameters defined as randomized expressions in `SIM_CONFIG` (e.g., `"np.random.choice(np.arange(1, 6, 1))"`).
- No TensorBoard integration (results are saved as JSON).
- The discrete parameter space handling (rounding) works but is not as sophisticated as dedicated discrete BO libraries.

### Array-Type Actions

The current training scripts (`train_agent.py`) do not support **array-type action spaces** — only scalar actions are implemented. AnyLogic models that require passing arrays as actions would need a custom `_to_action()` implementation.

### Platform Support

The application was developed and tested on **Windows**. The core scripts and Alpyne library are cross-platform, but the GUI contains some Windows-specific behavior (e.g., `taskkill` for TensorBoard cleanup, `winsound` for notifications). These degrade gracefully on other platforms.

### Model Scanning Limitations

- The scanner discovers variables accessible from the root agent. Deeply nested sub-model variables may not appear.
- Complex Java types (collections, custom classes) are reported with their full type string but cannot be directly used as RL parameters without manual mapping.

---

## Project Status

This project was developed in the scope of a university thesis and is **not actively maintained**. It is published as-is for reference and reuse. Bug reports and forks are welcome, but there are no plans for continued development.

---

## Acknowledgments

This project builds on top of [Alpyne](https://github.com/the-anylogic-company/Alpyne) by The AnyLogic Company. The modified server JAR is derived from the original Alpyne source (v1.2.0) under the MIT License.

---

## License

This project is released under the [MIT License](Library-Release/LICENSE).
