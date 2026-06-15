from pathlib import Path

# WORK_DIR is dynamically set to the folder containing this directory.py file (solo-obsplan)
WORK_DIR = Path(__file__).resolve().parent

ROOT_DIR = WORK_DIR

# Directory paths for miscellaneous info.
INFO_DIR = WORK_DIR / "_info"

# Directory paths for executables and subscripts.
SCRIPT_DIR = WORK_DIR / "_subscripts"

# Directory path for observation plans (YAML files)
PLAN_DIR = WORK_DIR / "obsplans"

# Directory path for log files
LOG_DIR = WORK_DIR / "logs"

# Directory path to save observational data
DATA_DIR = Path("C:/RASA_Data/")