import os
import sys
import platform
import asyncio
import threading
import logging

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

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger("userbot")

# Global Flask app (needed for gunicorn/heroku)
app = create_web_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    plat = platform.system()
    logger.info(f"Platform: {plat} | Python: {sys.version.split()[0]}")

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
        pass
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()
