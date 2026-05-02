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

    # ── Logs ────────────────────────────────────────────────────────────

    @app.route("/api/logs", methods=["GET"])
    def get_logs():
        return jsonify({"success": True, "logs": Config.get_logs()})

    @app.route("/api/logs/clear", methods=["POST"])
    def clear_logs():
        Config.clear_logs()
        return jsonify({"success": True})

    # ── Scripts ─────────────────────────────────────────────────────────

    @app.route("/api/scripts", methods=["GET"])
    def list_scripts():
        loader = ScriptLoader()
        scripts = []
        for sid in loader.get_available_scripts():
            info = loader.get_script_info(sid)
            if info:
                # Add addon enabled states
                if info.get("addons"):
                    addon_states = loader.get_addon_states(sid)
                    for addon in info["addons"]:
                        addon_file = addon.get("file", "")
                        addon["enabled"] = addon_states.get(addon_file, addon.get("enabled", True))
                scripts.append(info)
        return jsonify({"success": True, "scripts": scripts})

    @app.route("/api/scripts/<script_id>/source", methods=["GET"])
    def get_script_source(script_id):
        subpath = request.args.get("file", "main.py")
        loader = ScriptLoader()
        source = loader.get_script_source(script_id, subpath)
        if source is None:
            return jsonify({"success": False, "error": "File not found"}), 404
        return jsonify({
            "success": True,
            "script_id": script_id,
            "subpath": subpath,
            "source": source,
        })

    @app.route("/api/scripts/<script_id>/source", methods=["POST"])
    def save_script_source(script_id):
        data = request.get_json(silent=True) or {}
        subpath = data.get("file", "main.py")
        source = data.get("source", "")
        loader = ScriptLoader()
        result = loader.save_script(script_id, source, subpath)
        if result["success"]:
            Config.add_log(f"Script {script_id}/{subpath} saved via web panel")
        return jsonify(result)

    @app.route("/api/scripts/<script_id>/load", methods=["POST"])
    def load_script(script_id):
        loader = ScriptLoader()
        client = _get_bot_client()
        result = loader.load_script(script_id, client)
        if result["success"]:
            Config.add_log(f"Script {script_id} loaded via web panel")
        return jsonify(result)

    @app.route("/api/scripts/<script_id>/unload", methods=["POST"])
    def unload_script(script_id):
        loader = ScriptLoader()
        result = loader.unload_script(script_id)
        if result["success"]:
            Config.add_log(f"Script {script_id} unloaded via web panel")
        return jsonify(result)

    @app.route("/api/scripts/<script_id>/reload", methods=["POST"])
    def reload_script(script_id):
        loader = ScriptLoader()
        client = _get_bot_client()
        loader.unload_script(script_id)
        result = loader.load_script(script_id, client)
        if result["success"]:
            Config.add_log(f"Script {script_id} reloaded via web panel")
        return jsonify(result)

    @app.route("/api/scripts/<script_id>", methods=["DELETE"])
    def delete_script(script_id):
        loader = ScriptLoader()
        result = loader.delete_script(script_id)
        if result["success"]:
            Config.add_log(f"Script {script_id} deleted via web panel")
            Config.set_auto_start(script_id, False)
        return jsonify(result)

    # ── Auto-start ──────────────────────────────────────────────────────

    @app.route("/api/autostart", methods=["GET"])
    def get_autostart():
        return jsonify({"success": True, "scripts": Config.get_auto_start()})

    @app.route("/api/autostart/<script_id>", methods=["POST"])
    def toggle_autostart(script_id):
        data = request.get_json(silent=True) or {}
        enabled = bool(data.get("enabled", True))
        loader = ScriptLoader()
        # Verify script exists
        if not loader.get_script_info(script_id):
            return jsonify({"success": False, "error": f"Script {script_id} not found"}), 404
        ok = Config.set_auto_start(script_id, enabled)
        if ok:
            Config.add_log(f"Auto-start {'enabled' if enabled else 'disabled'} for {script_id}")
        return jsonify({"success": ok})

    # ── Addons ──────────────────────────────────────────────────────────

    @app.route("/api/scripts/<script_id>/addons/<addon_file>", methods=["POST"])
    def toggle_addon(script_id, addon_file):
        """Toggle an addon enabled/disabled."""
        data = request.get_json(silent=True) or {}
        enabled = bool(data.get("enabled", True))
        loader = ScriptLoader()
        ok = loader.set_addon_state(script_id, addon_file, enabled)
        if ok:
            Config.add_log(f"Addon {script_id}/{addon_file} {'enabled' if enabled else 'disabled'}")
            # Reload the script to apply addon changes
            client = _get_bot_client()
            loader.unload_script(script_id)
            result = loader.load_script(script_id, client)
            return jsonify({"success": result["success"], "reloaded": True})
        return jsonify({"success": False, "error": "Failed to save addon state"})

    # ── Tabs (dynamic from scripts) ────────────────────────────────────

    @app.route("/api/tabs", methods=["GET"])
    def get_tabs():
        """Get all available tabs from loaded scripts."""
        loader = ScriptLoader()
        tabs = loader.get_available_tabs()
        logger.info(f"Tabs requested: found {len(tabs)} tabs, loaded_modules={list(Config.loaded_modules.keys())}")
        return jsonify({"success": True, "tabs": tabs})

    @app.route("/api/tabs/<tab_id>", methods=["GET"])
    def get_tab_data(tab_id):
        """Get data for a specific tab."""
        loader = ScriptLoader()
        params = dict(request.args)
        result = loader.get_tab_data(tab_id, **params)
        return jsonify(result)

    # ── Debug ───────────────────────────────────────────────────────────

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

    # ── Console ─────────────────────────────────────────────────────────

    @app.route("/api/console/exec", methods=["POST"])
    def exec_command():
        data = request.get_json(silent=True) or {}
        code = data.get("code", "").strip()
        if not code:
            return jsonify({"success": False, "error": "Empty command"})

        allowed_commands = {
            "status": lambda: {
                "loaded": list(Config.loaded_modules.keys()),
                "addons": {k: list(v.keys()) for k, v in Config.loaded_addons.items()},
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
