# version 2
# alpyne/log_utils.py
import logging
from datetime import datetime
from typing import Union, Optional

# Use a try-except block for imports to allow this module to be loaded
# even if alpyne is not fully installed, though it's expected to be.
try:
    from alpyne.sim import AnyLogicSim
    from alpyne.data import FieldData, SimSchema, EngineSettings, SimStatus, EngineStatus, SimObservation
except ImportError:
    # Define dummy classes if alpyne is not available to avoid crashing on load.
    AnyLogicSim = FieldData = SimSchema = EngineSettings = SimStatus = EngineStatus = SimObservation = object

def setup_logging(log_file_name: str, level=logging.INFO) -> logging.Logger:
    """
    Configures and returns a logger instance, overwriting the file on each run.
    """
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    logging.basicConfig(
        filename=log_file_name,
        level=level,
        format='%(asctime)s - %(levelname)s - %(name)s - %(funcName)s - %(message)s',
        filemode='w'
    )
    return logging.getLogger(log_file_name.split('.')[0])

# --- Master Logging Function ---

def log_simulation_state(logger: logging.Logger, sim_instance: AnyLogicSim, prefix: str):
    """
    Logs a comprehensive snapshot of the simulation's state by calling all
    individual logging functions and handling exceptions internally.

    :param logger: The logger instance to use.
    :param sim_instance: The AnyLogicSim instance (e.g., env_Base).
    :param prefix: A string to prepend to log sections (e.g., "Initial", "Final").
    """
    logger.info(f"--- Capturing {prefix.upper()} Model State ---")

    # Log Schema
    log_sim_schema(logger, sim_instance.schema)

    # Log Engine Settings
    log_engine_settings_instance(logger, sim_instance.engine_settings, prefix=prefix)

    # Log Model Outputs
    try:
        log_model_outputs(logger, sim_instance.outputs(), prefix=prefix)
    except Exception as e:
        logger.warning(f"Could not retrieve {prefix.lower()} model outputs (this is expected for initial state): {e}")

    # Log Simulation Status
    try:
        log_sim_status(logger, sim_instance.status(), prefix=prefix)
    except Exception as e:
        logger.error(f"Error retrieving {prefix.lower()} SimStatus: {e}")

    # Log Detailed Engine Status
    try:
        log_engine_status_details(logger, sim_instance._engine(), prefix=prefix)
    except Exception as e:
        logger.warning(f"Could not retrieve {prefix.lower()} detailed _engine() status: {e}")

    logger.info(f"--- Finished Capturing {prefix.upper()} Model State ---")


# --- Individual Component Loggers (called by the master function) ---

def format_field_data(fd: FieldData) -> str:
    """Formats a FieldData object into a readable string."""
    py_type_name = getattr(fd, 'py_type', 'Unknown')
    py_type_name = getattr(py_type_name, '__name__', str(py_type_name))
    return f"Name: {getattr(fd, 'name', 'N/A')}, Type: {getattr(fd, 'type', 'N/A')} (Python: {py_type_name}), Default: {getattr(fd, 'py_value', 'N/A')}, Units: {getattr(fd, 'units', 'N/A') or 'N/A'}"

def log_sim_schema(logger: logging.Logger, schema: Optional[SimSchema]):
    """Logs the content of the SimSchema."""
    logger.info("==================== SIMULATION SCHEMA ====================")
    if not isinstance(schema, SimSchema):
        logger.info(f"  Schema not available or in unexpected format: {schema}")
        logger.info("=======================================================")
        return

    sections = {
        "Inputs (Model Parameters)": schema.inputs,
        "Outputs (Analysis & Parameters)": schema.outputs,
        "RL Configuration Schema": schema.configuration,
        "RL Observation Schema": schema.observation,
        "RL Action Schema": schema.action,
        "Engine Settings Schema": schema.engine_settings
    }

    for section_name, section_data in sections.items():
        logger.info(f"--- {section_name} ---")
        if not section_data:
            logger.info("  (No fields defined in this section)")
            continue
        for field_name, field_obj in section_data.items():
            logger.info(f"  Field '{field_name}': {format_field_data(field_obj)}")
    logger.info("=======================================================")

def log_engine_settings_instance(logger: logging.Logger, es_instance: Optional[EngineSettings], prefix="Current"):
    """Logs the content of an EngineSettings instance."""
    logger.info(f"==================== {prefix.upper()} ENGINE SETTINGS (Instance) ====================")
    if not isinstance(es_instance, EngineSettings):
        logger.info(f"  EngineSettings instance not available or in unexpected format: {es_instance}")
        logger.info("========================================================================")
        return
    
    start_date = es_instance.start_date
    stop_date = es_instance.stop_date
    
    logger.info(f"  Units: {es_instance.units}")
    logger.info(f"  Start Time: {es_instance.start_time}")
    logger.info(f"  Start Date: {start_date.isoformat() if isinstance(start_date, datetime) else start_date}")
    logger.info(f"  Stop Time (effective): {es_instance.stop_time}")
    logger.info(f"  Stop Date (effective): {stop_date.isoformat() if isinstance(stop_date, datetime) else stop_date}")
    logger.info(f"  Seed: {es_instance.seed}")
    logger.info("========================================================================")

def log_sim_status(logger: logging.Logger, status: Optional[SimStatus], prefix="Current"):
    """Logs the content of a SimStatus object, handling unexpected types."""
    logger.info(f"==================== {prefix.upper()} SIMULATION STATUS ====================")
    if not isinstance(status, SimStatus):
        logger.info(f"  SimStatus not available or in a non-object format: {status}")
        logger.info("===========================================================")
        return

    state_val = status.state
    state_str = state_val.name if hasattr(state_val, 'name') else state_val
    model_date = status.date
    progress_val = status.progress
    progress_str = f"{progress_val:.2%}" if isinstance(progress_val, float) and progress_val != -1 else f"Progress: {progress_val} (N/A)"

    logger.info(f"  State: {state_str or 'N/A'}")
    logger.info(f"  Stop Condition Met (from model): {status.stop}")
    logger.info(f"  Sequence ID (resets + actions): {status.sequence_id}")
    logger.info(f"  Episode Number: {status.episode_num}")
    logger.info(f"  Step Number (actions in episode): {status.step_num}")
    logger.info(f"  Model Time: {status.time}")
    logger.info(f"  Model Date: {model_date.isoformat() if isinstance(model_date, datetime) else model_date}")
    logger.info(f"  Progress: {progress_str}")
    logger.info(f"  Message from Alpyne: {status.message or 'None'}")
    
    observation = status.observation
    logger.info(f"  --- Observation Data ({type(observation).__name__}) ---")
    if isinstance(observation, (SimObservation, dict)):
        if observation:
            for k, v in observation.items():
                logger.info(f"    {k}: {v}")
        else:
            logger.info("    (Observation data is empty or None)")
    else:
        logger.info(f"    Raw Observation: {observation}")
    logger.info("===========================================================")

def log_engine_status_details(logger: logging.Logger, engine_status: Optional[EngineStatus], prefix="Current"):
    """Logs the content of an EngineStatus object, handling unexpected types."""
    logger.info(f"==================== {prefix.upper()} DETAILED ENGINE STATUS ====================")
    if not isinstance(engine_status, EngineStatus):
        logger.info(f"  EngineStatus not available or in a non-object format: {engine_status}")
        logger.info("==================================================================")
        return

    engine_state_val = engine_status.state
    engine_state_str = engine_state_val.name if hasattr(engine_state_val, 'name') else engine_state_val
    model_date = engine_status.date
    progress_val = engine_status.progress
    progress_str = f"{progress_val:.2%}" if isinstance(progress_val, float) and progress_val != -1 else f"Progress: {progress_val}"

    logger.info(f"  Engine State: {engine_state_str or 'N/A'}")
    logger.info(f"  Engine Events Queued: {engine_status.engine_events}")
    logger.info(f"  Engine Steps Executed: {engine_status.engine_steps}")
    logger.info(f"  Next Engine Step Time (model units): {engine_status.next_engine_step}")
    logger.info(f"  Next Engine Event Time (model units): {engine_status.next_engine_event}")
    logger.info(f"  Model Time (detailed): {engine_status.time}")
    logger.info(f"  Model Date (detailed): {model_date.isoformat() if isinstance(model_date, datetime) else model_date}")
    logger.info(f"  Model Progress (detailed): {progress_str}")
    logger.info(f"  Engine Message: {engine_status.message or 'None'}")
    
    settings = engine_status.settings
    logger.info(f"  --- Actual Engine Settings In Use by Model ---")
    if settings:
        for k, v in settings.items():
            setting_value = v.isoformat() if isinstance(v, datetime) else str(v)
            logger.info(f"    {k}: {setting_value}")
    else:
        logger.info("    (No detailed engine settings reported by _engine())")
    logger.info("==================================================================")

def log_model_outputs(logger: logging.Logger, outputs: Optional[Union[list, dict]], prefix="Current"):
    """Logs the content of the model's outputs (parameters, analysis objects)."""
    logger.info(f"==================== {prefix.upper()} MODEL OUTPUTS ====================")
    if outputs is None:
        logger.info("  (Outputs are None - possibly no query made or model error)")
    elif not outputs:
        logger.info("  (No outputs retrieved or defined in the model schema)")
    elif isinstance(outputs, dict):
        for name, value in outputs.items():
            type_name = type(value).__name__
            if hasattr(value, '__dict__') and not isinstance(value, (int, float, str, bool, datetime)):
                logger.info(f"  Output '{name}' (Type: {type_name}):")
                if type_name == "DataSet":
                    logger.info(f"    xmin: {getattr(value, 'xmin', 'N/A')}, xmax: {getattr(value, 'xmax', 'N/A')}, ymin: {getattr(value, 'ymin', 'N/A')}, ymax: {getattr(value, 'ymax', 'N/A')}")
                    logger.info(f"    data points: {len(getattr(value, 'plainDataTable', []))}")
                elif type_name.startswith("Statistics"):
                    logger.info(f"    count: {getattr(value, 'count', 'N/A')}, mean: {getattr(value, 'mean', 'N/A')}, min: {getattr(value, 'min', 'N/A')}, max: {getattr(value, 'max', 'N/A')}")
                else:
                    logger.info(f"    Value (string representation): {str(value)[:200]}{'...' if len(str(value)) > 200 else ''}")
            else:
                logger.info(f"  Output '{name}' (Type: {type_name}): {str(value)[:200]}{'...' if len(str(value)) > 200 else ''}")
    elif isinstance(outputs, list):
        logger.info("  Outputs (returned as a list):")
        for i, value in enumerate(outputs):
            logger.info(f"    Item [{i}] (Type: {type(value).__name__}): {str(value)[:200]}{'...' if len(str(value)) > 200 else ''}")
    logger.info("========================================================")
