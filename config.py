import os
import json
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Userbot configuration. All settings from environment variables."""

    # Telegram API
    API_ID = int(os.environ.get("API_ID", 0))
    API_HASH = os.environ.get("API_HASH", "")
    PHONE = os.environ.get("PHONE", "")

    # Pyrogram session string (alternative to phone)
    SESSION_STRING = os.environ.get("SESSION_STRING", "")

    # Web panel
    WEB_PORT = int(os.environ.get("PORT", 8080))

    # Paths
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")            # built-in scripts (tracked)
    CUSTOM_SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts_custom")  # user scripts (gitignored)
    BACKUPS_DIR = os.path.join(BASE_DIR, "backups")
    AUTO_START_FILE = os.path.join(CUSTOM_SCRIPTS_DIR, "auto_start.json")

    # Loaded scripts
    loaded_modules = {}
    loaded_modules_info = {}

    # Log buffer for web console
    log_buffer = []
    MAX_LOG_LINES = 500

    @classmethod
    def add_log(cls, message: str, level: str = "INFO"):
        entry = f"[{level}] {message}"
        cls.log_buffer.append(entry)
        if len(cls.log_buffer) > cls.MAX_LOG_LINES:
            cls.log_buffer.pop(0)

    @classmethod
    def get_logs(cls):
        return cls.log_buffer.copy()

    @classmethod
    def clear_logs(cls):
        cls.log_buffer.clear()

    # ── Auto-start persistence ──────────────────────────────────────────

    @classmethod
    def get_auto_start(cls) -> list:
        """Return the list of filenames that should auto-load on startup."""
        try:
            if os.path.exists(cls.AUTO_START_FILE):
                with open(cls.AUTO_START_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return [fn for fn in data if isinstance(fn, str) and fn.endswith(".py")]
        except Exception:
            pass
        return []

    @classmethod
    def set_auto_start(cls, filename: str, enabled: bool) -> bool:
        """Add or remove a script from the auto-start list."""
        if not filename.endswith(".py"):
            filename += ".py"
        scripts = cls.get_auto_start()
        if enabled and filename not in scripts:
            scripts.append(filename)
        elif not enabled and filename in scripts:
            scripts.remove(filename)
        try:
            os.makedirs(os.path.dirname(cls.AUTO_START_FILE), exist_ok=True)
            with open(cls.AUTO_START_FILE, "w", encoding="utf-8") as f:
                json.dump(scripts, f, indent=2, ensure_ascii=False)
            return True
        except Exception:
            return False
