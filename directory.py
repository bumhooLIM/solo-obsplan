from pathlib import Path

# WORK_DIR is dynamically set to the folder containing this directory.py file (solo-obsplan)
WORK_DIR = Path(__file__).resolve().parent

# Directory paths for miscellaneous info.
INFO_DIR = WORK_DIR / "_info"

# Directory paths for executables and subscripts.
SCRIPT_DIR = WORK_DIR / "_subscripts"

# Directory path for log files
LOG_DIR = WORK_DIR / "log"

# Directory path to save observational data
DATA_DIR = WORK_DIR / "data"