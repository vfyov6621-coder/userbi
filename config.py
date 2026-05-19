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
    SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")              # built-in scripts (tracked)
    CUSTOM_SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts_custom") # user scripts (gitignored)
    BACKUPS_DIR = os.path.join(BASE_DIR, "backups")
    AUTO_START_FILE = os.path.join(CUSTOM_SCRIPTS_DIR, "auto_start.json")
    ADDON_STATES_FILE = os.path.join(CUSTOM_SCRIPTS_DIR, "addon_states.json")

    # Loaded scripts: script_id -> module
    loaded_modules = {}
    # Loaded addons: script_id -> {addon_file -> module}
    loaded_addons = {}
    # Script info cache
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
        """Return the list of script IDs that should auto-load on startup.
        If no auto_start.json exists, loads ALL available scripts."""
        try:
            if os.path.exists(cls.AUTO_START_FILE):
                with open(cls.AUTO_START_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return [s for s in data if isinstance(s, str)]
        except Exception:
            pass
        # Нет auto_start.json — вернём None (загрузить всё)
        return None

    @classmethod
    def set_auto_start(cls, script_id: str, enabled: bool) -> bool:
        """Add or remove a script from the auto-start list."""
        scripts = cls.get_auto_start()
        if scripts is None:
            # Первый раз создаём список со всеми текущими скриптами
            from loader import ScriptLoader
            scripts = ScriptLoader().get_available_scripts()
        if enabled and script_id not in scripts:
            scripts.append(script_id)
        elif not enabled and script_id in scripts:
            scripts.remove(script_id)
        try:
            os.makedirs(os.path.dirname(cls.AUTO_START_FILE), exist_ok=True)
            with open(cls.AUTO_START_FILE, "w", encoding="utf-8") as f:
                json.dump(scripts, f, indent=2, ensure_ascii=False)
            return True
        except Exception:
            return False

    # ── Addon states persistence ────────────────────────────────────────

    @classmethod
    def get_addon_states(cls, script_id: str) -> dict:
        """Get enabled/disabled states for addons of a script."""
        try:
            if os.path.exists(cls.ADDON_STATES_FILE):
                with open(cls.ADDON_STATES_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and script_id in data:
                    return data[script_id]
        except Exception:
            pass
        return {}

    @classmethod
    def set_addon_state(cls, script_id: str, addon_file: str, enabled: bool) -> bool:
        """Set addon enabled/disabled state."""
        try:
            all_states = {}
            if os.path.exists(cls.ADDON_STATES_FILE):
                with open(cls.ADDON_STATES_FILE, "r", encoding="utf-8") as f:
                    all_states = json.load(f)
            if not isinstance(all_states, dict):
                all_states = {}
            if script_id not in all_states:
                all_states[script_id] = {}
            all_states[script_id][addon_file] = enabled
            os.makedirs(os.path.dirname(cls.ADDON_STATES_FILE), exist_ok=True)
            with open(cls.ADDON_STATES_FILE, "w", encoding="utf-8") as f:
                json.dump(all_states, f, indent=2, ensure_ascii=False)
            return True
        except Exception:
            return False
