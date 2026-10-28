"""Configuration from environment variables."""
import os

DB_PATH = os.environ.get("SAMS_DB", "sams.db")
SESSION_TIMEOUT = int(os.environ.get("SAMS_SESSION_TIMEOUT", "1800"))  # SAM-SR-006
