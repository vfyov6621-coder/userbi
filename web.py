import os
import logging
from flask import Flask, jsonify, request, render_template

from config import Config
from loader import ScriptLoader

logger = logging.getLogger("userbot.web")


def _get_bot_client():
    try:
        from bot import bot_client
        return bot_client
    except Exception:
        return None


def create_web_app():
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        static_folder=None,
    )

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/status", methods=["GET"])
    def status():
        loaded_count = len(Config.loaded_modules)
        loader = ScriptLoader()
        total_scripts = len(loader.get_available_scripts())
        bot_running = _get_bot_client() is not None

        return jsonify({
            "success": True,
            "bot_running": bot_running,
            "loaded_scripts": loaded_count,
            "total_scripts": total_scripts,
            "log_count": len(Config.log_buffer),
            "uptime_logs": len(Config.log_buffer),
        })

    @app.route("/api/logs", methods=["GET"])
    def get_logs():
        return jsonify({"success": True, "logs": Config.get_logs()})

    @app.route("/api/logs/clear", methods=["POST"])
    def clear_logs():
        Config.clear_logs()
        return jsonify({"success": True})

    @app.route("/api/scripts", methods=["GET"])
    def list_scripts():
        loader = ScriptLoader()
        scripts = []
        for filename in loader.get_available_scripts():
            info = loader.get_script_info(filename) or {}
            info["filename"] = filename
            info["loaded"] = filename in Config.loaded_modules
            scripts.append(info)
        return jsonify({"success": True, "scripts": scripts})

    @app.route("/api/scripts/<filename>", methods=["GET"])
    def get_script(filename):
        if not filename.endswith(".py"):
            filename += ".py"
        loader = ScriptLoader()
        source = loader.get_script_source(filename)
        if source is None:
            return jsonify({"success": False, "error": "File not found"}), 404
        return jsonify({
            "success": True,
            "filename": filename,
            "source": source,
            "loaded": filename in Config.loaded_modules,
            "is_custom": loader.is_custom_script(filename),
        })

    @app.route("/api/scripts", methods=["POST"])
    def save_script():
        data = request.get_json(silent=True) or {}
        filename = data.get("filename", "")
        source = data.get("source", "")
        if not filename:
            return jsonify({"success": False, "error": "Filename not specified"}), 400
        loader = ScriptLoader()
        result = loader.save_script(filename, source)
        if result["success"]:
            Config.add_log(f"Script {filename} saved via web panel")
        return jsonify(result)

    @app.route("/api/scripts/<path:filename>/load", methods=["POST"])
    def load_script(filename):
        if not filename:
            return jsonify({"success": False, "error": "Filename is empty"}), 400
        if not filename.endswith(".py"):
            filename += ".py"
        loader = ScriptLoader()
        client = _get_bot_client()
        result = loader.load_script(filename, client)
        if result["success"]:
            Config.add_log(f"Script {filename} loaded via web panel")
        return jsonify(result)

    @app.route("/api/scripts/<path:filename>/unload", methods=["POST"])
    def unload_script(filename):
        if not filename:
            return jsonify({"success": False, "error": "Filename is empty"}), 400
        if not filename.endswith(".py"):
            filename += ".py"
        loader = ScriptLoader()
        result = loader.unload_script(filename)
        if result["success"]:
            Config.add_log(f"Script {filename} unloaded via web panel")
        return jsonify(result)

    @app.route("/api/scripts/<path:filename>/reload", methods=["POST"])
    def reload_script(filename):
        if not filename:
            return jsonify({"success": False, "error": "Filename is empty"}), 400
        if not filename.endswith(".py"):
            filename += ".py"
        loader = ScriptLoader()
        client = _get_bot_client()
        loader.unload_script(filename)
        result = loader.load_script(filename, client)
        if result["success"]:
            Config.add_log(f"Script {filename} reloaded via web panel")
        return jsonify(result)

    @app.route("/api/scripts/<path:filename>", methods=["DELETE"])
    def delete_script(filename):
        if not filename:
            return jsonify({"success": False, "error": "Filename is empty"}), 400
        if not filename.endswith(".py"):
            filename += ".py"
        loader = ScriptLoader()
        result = loader.delete_script(filename)
        if result["success"]:
            Config.add_log(f"Script {filename} deleted via web panel")
            # Also remove from auto-start list
            Config.set_auto_start(filename, False)
        return jsonify(result)

    @app.route("/api/autostart", methods=["GET"])
    def get_autostart():
        """Return the list of scripts configured for auto-start."""
        return jsonify({"success": True, "scripts": Config.get_auto_start()})

    @app.route("/api/autostart/<path:filename>", methods=["POST"])
    def toggle_autostart(filename):
        """Toggle auto-start for a specific script. Body: {\"enabled\": true/false}"""
        if not filename:
            return jsonify({"success": False, "error": "Filename is empty"}), 400
        if not filename.endswith(".py"):
            filename += ".py"
        data = request.get_json(silent=True) or {}
        enabled = bool(data.get("enabled", True))
        loader = ScriptLoader()
        # Verify the script exists
        if not loader.get_script_source(filename):
            return jsonify({"success": False, "error": f"Script {filename} not found"}), 404
        ok = Config.set_auto_start(filename, enabled)
        if ok:
            Config.add_log(f"Auto-start {'enabled' if enabled else 'disabled'} for {filename}")
        return jsonify({"success": ok})

    @app.route("/api/debug/backup", methods=["POST"])
    def create_backup():
        loader = ScriptLoader()
        result = loader.create_backup()
        return jsonify(result)

    @app.route("/api/debug/backups", methods=["GET"])
    def list_backups():
        loader = ScriptLoader()
        backups = loader.get_backups()
        return jsonify({"success": True, "backups": backups})

    @app.route("/api/debug/restart", methods=["POST"])
    def restart_bot():
        loader = ScriptLoader()
        client = _get_bot_client()
        loaded = list(Config.loaded_modules.keys())
        for name in loaded:
            loader.unload_script(name)
        reloaded = 0
        for name in loaded:
            result = loader.load_script(name, client)
            if result["success"]:
                reloaded += 1
        Config.add_log(f"Restart: {reloaded}/{len(loaded)} scripts reloaded")
        return jsonify({"success": True, "reloaded": reloaded, "total": len(loaded)})

    @app.route("/api/debug/unload_all", methods=["POST"])
    def unload_all_scripts():
        loader = ScriptLoader()
        loaded = list(Config.loaded_modules.keys())
        count = 0
        for name in loaded:
            result = loader.unload_script(name)
            if result["success"]:
                count += 1
        Config.add_log(f"All scripts unloaded: {count}/{len(loaded)}")
        return jsonify({"success": True, "unloaded": count, "total": len(loaded)})

    @app.route("/api/console/exec", methods=["POST"])
    def exec_command():
        data = request.get_json(silent=True) or {}
        code = data.get("code", "").strip()
        if not code:
            return jsonify({"success": False, "error": "Empty command"})

        allowed_commands = {
            "status": lambda: {
                "loaded": list(Config.loaded_modules.keys()),
                "scripts_count": len(ScriptLoader().get_available_scripts()),
                "bot_running": _get_bot_client() is not None,
            },
            "help": lambda: {
                "commands": ["status", "help", "loaded_list"],
                "description": "Available console commands",
            },
            "loaded_list": lambda: {
                "modules": [
                    {"name": name, "info": Config.loaded_modules_info.get(name, {})}
                    for name in Config.loaded_modules
                ]
            },
        }

        parts = code.split()
        cmd = parts[0].lower()

        if cmd in allowed_commands:
            try:
                result = allowed_commands[cmd]()
                return jsonify({"success": True, "output": result})
            except Exception as e:
                return jsonify({"success": False, "error": str(e)})
        else:
            return jsonify({
                "success": False,
                "error": f"Unknown command: {cmd}. Available: {', '.join(allowed_commands.keys())}",
            })

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"error": "Internal server error"}), 500

    return app
