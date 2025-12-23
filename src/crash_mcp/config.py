import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    # Logging

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    SUPPRESS_MCP_WARNINGS = os.getenv("SUPPRESS_MCP_WARNINGS", "true").lower() == "true"

    # Crash Analysis specific (defaults)
    CRASH_SEARCH_PATH = os.getenv("CRASH_SEARCH_PATH", "/var/crash")
