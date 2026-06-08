import logging
import directory
from datetime import datetime, timezone
import time

def setup_logger(name="SOLO_TCS"):
    # Ensure the output directory exists
    directory.LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    # --- 1. Generate the Dynamic UT Filename ---
    # Fetch current UT time and format it to YYYYMMDD
    ut_now = datetime.now(timezone.utc)
    date_str = ut_now.strftime('%Y%m%d')
    
    # Create the dynamic file path: e.g., output/obslog_20260608.log
    log_file = directory.LOG_DIR / f"obslog_{date_str}.log"

    # --- 2. Initialize the Logger ---
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Prevent duplicate log entries if the module is imported multiple times
    if not logger.handlers:
        # File Handler (Appends to today's UT .log file)
        file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        file_handler.setLevel(logging.INFO)

        # Console Handler (Prints to the terminal)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)

        # Formatter: Matches your [YYYY-MM-DD HH:MM:SS] format
        formatter = logging.Formatter(
            '[%(asctime)s UT] [%(levelname)s] %(message)s', 
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # --- 3. Force Log Timestamps to UT ---
        # This guarantees the [YYYY-MM-DD HH:MM:SS] prefix is written in UT, not KST
        formatter.converter = time.gmtime
        
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        # Attach handlers to the logger
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger

# Instantiate the logger so other scripts can just import this variable
obs_logger = setup_logger()