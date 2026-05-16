import os
import sys
import platform
import asyncio
import threading
import logging
import traceback
from datetime import datetime

# === Windows fix ===
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

import nest_asyncio
nest_asyncio.apply()

from flask import Flask
from config import Config
from web import create_web_app
from bot import run_bot

# ═══════════════════════════════════════════════════════════════════
#  Error logger — сохраняет ошибки в ops/
# ═══════════════════════════════════════════════════════════════════

OPS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ops")
os.makedirs(OPS_DIR, exist_ok=True)

_handler_errors_count = 0
_MAX_HANDLER_ERRORS = 50  # лимит чтобы не заспамить


class _ErrorFileHandler(logging.Handler):
    """Логирует ERROR и выше в отдельный .txt файл в ops/."""

    def emit(self, record):
        if record.levelno < logging.ERROR:
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(OPS_DIR, f"error_{ts}.txt")
        try:
            msg = self.format(record) + "\n\n" + (
                record.exc_text or traceback.format_exc()
                if record.exc_info else "No traceback"
            )
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"Time:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Logger:   {record.name}\n")
                f.write(f"Level:    {record.levelname}\n")
                f.write(f"Message:\n{msg}\n")
        except Exception:
            pass


# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
    ]
)

# Добавляем файловый хендлер для ошибок
_error_handler = _ErrorFileHandler()
_error_handler.setLevel(logging.ERROR)
_error_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logging.getLogger().addHandler(_error_handler)

logger = logging.getLogger("userbot")

# Global Flask app (needed for gunicorn/heroku)
app = create_web_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    plat = platform.system()
    ver = sys.version.split()[0]
    logger.info(f"Platform: {plat} | Python: {ver} | Logs dir: ops/")

    # Start Flask in a daemon thread (Flask is sync, no event loop needed)
    flask_thread = threading.Thread(
        target=lambda: app.run(
            host="0.0.0.0",
            port=port,
            debug=False,
            threaded=True,
            use_reloader=False,
        ),
        daemon=True,
    )
    flask_thread.start()

    logger.info(f"Web panel: http://localhost:{port}")
    logger.info("Starting userbot...")

    # Run bot on the MAIN thread's event loop (avoids "different loop" errors)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    nest_asyncio.apply(loop)

    try:
        loop.run_until_complete(run_bot())
    except KeyboardInterrupt:
        logger.info("Stopped by user (Ctrl+C)")
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        logger.critical(traceback.format_exc())
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()
        logger.info("Shutdown complete")
