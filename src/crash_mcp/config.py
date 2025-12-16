import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    # Browser configuration
    BROWSER_HEADLESS = os.getenv("BROWSER_HEADLESS", "false").lower() == "true"
    BROWSER_TIMEOUT = int(os.getenv("BROWSER_TIMEOUT", "60"))
    BROWSER_WINDOW_SIZE = os.getenv("BROWSER_WINDOW_SIZE", "1920x1080")
    
    # Chrome Password Manager
    BROWSER_USE_DEFAULT_PROFILE = os.getenv("BROWSER_USE_DEFAULT_PROFILE", "false").lower() == "true"
    BROWSER_ENABLE_PASSWORD_MANAGER = os.getenv("BROWSER_ENABLE_PASSWORD_MANAGER", "true").lower() == "true"
    BROWSER_AUTO_FILL_PASSWORDS = os.getenv("BROWSER_AUTO_FILL_PASSWORDS", "true").lower() == "true"

    # Authentication configuration
    AUTH_CACHE_TTL = int(os.getenv("AUTH_CACHE_TTL", "3600"))
    AUTH_RETRY_ATTEMPTS = int(os.getenv("AUTH_RETRY_ATTEMPTS", "3"))
    
    # Auth timing
    MANUAL_AUTH_TIMEOUT = int(os.getenv("MANUAL_AUTH_TIMEOUT", "180"))
    AUTH_WAIT_TIME = int(os.getenv("AUTH_WAIT_TIME", "10"))

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    SUPPRESS_MCP_WARNINGS = os.getenv("SUPPRESS_MCP_WARNINGS", "true").lower() == "true"

    # Crash Analysis specific (defaults)
    CRASH_SEARCH_PATH = os.getenv("CRASH_SEARCH_PATH", "/var/crash")
