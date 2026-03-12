import sys
import json
import os
import subprocess
import shutil
import re
import time
import math
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QStackedWidget,
    QFrame,
    QTabWidget,
    QLineEdit,
    QFileDialog,
    QTableView,
    QHeaderView,
    QAbstractItemView,
    QMessageBox,
    QFormLayout,
    QComboBox,
    QCheckBox,
    QListWidget,
    QTextEdit,
    QSplitter,
    QGroupBox,
    QDoubleSpinBox,
    QSpinBox,
    QScrollArea,
    QSizePolicy,
    QPlainTextEdit,
    QInputDialog,
    QGridLayout,
)
import webbrowser
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, pyqtSignal, QThread, QSize, QTimer
from PyQt6.QtGui import QColor, QFont, QTextCursor, QSyntaxHighlighter, QTextCharFormat
import qdarktheme

# --- Constants ---
BASE_DIR = Path(__file__).parent.resolve()
LOGS_DIR = BASE_DIR / "AlpyneXtend" / "Scripts" / "Logs"
CONFILOGS_DIR = BASE_DIR / "AlpyneXtend" / "logs"
CONFIG_DIR = BASE_DIR / "AlpyneXtend" / "configs"
SCAN_RESULTS_PATH = LOGS_DIR / "structured_scan_results.json"
CONFIG_PATH = BASE_DIR / "AlpyneXtend" / "config.json"
APP_SETTINGS_PATH = BASE_DIR / "AlpyneXtend" / "Xtend_settings.json"
TB_LOGS_DIR = BASE_DIR / "AlpyneXtend" / "tensorboard_logs"

# Ensure dirs exist
LOGS_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
TB_LOGS_DIR.mkdir(parents=True, exist_ok=True)

# --- TOOLTIPS DATA ---
TOOLTIPS = {
    "MODEL_PATH": "The location of your exported AnyLogic model (.zip).",
    "JAVA_EXE": "Path to java.exe. Required to run the Alpyne server.",
    "PYTHON_VENV": "Optional: Path to python.exe in your virtual environment.",
    "SCAN_SCRIPT": "Script used to analyze the AnyLogic model.",
    "LOG_LEVEL_PY": "Python log verbosity.",
    "MAX_AWAIT": "Time (seconds) to wait for AnyLogic server startup.",
    "NUM_ENVS": "Number of parallel simulation instances.",
    "TOTAL_EPISODES": "Total training episodes.",
    "STEPS_PER_EP": "Max steps per episode.",
    "MAX_DURATION": "Max wall-clock training time (minutes).",
    "POLICY": "Network architecture (MlpPolicy, CnnPolicy).",
    "SEED": "Random seed for reproducibility.",
    "DEVICE": "Hardware device (cpu/cuda).",
    "LEARNING_RATE": "Step size for optimizer.",
    "GAMMA": "Discount factor.",
    "BATCH_SIZE": "Minibatch size for gradient updates.",
    "TAU": "Soft update coefficient.",
    "LEARNING_STARTS": "Steps before training starts.",
    "NET_ARCH": "Network layers e.g. [256, 256].",
    "USE_TB": "Enable TensorBoard logging.",
    "NORM_OBS": "Normalize observations (Mean=0, Std=1).",
    "NORM_REW": "Normalize rewards.",
}


# --- Config Manager ---
class ConfigManager:
    DEFAULT_CONFIG = {
        "MODEL_PATH": "",
        "JAVA_EXE_PATH": "java",
        "PYTHON_VENV": "",
        "ALPYNE_SIM_SETTINGS": {"py_log_level": "ERROR", "java_log_level": "ERROR", "max_server_await_time": 10},
        "TRAINING": {
            "n_envs": 1,
            "total_episodes": 1000,
            "steps_per_episode": 100,
            "max_duration": 0,
            "save_models": False,
            "reset_num_timesteps": False,
            "use_tensorboard": True,
            "auto_launch_tb": True,
            "play_sound": True,
            "norm_obs": True,
            "norm_reward": True,
            "extended_logging": False,
            "extended_logging_freq": "10",
        },
        "RL_AGENT_SETTINGS": {"policy": "MlpPolicy", "seed": 42, "device": "cpu"},
        "SAC_PARAMS": {
            "learning_rate": 0.0003,
            "gamma": 0.99,
            "batch_size": 256,
            "tau": 0.005,
            "learning_starts": 100,
            "policy_net_arch": [256, 256],
        },
        "SIM_CONFIG": {},
        "ACTIONS": {},
        "OBSERVATIONS": {},
    }

    @staticmethod
    def load():
        try:
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
                if data:
                    return data
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        # Create default if missing
        ConfigManager.save(ConfigManager.DEFAULT_CONFIG)
        return ConfigManager.DEFAULT_CONFIG.copy()

    @staticmethod
    def save(data):
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(data, f, indent=4)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False

    @staticmethod
    def load_scan_results():
        try:
            with open(SCAN_RESULTS_PATH, "r") as f:
                data = json.load(f)
            return data
        except (FileNotFoundError, json.JSONDecodeError):
            return {"variables": []}

    @staticmethod
    def save_scan_results(data):
        try:
            with open(SCAN_RESULTS_PATH, "w") as f:
                json.dump(data, f, indent=4)
            return True
        except Exception as e:
            print(f"Error saving scan results: {e}")
            return False
            # --- SMART EXPANSION LOGIC ---
            SMART_MAP = {
                "ResourcePool": [
                    {"suffix": ".utilization()", "type": "double", "name_suf": ".utilization", "read_only": True},
                    {"suffix": ".size()", "type": "int", "name_suf": ".size", "read_only": True},
                    {"suffix": ".idle()", "type": "int", "name_suf": ".idle", "read_only": True},
                    {"suffix": ".busy()", "type": "int", "name_suf": ".busy", "read_only": True},
                ],
                "Queue": [
                    {"suffix": ".size()", "type": "int", "name_suf": ".size", "read_only": True},
                    {"suffix": ".capacity", "type": "int", "name_suf": ".capacity", "read_only": False},
                    {"suffix": ".statsSize.mean()", "type": "double", "name_suf": ".meanSize", "read_only": True},
                ],
                "Conveyor": [{"suffix": ".currentSpeed", "type": "double", "name_suf": ".speed", "read_only": True}],
                "Seize": [{"suffix": ".size()", "type": "int", "name_suf": ".size", "read_only": True}],
                "Service": [
                    {"suffix": ".utilization()", "type": "double", "name_suf": ".utilization", "read_only": True}
                ],
            }

            expanded_vars = []
            # First pass: Collect all existing names to prevent duplicates
            existing_names = set(v["name"] for v in data.get("variables", []))

            # Universal Translator & Expansion
            for v in data.get("variables", []):
                # Map Categories
                raw_cat = v.get("category", "").lower()
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

                # Sync Flags
                used = v.get("currently_used_as", [])
                if "configuration" in used:
                    v["use_cfg"] = True
                if "action" in used:
                    v["use_act"] = True
                if "observation" in used:
                    v["use_obs"] = True

                expanded_vars.append(v)

                # Check for Smart Expansion
                raw_type = v.get("data_type", "")
                for key, rules in SMART_MAP.items():
                    if key in raw_type:
                        for rule in rules:
                            child_name = f"{v['name']}{rule['name_suf']}"
                            if child_name not in existing_names:
                                child = {
                                    "name": child_name,
                                    "category": "output",
                                    "data_type": rule["type"],
                                    "path": f"{v.get('path', '')}{rule['suffix']}",
                                    "default_value": "",
                                    "is_exposed": False,
                                    "suggested_as": ["observation"],
                                    "is_virtual": True,
                                    "read_only": rule.get("read_only", False),
                                    "parent_obj": v["name"],
                                }
                                expanded_vars.append(child)
                                existing_names.add(child_name)
                        break

            data["variables"] = expanded_vars
            return data
        except (FileNotFoundError, json.JSONDecodeError):
            return {"variables": []}


# --- Log Syntax Highlighter ---
class LogHighlighter(QSyntaxHighlighter):
    def highlightBlock(self, text):
        fmt = QTextCharFormat()
        if "ERROR" in text.upper() or "EXCEPTION" in text.upper() or "FAIL" in text.upper():
            fmt.setForeground(QColor("#FF5555"))
            self.setFormat(0, len(text), fmt)
        elif "WARNING" in text.upper():
            fmt.setForeground(QColor("#FFB86C"))
            self.setFormat(0, len(text), fmt)
        elif "SUCCESS" in text.upper() or "COMPLETED" in text.upper():
            fmt.setForeground(QColor("#50FA7B"))
            self.setFormat(0, len(text), fmt)
        elif "EPISODE" in text.upper():
            fmt.setForeground(QColor("#8BE9FD"))
            self.setFormat(0, len(text), fmt)

            self.setFormat(0, len(text), fmt)


class JavaHighlighter(QSyntaxHighlighter):
    def highlightBlock(self, text):
        # Keywords
        keywords = ["double", "int", "boolean", "void", "return", "if", "else", "true", "false", "root", "this"]
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#569CD6"))  # Blue
        fmt.setFontWeight(QFont.Weight.Bold)
        for w in keywords:
            # Simple whole word match
            import re

            for m in re.finditer(r"\b" + w + r"\b", text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)

        # Numbers
        fmt_num = QTextCharFormat()
        fmt_num.setForeground(QColor("#B5CEA8"))  # Light Green
        for m in re.finditer(r"\b\d+\.?\d*\b", text):
            self.setFormat(m.start(), m.end() - m.start(), fmt_num)

        # Comments
        if "//" in text:
            idx = text.index("//")
            fmt_com = QTextCharFormat()
            fmt_com.setForeground(QColor("#6A9955"))  # Green
            self.setFormat(idx, len(text) - idx, fmt_com)


class AppSettings:
    @staticmethod
    def load():
        try:
            with open(APP_SETTINGS_PATH, "r") as f:
                return json.load(f)
        except:
            return {}

    @staticmethod
    def save(data):
        try:
            with open(APP_SETTINGS_PATH, "w") as f:
                json.dump(data, f, indent=4)
        except:
            pass

    @staticmethod
    def get(key, default=None):
        return AppSettings.load().get(key, default)

    @staticmethod
    def set(key, value):
        data = AppSettings.load()
        data[key] = value
        AppSettings.save(data)


# --- Worker Threads ---
class ScriptRunnerThread(QThread):
    log_signal = pyqtSignal(str)
    metric_signal = pyqtSignal(str, str, str)
    finished_signal = pyqtSignal()

    def __init__(self, cmd, cwd, n_envs=1):
        super().__init__()
        self.cmd = cmd
        self.cwd = cwd
        self.n_envs = str(n_envs)
        self.process = None
        self.start_time = None

    def run(self):
        self.start_time = time.time()
        try:
            self.process = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=self.cwd,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            for line in self.process.stdout:
                line = line.strip()
                self.log_signal.emit(line)

                if "--- Episode" in line:
                    try:
                        parts = line.split("Episode")[1].split("---")[0].strip().split("/")
                        if len(parts) == 2:
                            ep_str = f"{parts[0]} / {parts[1]}"
                            elapsed = int(time.time() - self.start_time)
                            h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
                            time_str = f"{h:02d}:{m:02d}:{s:02d}"
                            self.metric_signal.emit(time_str, ep_str, self.n_envs)
                    except:
                        pass

            self.process.wait()
        except Exception as e:
            self.log_signal.emit(f"Error: {str(e)}")
        finally:
            self.finished_signal.emit()

    def stop(self):
        if self.process:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.process.pid)], capture_output=True)


# --- Custom Widgets ---
class InfoButton(QPushButton):
    def __init__(self, key):
        super().__init__("?")
        self.setFixedWidth(20)
        self.setFixedHeight(20)
        self.setStyleSheet(
            "QPushButton { border-radius: 10px; background-color: #555; color: white; font-weight: bold; } QPushButton:hover { background-color: #777; }"
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.key = key
        self.clicked.connect(self.show_info)

    def show_info(self):
        msg = TOOLTIPS.get(self.key, "No info available.")
        QMessageBox.information(self, "Info", msg)


class FileSelector(QWidget):
    def __init__(self, config_key, parent_config, is_folder=False, filters="All Files (*.*)"):
        super().__init__()
        self.key = config_key
        self.config = parent_config
        self.is_folder = is_folder
        self.filters = filters

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.line_edit = QLineEdit()
        self.line_edit.setText(str(self.config.get(self.key, "")))
        self.line_edit.textChanged.connect(self._update)

        btn = QPushButton("...")
        btn.setFixedWidth(30)
        btn.clicked.connect(self._browse)

        layout.addWidget(self.line_edit)
        layout.addWidget(btn)

    def _browse(self):
        if self.is_folder:
            path = QFileDialog.getExistingDirectory(self, "Select Directory")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Select File", filter=self.filters)
        if path:
            self.line_edit.setText(path)

    def _update(self, text):
        self.config[self.key] = text


# --- Models ---
class VariableTableModel(QAbstractTableModel):
    dataRefreshed = pyqtSignal()  # Custom signal

    def __init__(self, variables_data=None):
        super().__init__()
        self._data = variables_data or []
        self._headers = ["Cat", "Name", "Type", "Obs", "Act", "Cfg"]

    def update_data(self, new_data):
        self.beginResetModel()
        self._data = new_data
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self._headers)

    def data(self, index, role):
        if not index.isValid():
            return None
        row = self._data[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return row.get("category", "").upper()
            if col == 1:
                return f"{'    ↳ ' if row.get('is_virtual') else ''}{row.get('name', '')}"
            if col == 2:
                return row.get("data_type", "").split(".")[-1] if row.get("is_parent") else row.get("data_type", "")
            return None

        if role == Qt.ItemDataRole.CheckStateRole and col in [3, 4, 5]:
            keys = {3: "use_obs", 4: "use_act", 5: "use_cfg"}
            # Disable check for read-only items (logic)
            if col in [4, 5] and row.get("read_only", False):
                return None  # No checkbox for read-only actions/config
            return Qt.CheckState.Checked if row.get(keys[col], False) else Qt.CheckState.Unchecked

        if role == Qt.ItemDataRole.ForegroundRole:
            cat = row.get("category", "").lower()
            if col == 0:
                return (
                    QColor("#3B8ED0")
                    if cat == "input"
                    else (QColor("#E07A5F") if cat == "output" else QColor("#2cc985"))
                )
            if row.get("is_parent"):
                return QColor("gray")

        return None

    def setData(self, index, value, role):
        if role == Qt.ItemDataRole.CheckStateRole:
            row = self._data[index.row()]
            col = index.column()
            keys = {3: "use_obs", 4: "use_act", 5: "use_cfg"}
            if col in keys:
                # Handle both integer (0/2) and enum inputs
                state = value
                if isinstance(value, int):
                    state = Qt.CheckState(value)

                new_bool = state == Qt.CheckState.Checked
                row[keys[col]] = new_bool
                self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])

                # Auto-Save on Toggle
                try:
                    data_wrap = {"variables": self._data}
                    ConfigManager.save_scan_results(data_wrap)
                    self.dataRefreshed.emit()  # Notify listeners
                except:
                    # Fallback if method missing or static access issue, though save_scan_results isn't in ConfigManager yet (only load_scan_results)
                    with open(SCAN_RESULTS_PATH, "w") as f:
                        json.dump(data_wrap, f, indent=4)
                return True
        return False

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self._headers[section]
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        row = self._data[index.row()]
        col = index.column()

        if col in [3, 4, 5]:
            if col in [4, 5] and row.get("read_only", False):
                return flags & ~Qt.ItemFlag.ItemIsEnabled
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        return flags

    def sort(self, column, order):
        self.layoutAboutToBeChanged.emit()
        try:
            # Custom sort for Category (Input -> Output -> Exposed)
            if column == 0:
                rank = {"input": 0, "output": 1, "exposed": 2}
                self._data.sort(key=lambda r: (rank.get(r.get("category", "").lower(), 99), r.get("name", "")))
                if order == Qt.SortOrder.DescendingOrder:
                    self._data.reverse()
            else:
                # Default sort for other columns
                key_name = ["category", "name", "data_type", "use_obs", "use_act", "use_cfg"][column]
                self._data.sort(key=lambda r: str(r.get(key_name, "")).lower())
                if order == Qt.SortOrder.DescendingOrder:
                    self._data.reverse()
        finally:
            self.layoutChanged.emit()


# --- Guide Tab ---
class GuideTab(QWidget):
    def __init__(self, content):
        super().__init__()
        layout = QVBoxLayout(self)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setHtml(content)
        text.setStyleSheet("background-color: #2b2b2b; color: #dcdcdc; padding: 10px; font-size: 14px;")
        layout.addWidget(text)


# ==========================================
#               TAB A: SETUP
# ==========================================


class ProjectSetupTab(QWidget):
    def __init__(self):
        super().__init__()
        self.config = ConfigManager.load()
        self.init_ui()

    def init_ui(self):
        main_layout = QHBoxLayout(self)

        # --- LEFT: SETTINGS FORM ---
        left_panel = QFrame()
        left_layout = QVBoxLayout(left_panel)
        form = QFormLayout()
        form.setSpacing(10)

        lbl_title = QLabel("Environment Configuration")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        left_layout.addWidget(lbl_title)

        def add_row(label, widget, key):
            h = QHBoxLayout()
            h.addWidget(widget)
            h.addWidget(InfoButton(key))
            form.addRow(label, h)

        self.model_path = FileSelector("MODEL_PATH", self.config, filters="Zip (*.zip)")
        add_row("AnyLogic Model (.zip):", self.model_path, "MODEL_PATH")

        self.java_path = FileSelector("JAVA_EXE_PATH", self.config, filters="Exe (*.exe)")
        add_row("Java Executable:", self.java_path, "JAVA_EXE")

        self.python_venv = FileSelector("PYTHON_VENV", self.config, filters="Exe (*.exe)")
        add_row("Python Venv:", self.python_venv, "PYTHON_VENV")

        self.scan_script = FileSelector("SCAN_SCRIPT", self.config, filters="Python (*.py)")
        if not self.config.get("SCAN_SCRIPT"):
            self.config["SCAN_SCRIPT"] = str(BASE_DIR / "AlpyneXtend" / "Scripts" / "diagnostic_scan.py")
            self.scan_script.line_edit.setText(self.config["SCAN_SCRIPT"])
        add_row("Scan Script:", self.scan_script, "SCAN_SCRIPT")

        lbl_sim = QLabel("Alpyne Settings")
        lbl_sim.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 10px;")
        form.addRow(lbl_sim)

        self.alpyne_cfg = self.config.get("ALPYNE_SIM_SETTINGS", {})

        self.py_log = QComboBox()
        self.py_log.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self.py_log.setCurrentText(self.alpyne_cfg.get("py_log_level", "ERROR"))
        self.py_log.currentTextChanged.connect(lambda t: self._update_alpyne("py_log_level", t))
        add_row("Python Log Level:", self.py_log, "LOG_LEVEL_PY")

        self.java_log = QComboBox()
        self.java_log.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "OFF"])
        self.java_log.setCurrentText(self.alpyne_cfg.get("java_log_level", "ERROR"))
        self.java_log.currentTextChanged.connect(lambda t: self._update_alpyne("java_log_level", t))
        add_row("Java Log Level:", self.java_log, "LOG_LEVEL_JAVA")

        self.max_await = QSpinBox()
        self.max_await.setRange(10, 300)
        self.max_await.setValue(int(self.alpyne_cfg.get("max_server_await_time", 60)))
        self.max_await.valueChanged.connect(lambda v: self._update_alpyne("max_server_await_time", v))
        add_row("Max Server Await (s):", self.max_await, "MAX_AWAIT")

        left_layout.addLayout(form)

        btn_box = QHBoxLayout()
        save_btn = QPushButton("SAVE SETTINGS")
        save_btn.setStyleSheet("background-color: #2cc985; color: white; font-weight: bold; padding: 8px;")
        save_btn.clicked.connect(self._save)
        btn_box.addWidget(save_btn)

        scan_btn = QPushButton("RUN MODEL SCAN")
        scan_btn.setStyleSheet("background-color: #1f6aa5; color: white; font-weight: bold; padding: 8px;")
        scan_btn.clicked.connect(self._run_scan)
        btn_box.addWidget(scan_btn)

        left_layout.addLayout(btn_box)
        left_layout.addStretch()

        main_layout.addWidget(left_panel, stretch=3)

        # --- RIGHT: STATUS CONSOLE ---
        right_panel = QFrame()
        right_panel.setStyleSheet("background-color: #1f1f1f; border-radius: 5px;")
        right_layout = QVBoxLayout(right_panel)

        lbl_status_title = QLabel("Scan Status")
        lbl_status_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #dcdcdc;")
        right_layout.addWidget(lbl_status_title)

        self.lbl_status = QLabel("No Scan Run")
        self.lbl_status.setStyleSheet("font-size: 20px; font-weight: bold; color: gray; margin: 10px 0;")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(self.lbl_status)

        self.console_log = QTextEdit()
        self.console_log.setReadOnly(True)
        self.console_log.setStyleSheet(
            "background-color: #111; color: #dcdcdc; font-family: Consolas; font-size: 10px;"
        )
        self.highlighter = LogHighlighter(self.console_log.document())
        right_layout.addWidget(self.console_log)

        main_layout.addWidget(right_panel, stretch=2)

    def _update_alpyne(self, key, value):
        if "ALPYNE_SIM_SETTINGS" not in self.config:
            self.config["ALPYNE_SIM_SETTINGS"] = {}
        self.config["ALPYNE_SIM_SETTINGS"][key] = value

    def _save(self):
        ConfigManager.save(self.config)
        QMessageBox.information(self, "Saved", "Settings saved to config.json")

    def _run_scan(self):
        self.console_log.clear()
        self.console_log.append("Starting Scan...")
        self.lbl_status.setText("Scanning...")
        self.lbl_status.setStyleSheet("font-size: 20px; font-weight: bold; color: orange;")

        script = self.config.get("SCAN_SCRIPT", str(BASE_DIR / "AlpyneXtend" / "Scripts" / "diagnostic_scan.py"))
        model = self.config.get("MODEL_PATH", "")
        java = self.config.get("JAVA_EXE_PATH", "java")
        if not shutil.which(java) and not os.path.exists(java):
            if shutil.which("java"):
                java = "java"
            else:
                self.console_log.append("CRITICAL: Java not found. Install Java or set path.")
                self.lbl_status.setText("Error: Java Missing")
                self.lbl_status.setStyleSheet("color: red;")
                return
        venv = self.config.get("PYTHON_VENV", sys.executable)
        if not venv:
            venv = sys.executable

        cmd = [venv, str(script), "--model-path", model, "--java-path", java, "--log-dir", str(LOGS_DIR)]

        self.scan_thread = ScriptRunnerThread(cmd, str(BASE_DIR))
        self.scan_thread.log_signal.connect(self.console_log.append)
        self.scan_thread.finished_signal.connect(self._on_scan_finished)
        self.scan_thread.start()

    def _on_scan_finished(self):
        self.lbl_status.setText("Scan Complete")
        self.lbl_status.setStyleSheet("font-size: 20px; font-weight: bold; color: #50fa7b;")


class ExperimentConfigTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        h = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter...")
        self.search.textChanged.connect(self._filter)
        h.addWidget(QLabel("Search:"))
        h.addWidget(self.search)
        refresh = QPushButton("Reload Scan Data")
        refresh.clicked.connect(self.load_data)
        h.addWidget(refresh)
        layout.addLayout(h)

        self.table = QTableView()
        self.model = VariableTableModel()
        self.proxy = QSortFilterProxyModel()
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setFilterKeyColumn(1)
        self.table.setModel(self.proxy)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSortingEnabled(True)
        # Fix Alternating colors visibility
        self.table.setStyleSheet(
            "QTableView { background-color: #1e1e1e; alternate-background-color: #252525; selection-background-color: #1f6aa5; selection-color: white; }"
        )
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)
        self.load_data()

    def _filter(self, text):
        self.proxy.setFilterFixedString(text)

    def load_data(self):
        data = ConfigManager.load_scan_results()
        self.model.update_data(data.get("variables", []))


class CodeReviewTab(QWidget):
    def __init__(self):
        super().__init__()
        self.config = ConfigManager.load()
        layout = QVBoxLayout(self)

        h = QHBoxLayout()
        self.pre_obs = QLineEdit("XO_")
        h.addWidget(QLabel("Obs Prefix:"))
        h.addWidget(self.pre_obs)
        self.pre_act = QLineEdit("XA_")
        h.addWidget(QLabel("Act Prefix:"))
        h.addWidget(self.pre_act)
        self.pre_cfg = QLineEdit("XC_")
        h.addWidget(QLabel("Cfg Prefix:"))
        h.addWidget(self.pre_cfg)
        gen_btn = QPushButton("Generate Code")
        gen_btn.clicked.connect(self._generate)
        h.addWidget(gen_btn)
        layout.addLayout(h)

        self.codegen_warning_label = QLabel("")
        self.codegen_warning_label.setStyleSheet("color: orange; font-weight: bold;")
        layout.addWidget(self.codegen_warning_label)

        vbox = QVBoxLayout()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        vbox = QVBoxLayout(content)

        # Split View Grid

        def mk_block(title):
            g = QGroupBox(title)
            l = QVBoxLayout(g)
            l.setContentsMargins(0, 0, 0, 0)
            t = QPlainTextEdit()
            t.setFont(QFont("Consolas", 10))
            t.setFixedHeight(120)
            l.addWidget(t)
            vbox.addWidget(g)
            return g

        if not self.config.get("SIM_CONFIG") and not self.config.get("ACTIONS"):
            self.codegen_warning_label.setText(
                "⚠ Warning: No actions or simulation config defined. Code may be incomplete."
            )
            self.codegen_warning_label.show()
        else:
            self.codegen_warning_label.hide()

        # 1. Observations
        obs_grp = QGroupBox("Observations")
        obs_l = QHBoxLayout(obs_grp)
        self.text_obs_data = QPlainTextEdit()
        self.text_obs_data.setFont(QFont("Consolas", 10))
        self.text_obs_code = QPlainTextEdit()
        self.text_obs_code.setFont(QFont("Consolas", 10))
        self.hl_obs_code = JavaHighlighter(self.text_obs_code.document())  # Highlighting
        obs_l.addWidget(QLabel("Data Fields"))
        obs_l.addWidget(self.text_obs_data)
        obs_l.addWidget(QLabel("Code Logic"))
        obs_l.addWidget(self.text_obs_code)
        vbox.addWidget(obs_grp)

        # 2. Actions
        act_grp = QGroupBox("Actions")
        act_l = QHBoxLayout(act_grp)
        self.text_act_data = QPlainTextEdit()
        self.text_act_data.setFont(QFont("Consolas", 10))
        self.text_act_code = QPlainTextEdit()
        self.text_act_code.setFont(QFont("Consolas", 10))
        self.hl_act_code = JavaHighlighter(self.text_act_code.document())  # Highlighting
        act_l.addWidget(QLabel("Data Fields"))
        act_l.addWidget(self.text_act_data)
        act_l.addWidget(QLabel("Code Logic"))
        act_l.addWidget(self.text_act_code)
        vbox.addWidget(act_grp)

        # 3. Config
        cfg_grp = QGroupBox("Configuration")
        cfg_l = QHBoxLayout(cfg_grp)
        self.text_cfg_data = QPlainTextEdit()
        self.text_cfg_data.setFont(QFont("Consolas", 10))
        self.text_cfg_code = QPlainTextEdit()
        self.text_cfg_code.setFont(QFont("Consolas", 10))
        self.hl_cfg_code = JavaHighlighter(self.text_cfg_code.document())  # Highlighting
        cfg_l.addWidget(QLabel("Data Fields"))
        cfg_l.addWidget(self.text_cfg_data)
        cfg_l.addWidget(QLabel("Code Logic"))
        cfg_l.addWidget(self.text_cfg_code)
        vbox.addWidget(cfg_grp)

        # 4. Extras
        self.text_stop = mk_block("Stop Condition")
        self.text_post = mk_block("Post-Action")

        scroll.setWidget(content)
        layout.addWidget(scroll)

    def _generate(self):
        data = ConfigManager.load_scan_results()
        vars = data.get("variables", [])
        p_obs, p_act, p_cfg = self.pre_obs.text(), self.pre_act.text(), self.pre_cfg.text()

        def get_name(name, prefix):
            clean = name.replace(".", "_")
            if clean.startswith(prefix):
                return clean
            return f"{prefix}{clean}"

        def fill_widgets(category, prefix, t_data, t_code, is_obs=False):
            t_data.clear()
            t_code.clear()

            flag = "use_obs" if category == "obs" else ("use_act" if category == "act" else "use_cfg")
            selected = [v for v in vars if v.get(flag)]

            str_data = ""
            str_code = ""

            for v in selected:
                exposed = get_name(v["name"], prefix)
                java_path = v.get("path", f"root.{v['name']}")
                dtype = v.get("data_type", "double")
                j_type = "double" if dtype == "boolean" else dtype
                if j_type == "int":
                    j_type = "int"
                elif j_type == "boolean":
                    j_type = "boolean"
                if is_obs and dtype == "boolean":
                    j_type = "double"

                str_data += f"{exposed}\t{j_type}\n"

                if is_obs:
                    val = f"({java_path} ? 1.0 : 0.0)" if dtype == "boolean" else java_path
                    str_code += f"{exposed} = {val};\n"
                else:
                    target = java_path if not v.get("is_virtual") else f"root.{v['name']}"
                    if "." in target:
                        parent, var = target.rsplit(".", 1)
                        str_code += f"{parent}.set_{var}({exposed});\n"
                    else:
                        str_code += f"set_{target}({exposed});\n"
            t_data.setPlainText(str_data)
            t_code.setPlainText(str_code)

        fill_widgets("obs", p_obs, self.text_obs_data, self.text_obs_code, True)
        fill_widgets("act", p_act, self.text_act_data, self.text_act_code, False)
        fill_widgets("cfg", p_cfg, self.text_cfg_data, self.text_cfg_code, False)

        self.text_stop.findChild(QPlainTextEdit).setPlainText("// --- STOP CONDITION ---\nroot.exceededCapacity")
        self.text_post.findChild(QPlainTextEdit).setPlainText("// --- POST-ACTION CODE ---\nroot.resetCosts();")


# ==========================================
#               TAB B: TRAINING
# ==========================================


class ParamConfigTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        # --- Named Presets ---
        h_presets = QHBoxLayout()
        h_presets.addWidget(QLabel("Saved Configs:"))
        self.preset_combo = QComboBox()
        self.preset_combo.currentIndexChanged.connect(self._load_preset)
        h_presets.addWidget(self.preset_combo)
        self.preset_name = QLineEdit()
        self.preset_name.setPlaceholderText("Config Name")
        h_presets.addWidget(self.preset_name)
        save_preset = QPushButton("Save Preset")
        save_preset.clicked.connect(self._save_preset)
        h_presets.addWidget(save_preset)

        reset_btn = QPushButton("Reset Config")
        reset_btn.setStyleSheet("background-color: #c0392b; color: white;")
        reset_btn.clicked.connect(self._reset_configuration)
        h_presets.addWidget(reset_btn)

        layout.addLayout(h_presets)

        split = QSplitter()

        self.lists_widget = QWidget()
        l_layout = QHBoxLayout(self.lists_widget)
        self.lst_cfg = self._mk_list("Configuration")
        l_layout.addWidget(self.lst_cfg)
        self.lst_act = self._mk_list("Actions")
        l_layout.addWidget(self.lst_act)
        self.lst_obs = self._mk_list("Observations")
        l_layout.addWidget(self.lst_obs)
        split.addWidget(self.lists_widget)

        self.prop_widget = QGroupBox("Properties")
        self.prop_layout = QFormLayout(self.prop_widget)
        split.addWidget(self.prop_widget)
        layout.addWidget(split)

        apply_btn = QPushButton("APPLY CONFIGURATION")
        apply_btn.setStyleSheet("background-color: #2cc985; color: white; font-weight: bold; height: 40px;")
        apply_btn.clicked.connect(self._apply_config)
        layout.addWidget(apply_btn)
        self.current_var = None
        self.overrides = {}
        self._refresh_presets()
        self._sync_overrides_from_config()

    def _mk_list(self, title):
        g = QGroupBox(title)
        v = QVBoxLayout(g)
        l = QListWidget()
        l.itemClicked.connect(lambda i: self._load_prop(i, title))
        v.addWidget(l)
        return g

    def load_from_scan(self):
        data = ConfigManager.load_scan_results()
        cfg_overrides = ConfigManager.load()  # Load full config to check overrides status

        sim_conf = cfg_overrides.get("SIM_CONFIG", {})
        actions = cfg_overrides.get("ACTIONS", {})

        for lst in [self.lst_cfg, self.lst_act, self.lst_obs]:
            lst.findChild(QListWidget).clear()

        for v in data.get("variables", []):
            name = v["name"]

            # Helper to add item with status icon
            def add_item(target_list, is_active):
                icon = "✓ " if is_active else "○ "  # Simple text icon
                item = target_list.findChild(QListWidget).addItem(f"{icon}{name}")
                # Note: We store original name in UserRole or just parse it back?
                # Simpler: Just render text, but handle click by stripping prefix

            # Using widget items or just text? Text is easier.
            # But click handler `_load_prop` needs exact name.
            # Let's use `QListWidgetItem` with stored data.

            if v.get("use_cfg"):
                is_set = name in sim_conf
                self._add_list_item(self.lst_cfg, name, is_set)

            if v.get("use_act"):
                is_set = name in actions
                self._add_list_item(self.lst_act, name, is_set)

            if v.get("use_obs"):
                self._add_list_item(self.lst_obs, name, False)  # Obs don't have overrides usually

    def _add_list_item(self, group_box, name, is_active):
        from PyQt6.QtWidgets import QListWidgetItem

        lst = group_box.findChild(QListWidget)
        icon = "✓ " if is_active else "○ "
        item = QListWidgetItem(f"{icon}{name}")
        item.setData(Qt.ItemDataRole.UserRole, name)  # Store raw name
        lst.addItem(item)

    def _load_prop(self, item, category):
        while self.prop_layout.count():
            child = self.prop_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        name = item.data(Qt.ItemDataRole.UserRole)  # Retrieve raw name
        if not name:
            name = item.text()  # Fallback

        self.current_var = name
        self.prop_widget.setTitle(f"Properties: {name}")
        if name not in self.overrides:
            self.overrides[name] = {}

        if category == "Actions":
            is_int = self.overrides[name].get("type") == "int"
            chk_int = QCheckBox("Discrete / Integer")
            chk_int.setChecked(is_int)
            chk_int.toggled.connect(lambda b: self._set_ov(name, "type", "int" if b else "double"))
            self.prop_layout.addRow("", chk_int)

            min_spin = QDoubleSpinBox()
            min_spin.setRange(-1e9, 1e9)
            min_spin.setValue(float(self.overrides[name].get("low", 0)))
            max_spin = QDoubleSpinBox()
            max_spin.setRange(-1e9, 1e9)
            max_spin.setValue(float(self.overrides[name].get("high", 1)))
            min_spin.valueChanged.connect(lambda v: self._set_ov(name, "low", v))
            max_spin.valueChanged.connect(lambda v: self._set_ov(name, "high", v))
            self.prop_layout.addRow("Min Value:", min_spin)
            self.prop_layout.addRow("Max Value:", max_spin)

        elif category == "Configuration":
            mode_combo = QComboBox()
            mode_combo.addItems(["Fixed Value", "Random Range (Step)", "Random Choice"])
            val = self.overrides[name].get("value", "0.0")
            current_mode = "Fixed Value"
            if "arange" in str(val):
                current_mode = "Random Range (Step)"
            elif "choice" in str(val):
                current_mode = "Random Choice"
            mode_combo.setCurrentText(current_mode)

            container = QWidget()
            cont_layout = QFormLayout(container)

            def update_ui(mode):
                while cont_layout.count():
                    child = cont_layout.takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
                if mode == "Fixed Value":
                    le = QLineEdit(str(val) if "np." not in str(val) else "0.0")
                    le.textChanged.connect(lambda t: self._set_ov(name, "value", t))
                    cont_layout.addRow("Value:", le)
                elif mode == "Random Range (Step)":
                    v_min, v_max, v_step = "0.0", "1.0", "0.1"
                    try:
                        if "arange" in str(val):
                            parts = str(val).split("arange(")[1].split(")")[0].split(",")
                            if len(parts) >= 3:
                                v_min, v_max, v_step = parts[0].strip(), parts[1].strip(), parts[2].strip()
                    except:
                        pass
                    le_min = QLineEdit(v_min)
                    le_max = QLineEdit(v_max)
                    le_step = QLineEdit(v_step)
                    cont_layout.addRow("Min:", le_min)
                    cont_layout.addRow("Max:", le_max)
                    cont_layout.addRow("Step:", le_step)

                    def save_range():
                        expr = f"np.random.choice(np.arange({le_min.text()}, {le_max.text()}, {le_step.text()}))"
                        self._set_ov(name, "value", expr)

                    for w in [le_min, le_max, le_step]:
                        w.textChanged.connect(save_range)
                elif mode == "Random Choice":
                    choice_str = "1, 2, 3"
                    try:
                        if "choice([" in str(val):
                            choice_str = str(val).split("[")[1].split("]")[0]
                    except:
                        pass
                    le_choices = QLineEdit(choice_str)
                    cont_layout.addRow("Values (comma sep):", le_choices)
                    le_choices.textChanged.connect(lambda t: self._set_ov(name, "value", f"np.random.choice([{t}])"))

            mode_combo.currentTextChanged.connect(update_ui)
            update_ui(current_mode)
            self.prop_layout.addRow("Mode:", mode_combo)
            self.prop_layout.addRow(container)
        elif category == "Observations":
            self.prop_layout.addWidget(QLabel("Observation (Read-Only)"))
            self.prop_layout.addWidget(QLabel("Range: (-∞ to +∞)"))
            self.prop_layout.addWidget(QLabel("<i>Note: Values are normalized during training.</i>"))

        self.prop_layout.addStretch()

    def _set_ov(self, name, key, val):
        if name not in self.overrides:
            self.overrides[name] = {}
        self.overrides[name][key] = val

    def _apply_config(self):
        cfg = ConfigManager.load()
        cfg["rl_experiment_current_state"] = {
            "configuration": [
                self.lst_cfg.findChild(QListWidget).item(i).text()
                for i in range(self.lst_cfg.findChild(QListWidget).count())
            ],
            "actions": [
                self.lst_act.findChild(QListWidget).item(i).text()
                for i in range(self.lst_act.findChild(QListWidget).count())
            ],
            "observations": [
                self.lst_obs.findChild(QListWidget).item(i).text()
                for i in range(self.lst_obs.findChild(QListWidget).count())
            ],
        }
        for name, ov in self.overrides.items():
            if "low" in ov and "ACTIONS" in cfg:
                if name not in cfg["ACTIONS"]:
                    cfg["ACTIONS"][name] = {}
                cfg["ACTIONS"][name]["low"] = ov["low"]
                cfg["ACTIONS"][name]["high"] = ov["high"]
            if "value" in ov:
                if "SIM_CONFIG" not in cfg:
                    cfg["SIM_CONFIG"] = {}
                cfg["SIM_CONFIG"][name] = ov["value"]
            if "type" in ov:
                for v in cfg.get("variables", []):
                    if v["name"] == name:
                        v["type"] = ov["type"]
                        v["data_type"] = ov["type"]
        ConfigManager.save(cfg)
        QMessageBox.information(self, "Success", "Configuration Applied!")

    def _get_preset_dir(self):
        cfg = ConfigManager.load()
        model_path = cfg.get("MODEL_PATH", "")
        model_name = Path(model_path).stem if model_path else "Default"
        target = CONFIG_DIR / model_name
        target.mkdir(parents=True, exist_ok=True)
        return target

    def _save_preset(self):
        name = self.preset_name.text()
        if not name:
            return
        data = {"overrides": self.overrides}
        with open(self._get_preset_dir() / f"{name}.json", "w") as f:
            json.dump(data, f, indent=4)
        self._refresh_presets()

    def _load_preset(self):
        name = self.preset_combo.currentText()
        if not name:
            return
        try:
            with open(self._get_preset_dir() / f"{name}.json", "r") as f:
                data = json.load(f)
                self.overrides = data.get("overrides", {})
                self._apply_config()
        except:
            pass

    def _refresh_presets(self):
        self.preset_combo.clear()
        target = self._get_preset_dir()
        if target.exists():
            for f in target.glob("*.json"):
                self.preset_combo.addItem(f.stem)

    def _sync_overrides_from_config(self):
        cfg = ConfigManager.load()
        self.overrides = {}

        # 1. Sync Values (SIM_CONFIG)
        sim_config = cfg.get("SIM_CONFIG", {})
        for name, value in sim_config.items():
            if name not in self.overrides:
                self.overrides[name] = {}
            self.overrides[name]["value"] = value

        # 2. Sync Actions ranges
        actions = cfg.get("ACTIONS", {})
        for name, props in actions.items():
            if name not in self.overrides:
                self.overrides[name] = {}
            if "low" in props:
                self.overrides[name]["low"] = props["low"]
            if "high" in props:
                self.overrides[name]["high"] = props["high"]

    def _reset_configuration(self):
        confirm = QMessageBox.question(
            self,
            "Reset Configuration",
            "Are you sure you want to reset all overrides and reload data?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.overrides = {}
            # Clear SIM_CONFIG and ACTIONS in config.json?
            cfg = ConfigManager.load()
            if "SIM_CONFIG" in cfg:
                del cfg["SIM_CONFIG"]
            if "ACTIONS" in cfg:
                del cfg["ACTIONS"]
            ConfigManager.save(cfg)

            # Reload scan data
            self.load_from_scan()
            QMessageBox.information(self, "Reset", "Configuration reset.")


class RewardTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        left = QWidget()
        lv = QVBoxLayout(left)
        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont("Consolas", 12))
        lv.addWidget(QLabel("Reward Expression (Python):"))
        lv.addWidget(self.editor)
        save_btn = QPushButton("Save Reward Function")
        save_btn.clicked.connect(self._save)

        # Verify Button
        verify_btn = QPushButton("Verify")
        verify_btn.setStyleSheet("background-color: orange; color: black; font-weight: bold;")
        verify_btn.clicked.connect(self._verify)

        h = QHBoxLayout()
        h.addWidget(save_btn)
        h.addWidget(verify_btn)
        lv.addLayout(h)
        layout.addWidget(left, stretch=2)

        right_panel = QWidget()
        rv = QVBoxLayout(right_panel)

        # 1. Variables List
        var_grp = QGroupBox("Available Variables")
        vl = QVBoxLayout(var_grp)
        self.var_list = QListWidget()
        self.var_list.itemClicked.connect(self._insert_var)
        vl.addWidget(self.var_list)
        rv.addWidget(var_grp)

        # 2. Math Ref
        vbox = QVBoxLayout()
        vbox.addWidget(QLabel("Available Variables"))
        self.vars_list = QListWidget()  # Assuming this is meant to be self.var_list or a new one
        vbox.addWidget(self.vars_list)

        # Detailed Math Reference
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        math_content = QWidget()
        math_l = QVBoxLayout(math_content)

        def add_math_sec(title, items):
            g = QGroupBox(title)
            gl = QFormLayout(g)
            for k, v in items:
                l = QLabel(k)
                l.setStyleSheet("font-family: Consolas; font-weight: bold; color: #569CD6;")
                gl.addRow(l, QLabel(v))
            math_l.addWidget(g)

        add_math_sec(
            "Arithmetic",
            [("a + b", "Add"), ("a - b", "Subtract"), ("a * b", "Multiply"), ("a / b", "Divide"), ("a ** b", "Power")],
        )
        add_math_sec(
            "Functions", [("abs(x)", "Absolute"), ("min(a,b)", "Min"), ("max(a,b)", "Max"), ("round(x)", "Round")]
        )
        add_math_sec(
            "Advanced", [("math.log(x)", "Log_e"), ("math.sqrt(x)", "Sqrt"), ("math.sin(x)", "Sin"), ("math.pi", "PI")]
        )
        add_math_sec("Logic", [("10 if x>0 else -1", "Condition")])

        math_l.addStretch()
        scroll.setWidget(math_content)
        vbox.addWidget(scroll)

        spl = QSplitter(Qt.Orientation.Vertical)  # Assuming spl is a QSplitter
        spl.addWidget(var_grp)  # Add the existing var_grp
        spl.addWidget(scroll)  # Add the new math reference scroll area
        rv.addWidget(spl)  # Add the splitter to the right panel layout

        layout.addWidget(right_panel, stretch=1)

        self.refresh_vars()
        cfg = ConfigManager.load()
        if "REWARD_FUNCTION" in cfg:
            self.editor.setPlainText(cfg["REWARD_FUNCTION"].get("expression", ""))

    def refresh_vars(self):
        self.var_list.clear()
        scan = ConfigManager.load_scan_results()
        for v in scan.get("variables", []):
            if v.get("use_obs"):
                self.var_list.addItem(v["name"])

    def _insert_var(self, item):
        self.editor.insertPlainText(item.text())
        self.editor.setFocus()

    def _verify(self):
        expr = self.editor.toPlainText()
        try:
            # Mock context
            ctx = {"math": math, "np": None}
            # Add dummy vars
            scan = ConfigManager.load_scan_results()
            for v in scan.get("variables", []):
                ctx[v["name"]] = 1.0
            eval(expr, {}, ctx)
            QMessageBox.information(self, "Valid", "Expression is valid syntax.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _save(self):
        expr = self.editor.toPlainText()
        cfg = ConfigManager.load()
        scan = ConfigManager.load_scan_results()
        used = []
        for v in scan.get("variables", []):
            if re.search(r"\b" + re.escape(v["name"]) + r"\b", expr):
                used.append(v["name"])
        cfg["REWARD_FUNCTION"] = {"type": "expression", "expression": expr, "variables": used}
        ConfigManager.save(cfg)
        QMessageBox.information(self, "Saved", "Reward function updated.")


class DashboardTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        # HUD
        hud = QFrame()
        hud.setStyleSheet("background-color: #2b2b2b; border-radius: 8px;")
        hud.setFixedHeight(80)
        hud_layout = QHBoxLayout(hud)

        def mk_metric(label, default):
            container = QWidget()
            vbox = QVBoxLayout(container)
            vbox.setContentsMargins(0, 0, 0, 0)
            l = QLabel(label)
            l.setStyleSheet("color: #aaa; font-weight: bold;")
            v = QLabel(default)
            v.setStyleSheet("color: white; font-size: 24px; font-weight: bold;")
            vbox.addWidget(l)
            vbox.addWidget(v)
            vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
            return container, v

        self.time_widget, self.lbl_time = mk_metric("⏱️ Time", "00:00:00")
        self.ep_widget, self.lbl_ep = mk_metric("🔄 Episode", "0 / 0")
        self.envs_widget, self.lbl_envs = mk_metric("🏙️ Envs", "1")
        hud_layout.addStretch()
        hud_layout.addWidget(self.time_widget)
        hud_layout.addSpacing(50)
        hud_layout.addWidget(self.ep_widget)
        hud_layout.addSpacing(50)
        hud_layout.addWidget(self.envs_widget)
        hud_layout.addStretch()
        layout.addWidget(hud)

        config_area = QHBoxLayout()
        left_grp = QGroupBox("Simulation Limits & Options")
        l_form = QFormLayout(left_grp)
        self.params = {}
        self.cfg = ConfigManager.load()

        def add_p(layout, label, key, parent_key, default_val, info_key):
            val = self.cfg.get(parent_key, {}).get(key, default_val)
            le = QLineEdit(str(val))
            h = QHBoxLayout()
            h.addWidget(le)
            h.addWidget(InfoButton(info_key))
            layout.addRow(label, h)
            self.params[f"{parent_key}.{key}"] = le

        add_p(l_form, "Num Envs:", "n_envs", "TRAINING", 1, "NUM_ENVS")
        add_p(l_form, "Total Episodes:", "total_episodes", "TRAINING", 1000, "TOTAL_EPISODES")
        add_p(l_form, "Steps/Episode:", "steps_per_episode", "TRAINING", 100, "STEPS_PER_EP")
        add_p(l_form, "Max Duration (min):", "max_duration", "TRAINING", 0, "MAX_DURATION")

        toggles_frame = QFrame()
        grid = QGridLayout(toggles_frame)
        self.toggles = {}

        def add_t(label, key, parent_key, default, row, col):
            chk = QCheckBox(label)
            chk.setChecked(self.cfg.get(parent_key, {}).get(key, default))
            grid.addWidget(chk, row, col)
            self.toggles[f"{parent_key}.{key}"] = chk
            return chk

        add_t("Enable TensorBoard", "use_tensorboard", "TRAINING", True, 0, 0)
        add_t("Auto-Launch TB", "auto_launch_tb", "TRAINING", True, 1, 0)
        add_t("Save Models", "save_models", "TRAINING", False, 2, 0)
        add_t("Norm Obs", "norm_obs", "TRAINING", True, 0, 1)
        add_t("Norm Reward", "norm_reward", "TRAINING", True, 1, 1)
        add_t("Sound on Finish", "play_sound", "TRAINING", True, 2, 1)

        # Extended Logging Row
        ext_row = QHBoxLayout()
        self.chk_ext = QCheckBox("Extended Log")
        is_ext = self.cfg.get("TRAINING", {}).get("extended_logging", False)
        self.chk_ext.setChecked(is_ext)
        self.toggles["TRAINING.extended_logging"] = self.chk_ext
        ext_row.addWidget(self.chk_ext)

        self.combo_freq = QComboBox()
        self.combo_freq.addItems(["10", "100", "500", "1000"])
        self.combo_freq.setCurrentText(str(self.cfg.get("TRAINING", {}).get("extended_logging_freq", "10")))
        ext_row.addWidget(QLabel("Freq:"))
        ext_row.addWidget(self.combo_freq)
        self.toggles["TRAINING.extended_logging_freq"] = self.combo_freq

        grid.addLayout(ext_row, 3, 0, 1, 2)

        l_form.addRow(toggles_frame)

        # --- File Selectors (Script & VEnv) ---
        l_form.addRow(QLabel("Paths Override:"))

        # Script
        self.dash_script = FileSelector("SCAN_SCRIPT", self.cfg, filters="Python (*.py)")
        # Manually override key binding since FileSelector is usually auto-bound?
        # Actually FileSelector updates self.config[key]. We need to make sure we use Training Script key if distinct.
        # But 'SCAN_SCRIPT' is for Scan. We need 'TRAIN_SCRIPT' or just generic override.
        # User request: "Script Path Selector". Original App used "SCAN_SCRIPT" mostly or a dedicated one.
        # Let's check original... it used "Scripts/train_agent.py" hardcoded mostly or settable.
        # To be safe, we'll just add simple browsing QLineEdits that override the defaults.

        def browse_file(target_widget):
            f, _ = QFileDialog.getOpenFileName(self, "Select File")
            if f:
                target_widget.setText(f)

        self.train_script = QLineEdit(str(BASE_DIR / "AlpyneXtend" / "Scripts" / "train_agent.py"))
        btn_script = QPushButton("...")
        btn_script.setFixedWidth(30)
        btn_script.clicked.connect(lambda: browse_file(self.train_script))
        h_s = QHBoxLayout()
        h_s.addWidget(self.train_script)
        h_s.addWidget(btn_script)
        l_form.addRow("Train Script:", h_s)

        self.train_venv = QLineEdit(self.cfg.get("PYTHON_VENV", sys.executable))
        btn_venv = QPushButton("...")
        btn_venv.setFixedWidth(30)
        btn_venv.clicked.connect(lambda: browse_file(self.train_venv))
        h_v = QHBoxLayout()
        h_v.addWidget(self.train_venv)
        h_v.addWidget(btn_venv)
        l_form.addRow("Python VEnv:", h_v)

        config_area.addWidget(left_grp)

        right_grp = QGroupBox("Agent Hyperparameters (SAC)")
        r_form = QFormLayout(right_grp)
        add_p(r_form, "Policy:", "policy", "RL_AGENT_SETTINGS", "MlpPolicy", "POLICY")
        add_p(r_form, "Learning Rate:", "learning_rate", "SAC_PARAMS", 0.0003, "LEARNING_RATE")
        add_p(r_form, "Batch Size:", "batch_size", "SAC_PARAMS", 256, "BATCH_SIZE")
        add_p(r_form, "Gamma:", "gamma", "SAC_PARAMS", 0.99, "GAMMA")
        add_p(r_form, "Tau:", "tau", "SAC_PARAMS", 0.005, "TAU")
        add_p(r_form, "Net Arch:", "policy_net_arch", "SAC_PARAMS", "[256, 256]", "NET_ARCH")
        config_area.addWidget(right_grp)
        layout.addLayout(config_area)

        ctrl = QHBoxLayout()
        self.btn_start = QPushButton("START TRAINING")
        self.btn_start.setStyleSheet("background-color: #1f6aa5; color: white; padding: 10px; font-weight: bold;")
        self.btn_start.clicked.connect(self._start)
        self.btn_stop = QPushButton("STOP")
        self.btn_stop.setStyleSheet("background-color: #c0392b; color: white; padding: 10px; font-weight: bold;")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop)

        # TB Buttons
        btn_tb = QPushButton("Open TB UI")
        btn_tb.clicked.connect(self._open_tb)
        btn_stop_tb = QPushButton("Stop TB")
        btn_stop_tb.clicked.connect(self._stop_tb)
        btn_arc = QPushButton("Archive Logs")
        btn_arc.clicked.connect(self._archive_logs)

        ctrl.addWidget(self.btn_start)
        ctrl.addWidget(self.btn_stop)
        ctrl.addWidget(btn_tb)
        ctrl.addWidget(btn_stop_tb)
        ctrl.addWidget(btn_arc)
        layout.addLayout(ctrl)

        # Directory Buttons
        dir_layout = QHBoxLayout()
        btn_mdl_dir = QPushButton("Open Models Folder")
        btn_mdl_dir.clicked.connect(self._open_models_dir)
        btn_log_dir = QPushButton("Open TB Logs Folder")
        btn_log_dir.clicked.connect(self._open_tb_logs_dir)
        dir_layout.addStretch()
        dir_layout.addWidget(btn_mdl_dir)
        dir_layout.addWidget(btn_log_dir)
        layout.addLayout(dir_layout)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet("background-color: #1e1e1e; color: #ccc; font-family: Consolas;")
        self.highlighter = LogHighlighter(self.log.document())
        layout.addWidget(self.log)

    def _update_metrics(self, time_str, ep_str, envs_str):
        self.lbl_time.setText(time_str)
        self.lbl_ep.setText(ep_str)
        self.lbl_envs.setText(envs_str)

    def _start(self):
        cfg = ConfigManager.load()
        for k, widget in self.params.items():
            parent, key = k.split(".")
            if parent not in cfg:
                cfg[parent] = {}
            val = widget.text()
            try:
                if "[" in val:
                    cfg[parent][key] = json.loads(val)
                elif "." in val:
                    cfg[parent][key] = float(val)
                else:
                    cfg[parent][key] = int(val)
            except:
                cfg[parent][key] = val
        for k, widget in self.toggles.items():
            parent, key = k.split(".")
            if parent not in cfg:
                cfg[parent] = {}
            if isinstance(widget, QComboBox):
                cfg[parent][key] = widget.currentText()
            else:
                cfg[parent][key] = widget.isChecked()
        ConfigManager.save(cfg)

        self.log.clear()
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.lbl_envs.setText(str(cfg["TRAINING"].get("n_envs", 1)))

        # venv = cfg.get("PYTHON_VENV", sys.executable)
        # if not venv: venv = sys.executable
        # cmd = [venv, str(BASE_DIR / "AlpyneXtend" / "Scripts" / "train_agent.py")]

        # Use paths from UI override
        venv = self.train_venv.text()
        if not venv:
            venv = sys.executable
        script = self.train_script.text()
        if not script:
            script = str(BASE_DIR / "AlpyneXtend" / "Scripts" / "train_agent.py")

        cmd = [venv, script]

        self.thread = ScriptRunnerThread(cmd, str(BASE_DIR), cfg["TRAINING"].get("n_envs", 1))
        self.thread.log_signal.connect(self.log.append)
        self.thread.metric_signal.connect(self._update_metrics)
        self.thread.finished_signal.connect(lambda: [self.btn_start.setEnabled(True), self.btn_stop.setEnabled(False)])
        self.thread.start()

        if cfg["TRAINING"].get("play_sound", True):
            self.thread.finished_signal.connect(lambda: QApplication.beep())

    def _stop(self):
        if hasattr(self, "thread"):
            self.thread.stop()
            self.log.append("STOPPED.")

    def _open_tb(self):
        venv = ConfigManager.load().get("PYTHON_VENV", sys.executable) or sys.executable
        self.tb_process = subprocess.Popen(
            [venv, "-m", "tensorboard.main", "--logdir", str(TB_LOGS_DIR), "--port", "6006"],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        webbrowser.open("http://localhost:6006")

    def _stop_tb(self):
        # Kill the process if we started it
        if hasattr(self, "tb_process") and self.tb_process:
            self.tb_process.kill()
            self.tb_process = None
            QMessageBox.information(self, "TensorBoard", "TensorBoard process stopped.")
        else:
            # Fallback for manually started TB or zombie
            try:
                subprocess.run(
                    ["taskkill", "/F", "/IM", "tensorboard.exe"],
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                QMessageBox.information(self, "TensorBoard", "Killed all tensorboard.exe processes.")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not stop TensorBoard: {e}")

    def _open_models_dir(self):
        target = BASE_DIR
        if os.path.exists(target):
            os.startfile(target)
        else:
            QMessageBox.warning(self, "Error", f"Folder not found: {target}")

    def _open_tb_logs_dir(self):
        if TB_LOGS_DIR.exists():
            os.startfile(str(TB_LOGS_DIR))
        else:
            QMessageBox.warning(self, "Error", f"Folder not found: {TB_LOGS_DIR}")

    def _archive_logs(self):
        ts = time.strftime("%Y%m%d_%H%M%S")
        target = BASE_DIR / "AlpyneXtend" / "tensorboard_archives" / f"Archive_{ts}"
        target.mkdir(parents=True, exist_ok=True)
        for item in TB_LOGS_DIR.glob("*"):
            shutil.move(str(item), str(target))
        QMessageBox.information(self, "Archived", f"Logs moved to {target}")


# --- Testing Tab ---
class TestingTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select Model (.zip):"))
        self.model_path = QLineEdit()
        btn = QPushButton("Browse")
        btn.clicked.connect(self._browse)
        h = QHBoxLayout()
        h.addWidget(self.model_path)
        h.addWidget(btn)
        layout.addLayout(h)

        opt_layout = QHBoxLayout()
        self.episodes = QSpinBox()
        self.episodes.setValue(5)
        self.episodes.setPrefix("Episodes: ")
        self.stochastic = QCheckBox("Use Stochastic Policy")
        opt_layout.addWidget(self.episodes)
        opt_layout.addWidget(self.stochastic)
        layout.addLayout(opt_layout)

        self.btn_run = QPushButton("RUN EVALUATION")
        self.btn_run.setStyleSheet("background-color: #8B5CF6; color: white; font-weight: bold; padding: 10px;")
        self.btn_run.clicked.connect(self._run_test)
        layout.addWidget(self.btn_run)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("background-color: #1e1e1e; color: #dcdcdc; font-family: Consolas;")
        self.highlighter = LogHighlighter(self.log_view.document())  # Reuse logic
        layout.addWidget(self.log_view)

    def _browse(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select Model", filter="Zip files (*.zip)")
        if f:
            self.model_path.setText(f)

    def _run_test(self):
        self.log_view.clear()
        cfg = ConfigManager.load()
        venv = cfg.get("PYTHON_VENV", sys.executable)
        if not venv:
            venv = sys.executable
        cmd = [
            venv,
            str(BASE_DIR / "AlpyneXtend" / "Scripts" / "test_agent.py"),
            "--model",
            self.model_path.text(),
            "--episodes",
            str(self.episodes.value()),
        ]
        if self.stochastic.isChecked():
            cmd.append("--stochastic")
        self.thread = ScriptRunnerThread(cmd, str(BASE_DIR))
        self.thread.log_signal.connect(self.log_view.append)
        self.thread.start()


# --- Main Window ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Alpyne-Xtend (PyQt6)")
        self.resize(1280, 850)

        # Restore Geometry
        geo = AppSettings.get("window_geometry")
        if geo:
            self.restoreGeometry(bytes.fromhex(geo))
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet("background-color: #212121;")
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(0, 20, 0, 20)
        title = QLabel("ALPYNE XTEND")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: white; margin-bottom: 20px;")
        sb_layout.addWidget(title)

        self.btn_setup = self._nav_btn("A. SETUP", sb_layout)
        self.btn_train = self._nav_btn("B. TRAINING", sb_layout)
        self.btn_test = self._nav_btn("C. TESTING", sb_layout)
        self.btn_train = self._nav_btn("B. TRAINING", sb_layout)
        self.btn_test = self._nav_btn("C. TESTING", sb_layout)
        sb_layout.addStretch()

        self.btn_settings = QPushButton("⚙ Settings")
        self.btn_settings.setStyleSheet("background: transparent; color: #aaa; border: none; font-size: 14px;")
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.clicked.connect(self._open_settings)
        sb_layout.addWidget(self.btn_settings)

        main_layout.addWidget(sidebar)

        self.stack = QStackedWidget()
        self.phase_a = QTabWidget()
        self.phase_a.addTab(
            GuideTab(
                "<h1>Setup Guide</h1><p>1. Select Project...<br>2. Configure Experiment...<br>3. Review Code...</p>"
            ),
            "0. Setup Guide",
        )
        self.phase_a.addTab(ProjectSetupTab(), "1. Project Setup")
        self.ex_config = ExperimentConfigTab()
        # Connect Sync Signal
        self.ex_config.model.dataRefreshed.connect(self._on_variables_toggled)
        self.phase_a.addTab(self.ex_config, "2. Experiment Configuration")
        self.phase_a.addTab(CodeReviewTab(), "3. Code Review")

        self.phase_b = QTabWidget()
        self.phase_b.addTab(
            GuideTab("<h1>Training Guide</h1><p>1. Config Params...<br>2. Set Rewards...<br>3. Start Training...</p>"),
            "0. Training Guide",
        )
        self.param_tab = ParamConfigTab()
        self.phase_b.addTab(self.param_tab, "1. Parameter Configuration")
        self.phase_b.addTab(RewardTab(), "2. Reward Function")
        self.phase_b.addTab(DashboardTab(), "3. Training Dashboard")

        self.phase_c = TestingTab()
        self.stack.addWidget(self.phase_a)
        self.stack.addWidget(self.phase_b)
        self.stack.addWidget(self.phase_c)
        main_layout.addWidget(self.stack)

        self.btn_setup.clicked.connect(lambda: self._switch(0, self.btn_setup))
        self.btn_train.clicked.connect(lambda: self._switch(1, self.btn_train))
        self.btn_test.clicked.connect(lambda: self._switch(2, self.btn_test))
        self._switch(0, self.btn_setup)

        # Auto-Load Scan Results on Startup
        if SCAN_RESULTS_PATH.exists():
            QTimer.singleShot(500, self.ex_config.load_data)

        # Tab Change Handlers
        self.phase_a.currentChanged.connect(self._on_setup_tab_changed)
        self.phase_b.currentChanged.connect(self._on_training_tab_changed)

    def _on_setup_tab_changed(self, index):
        # Refresh data when entering Experiment Config tab
        if index == 2:
            self.ex_config.load_data()

    def _on_training_tab_changed(self, index):
        # Refresh data when entering Parameter or Reward tab
        if index == 1:
            self.param_tab.load_from_scan()
        elif index == 2:
            self.phase_b.widget(2).refresh_vars()

    def _on_variables_toggled(self):
        # Called when checkboxes in Tab A.2 change
        # Force reload of Param Config to reflect new inclusions
        self.param_tab.load_from_scan()

    def _nav_btn(self, text, layout):
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setFixedHeight(45)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton { background: transparent; color: #b0b0b0; text-align: left; padding-left: 20px; border: none; font-weight: bold; }
            QPushButton:hover { background: #333333; color: white; }
            QPushButton:checked { background: #2b2b2b; color: #3B8ED0; border-left: 4px solid #3B8ED0; }
        """)
        layout.addWidget(btn)
        return btn

    def _switch(self, idx, btn):
        self.stack.setCurrentIndex(idx)
        for b in [self.btn_setup, self.btn_train, self.btn_test]:
            b.setChecked(b == btn)
        if idx == 1:
            self.param_tab.load_from_scan()
            self.phase_b.widget(2).refresh_vars()

    def closeEvent(self, event):
        # Save Geometry
        AppSettings.set("window_geometry", self.saveGeometry().toHex().data().decode())

        # Kill Zombies
        subprocess.run(["taskkill", "/F", "/IM", "java.exe"], capture_output=True, creationflags=0x08000000)
        subprocess.run(["taskkill", "/F", "/IM", "tensorboard.exe"], capture_output=True, creationflags=0x08000000)
        event.accept()

    def _open_settings(self):
        d = QDialog(self)
        d.setWindowTitle("Settings")
        d.setFixedSize(300, 200)
        l = QVBoxLayout(d)
        l.addWidget(QLabel("Appearance Theme:"))
        combo = QComboBox()
        combo.addItems(["Dark", "Light", "Auto"])
        l.addWidget(combo)
        l.addWidget(QLabel("<i>Note: Restart required for some changes.</i>"))
        l.addStretch()
        d.exec()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    try:
        app.setStyleSheet(qdarktheme.load_stylesheet(theme="dark", corner_shape="sharp"))
    except:
        try:
            app.setStyleSheet(qdarktheme.load_stylesheet())
        except Exception as e:
            print(f"Theme Error: {e}")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
