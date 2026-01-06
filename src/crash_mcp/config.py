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
    
    # Knowledge Base
    KB_BASE_DIR = os.getenv("KB_BASE_DIR", "")  # Empty = use project-relative paths
    KB_SIMILARITY_THRESHOLD = float(os.getenv("KB_SIMILARITY_THRESHOLD", "0.2"))
    KB_EMBEDDING_MODEL = os.getenv("KB_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
