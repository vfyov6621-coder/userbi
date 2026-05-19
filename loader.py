"""
ScriptLoader — модульная загрузка скриптов для sandusr.
"""

import os
import sys
import json
import ast
import importlib
import traceback
import shutil
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

from config import Config

logger = logging.getLogger("userbot.loader")


class ScriptLoader:
    def __init__(self):
        self.builtin_dir = Config.SCRIPTS_DIR
        self.custom_dir = Config.CUSTOM_SCRIPTS_DIR
        os.makedirs(self.builtin_dir, exist_ok=True)
        os.makedirs(self.custom_dir, exist_ok=True)

    # ═══════════════════════════════════════════════════════════════════
    #  Scanning
    # ═══════════════════════════════════════════════════════════════════

    def _scan_folders(self, directory):
        result = []
        if not os.path.exists(directory):
            return result
        for name in sorted(os.listdir(directory)):
            folder = os.path.join(directory, name)
            if os.path.isdir(folder) and os.path.exists(os.path.join(folder, "meta.json")):
                result.append(name)
        return result

    def _scan_legacy(self, directory):
        if not os.path.exists(directory):
            return []
        return sorted(
            f for f in os.listdir(directory)
            if f.endswith(".py") and not f.startswith("_")
        )

    def get_available_scripts(self):
        builtin_folders = set(self._scan_folders(self.builtin_dir))
        custom_folders = set(self._scan_folders(self.custom_dir))
        all_folders = builtin_folders | custom_folders
        builtin_files = set(self._scan_legacy(self.builtin_dir))
        custom_files = set(self._scan_legacy(self.custom_dir))
        all_files = (builtin_files | custom_files) - {f"{n}/" for n in all_folders}
        ids = set()
        for name in all_folders:
            ids.add(name)
        for fname in all_files:
            ids.add(fname.replace(".py", ""))
        return sorted(ids)

    def is_folder_script(self, script_id):
        for d in [self.custom_dir, self.builtin_dir]:
            if os.path.exists(os.path.join(d, script_id, "meta.json")):
                return True
        return False

    def is_legacy_script(self, script_id):
        fname = script_id if script_id.endswith(".py") else f"{script_id}.py"
        for d in [self.custom_dir, self.builtin_dir]:
            if os.path.exists(os.path.join(d, fname)):
                return True
        return False

    # ═══════════════════════════════════════════════════════════════════
    #  Resolution
    # ═══════════════════════════════════════════════════════════════════

    def _resolve_dir(self, script_id):
        custom = os.path.join(self.custom_dir, script_id)
        if os.path.exists(os.path.join(custom, "meta.json")):
            return custom, True
        builtin = os.path.join(self.builtin_dir, script_id)
        if os.path.exists(os.path.join(builtin, "meta.json")):
            return builtin, False
        return None

    def _resolve_file(self, script_id):
        fname = script_id if script_id.endswith(".py") else f"{script_id}.py"
        custom = os.path.join(self.custom_dir, fname)
        if os.path.exists(custom):
            return custom, True
        builtin = os.path.join(self.builtin_dir, fname)
        if os.path.exists(builtin):
            return builtin, False
        return None

    def _load_key(self, script_id):
        if self.is_folder_script(script_id):
            return script_id
        return script_id if script_id.endswith(".py") else f"{script_id}.py"

    # ═══════════════════════════════════════════════════════════════════
    #  Meta & Info
    # ═══════════════════════════════════════════════════════════════════

    def get_script_meta(self, script_id):
        resolved = self._resolve_dir(script_id)
        if resolved is None:
            return None
        dirpath, is_custom = resolved
        try:
            with open(os.path.join(dirpath, "meta.json"), "r", encoding="utf-8") as f:
                meta = json.load(f)
            meta["_is_custom"] = is_custom
            meta["_dir"] = dirpath
            return meta
        except Exception:
            return None

    def get_addon_states(self, script_id):
        return Config.get_addon_states(script_id)

    def set_addon_state(self, script_id, addon_file, enabled):
        return Config.set_addon_state(script_id, addon_file, enabled)

    def get_script_info(self, script_id):
        if self.is_folder_script(script_id):
            meta = self.get_script_meta(script_id)
            if not meta:
                return None
            info = {
                "id": script_id,
                "name": meta.get("name", script_id),
                "version": meta.get("version", "?"),
                "author": meta.get("author", "?"),
                "description": meta.get("description", ""),
                "command": meta.get("command", ""),
                "is_folder": True,
                "is_custom": meta.get("_is_custom", False),
                "addons": meta.get("addons", []),
                "tabs": meta.get("tabs", []),
                "loaded": script_id in Config.loaded_modules,
            }
            main_path = os.path.join(meta["_dir"], "main.py")
            if os.path.exists(main_path):
                info["size"] = self._fmt_size(os.path.getsize(main_path))
                info["lines"] = self._count_lines(main_path)
                info["modified"] = datetime.fromtimestamp(
                    os.path.getmtime(main_path)
                ).strftime("%Y-%m-%d %H:%M:%S")
            return info

        resolved = self._resolve_file(script_id)
        if resolved is None:
            return None
        filepath, is_custom = resolved
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                source = f.read()
            tree = ast.parse(source)
            docstring = ast.get_docstring(tree) or ""
            info = {
                "id": script_id,
                "name": script_id,
                "version": "?",
                "author": "?",
                "description": "",
                "command": "",
                "is_folder": False,
                "is_custom": is_custom,
                "addons": [],
                "tabs": [],
                "loaded": f"{script_id}.py" in Config.loaded_modules,
                "size": self._fmt_size(os.path.getsize(filepath)),
                "lines": len(source.splitlines()),
                "modified": datetime.fromtimestamp(
                    os.path.getmtime(filepath)
                ).strftime("%Y-%m-%d %H:%M:%S"),
            }
            for line in docstring.split("\n"):
                line = line.strip()
                if line.startswith("Name:"):
                    info["name"] = line.split(":", 1)[1].strip()
                elif line.startswith("Version:"):
                    info["version"] = line.split(":", 1)[1].strip()
                elif line.startswith("Author:"):
                    info["author"] = line.split(":", 1)[1].strip()
                elif line.startswith("Description:"):
                    info["description"] = line.split(":", 1)[1].strip()
            return info
        except Exception:
            return None

    # ═══════════════════════════════════════════════════════════════════
    #  Loading
    # ═══════════════════════════════════════════════════════════════════

    def load_script(self, script_id, client=None):
        load_key = self._load_key(script_id)
        if load_key in Config.loaded_modules:
            return {"success": False, "error": f"{script_id} already loaded"}
        if self.is_folder_script(script_id):
            return self._load_folder(script_id, client)
        elif self.is_legacy_script(script_id):
            return self._load_legacy(script_id, client)
        return {"success": False, "error": f"{script_id} not found"}

    def _load_folder(self, script_id, client=None):
        resolved = self._resolve_dir(script_id)
        if resolved is None:
            return {"success": False, "error": f"{script_id} not found"}
        dirpath, is_custom = resolved
        meta = self.get_script_meta(script_id)
        if not meta:
            return {"success": False, "error": "Cannot read meta.json"}
        main_path = os.path.join(dirpath, "main.py")
        if not os.path.exists(main_path):
            return {"success": False, "error": "main.py not found"}

        try:
            module_name = "sandusr_" + script_id
            if module_name in sys.modules:
                del sys.modules[module_name]

            spec = importlib.util.spec_from_file_location(module_name, main_path)
            if spec is None or spec.loader is None:
                return {"success": False, "error": "Cannot create spec"}

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            if hasattr(module, "register") and client is not None:
                module.register(client)
                logger.info(f"[{script_id}] register() called")

            if hasattr(module, "on_load"):
                module.on_load()

            Config.loaded_modules[script_id] = module
            Config.loaded_modules_info[script_id] = self.get_script_info(script_id) or {}

            # Load addons
            addon_states = Config.get_addon_states(script_id)
            loaded_addons = []
            for addon in meta.get("addons", []):
                addon_file = addon.get("file", "")
                addon_default = addon.get("enabled", True)
                is_enabled = addon_states.get(addon_file, addon_default)
                if not is_enabled:
                    continue
                r = self._load_addon(script_id, dirpath, addon_file, client)
                if r["success"]:
                    loaded_addons.append(addon_file)

            logger.info(f"[{script_id}] loaded (addons: {loaded_addons})")
            return {"success": True, "info": meta, "addons_loaded": loaded_addons}

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(f"Error loading {script_id}: {error_msg}")
            traceback.print_exc()
            return {"success": False, "error": error_msg}

    def _load_addon(self, script_id, dirpath, addon_file, client=None):
        addon_path = os.path.join(dirpath, addon_file)
        if not os.path.exists(addon_path):
            return {"success": False, "error": f"{addon_file} not found"}
        try:
            addon_name = "sandusr_" + script_id + "_" + addon_file.replace("/", "_").replace(".py", "")
            if addon_name in sys.modules:
                del sys.modules[addon_name]

            spec = importlib.util.spec_from_file_location(addon_name, addon_path)
            if spec is None or spec.loader is None:
                return {"success": False, "error": "Cannot create addon spec"}

            module = importlib.util.module_from_spec(spec)
            sys.modules[addon_name] = module
            spec.loader.exec_module(module)

            if hasattr(module, "register") and client is not None:
                module.register(client)
            if hasattr(module, "on_load"):
                module.on_load()

            Config.loaded_addons.setdefault(script_id, {})[addon_file] = module
            logger.info(f"[{script_id}/{addon_file}] addon loaded")
            return {"success": True}
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(f"Error loading addon {script_id}/{addon_file}: {error_msg}")
            return {"success": False, "error": error_msg}

    def _load_legacy(self, script_id, client=None):
        resolved = self._resolve_file(script_id)
        if resolved is None:
            return {"success": False, "error": f"{script_id} not found"}
        filepath, is_custom = resolved
        filename = os.path.basename(filepath)
        if filename in Config.loaded_modules:
            return {"success": False, "error": f"{filename} already loaded"}
        try:
            module_name = "sandusr_legacy_" + filename.replace(".py", "")
            if module_name in sys.modules:
                del sys.modules[module_name]

            spec = importlib.util.spec_from_file_location(module_name, filepath)
            if spec is None or spec.loader is None:
                return {"success": False, "error": "Cannot create spec"}

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            if hasattr(module, "register") and client is not None:
                module.register(client)
            if hasattr(module, "on_load"):
                module.on_load()

            Config.loaded_modules[filename] = module
            Config.loaded_modules_info[filename] = self.get_script_info(script_id) or {}
            logger.info(f"[{filename}] legacy loaded")
            return {"success": True}
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(f"Error loading {filename}: {error_msg}")
            traceback.print_exc()
            return {"success": False, "error": error_msg}

    # ═══════════════════════════════════════════════════════════════════
    #  Unloading
    # ═══════════════════════════════════════════════════════════════════

    def unload_script(self, script_id):
        load_key = self._load_key(script_id)
        actual_key = load_key if load_key in Config.loaded_modules else script_id
        if actual_key not in Config.loaded_modules:
            if script_id not in Config.loaded_modules:
                return {"success": False, "error": f"{script_id} not loaded"}
            actual_key = script_id

        module = Config.loaded_modules[actual_key]
        try:
            # Unload addons first
            addons = Config.loaded_addons.get(actual_key, {})
            for addon_file, addon_module in addons.items():
                if hasattr(addon_module, "on_unload"):
                    addon_module.on_unload()
                addon_name = "sandusr_" + actual_key + "_" + addon_file.replace("/", "_").replace(".py", "")
                sys.modules.pop(addon_name, None)
            Config.loaded_addons.pop(actual_key, None)

            # Unload main module
            if hasattr(module, "on_unload"):
                module.on_unload()
            if not actual_key.endswith(".py"):
                mod_name = "sandusr_" + actual_key
            else:
                mod_name = "sandusr_legacy_" + actual_key.replace(".py", "")
            sys.modules.pop(mod_name, None)

            del Config.loaded_modules[actual_key]
            Config.loaded_modules_info.pop(actual_key, None)
            logger.info(f"[{actual_key}] unloaded")
            return {"success": True}
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(f"Error unloading {script_id}: {error_msg}")
            return {"success": False, "error": error_msg}

    # ═══════════════════════════════════════════════════════════════════
    #  Auto-start
    # ═══════════════════════════════════════════════════════════════════

    def auto_load_all(self, client=None):
        scripts = Config.get_auto_start()

        # Если auto_start.json нет (None) — грузим ВСЕ доступные скрипты
        if scripts is None:
            scripts = self.get_available_scripts()
            logger.info(f"No auto_start.json found, loading all {len(scripts)} scripts")

        loaded, failed = [], []
        for item in scripts:
            result = self.load_script(item, client)
            if result["success"]:
                loaded.append(item)
            else:
                failed.append({"file": item, "error": result.get("error", "?")})
        return {"success": True, "loaded": loaded, "failed": failed, "total": len(scripts)}

    # ═══════════════════════════════════════════════════════════════════
    #  Tabs (for web panel)
    # ═══════════════════════════════════════════════════════════════════

    def get_available_tabs(self):
        tabs = []
        for script_id in list(Config.loaded_modules.keys()):
            if not self.is_folder_script(script_id):
                continue
            meta = self.get_script_meta(script_id)
            if meta and meta.get("tabs"):
                for tab in meta["tabs"]:
                    tabs.append({
                        "id": tab["id"],
                        "name": tab.get("name", tab["id"]),
                        "icon": tab.get("icon", ""),
                        "script_id": script_id,
                    })
        return tabs

    def get_tab_data(self, tab_id, **params):
        for script_id, module in Config.loaded_modules.items():
            if hasattr(module, "get_tab_data"):
                try:
                    result = module.get_tab_data(tab_id, **params)
                    if result is not None:
                        return result
                except Exception as e:
                    logger.error(f"Tab data error from {script_id}: {e}")
        return {"success": False, "error": "Tab not found"}

    # ═══════════════════════════════════════════════════════════════════
    #  Source read/write
    # ═══════════════════════════════════════════════════════════════════

    def get_script_source(self, script_id, subpath="main.py"):
        if self.is_folder_script(script_id):
            resolved = self._resolve_dir(script_id)
            if resolved is None:
                return None
            filepath = os.path.join(resolved[0], subpath)
        else:
            resolved = self._resolve_file(script_id)
            if resolved is None:
                return None
            filepath = resolved[0]
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                pass
        return None

    def save_script(self, script_id, source, subpath="main.py"):
        if self.is_folder_script(script_id):
            target_dir = os.path.join(self.custom_dir, script_id)
            os.makedirs(target_dir, exist_ok=True)
            if not os.path.exists(os.path.join(target_dir, "meta.json")):
                builtin_meta = os.path.join(self.builtin_dir, script_id, "meta.json")
                if os.path.exists(builtin_meta):
                    shutil.copy2(builtin_meta, os.path.join(target_dir, "meta.json"))
            filepath = os.path.join(target_dir, subpath)
        else:
            fname = script_id if script_id.endswith(".py") else f"{script_id}.py"
            filepath = os.path.join(self.custom_dir, fname)
        try:
            if source:
                compile(source, subpath, "exec")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(source)
            logger.info(f"Saved {filepath}")
            return {"success": True}
        except SyntaxError as e:
            return {"success": False, "error": f"Syntax error (line {e.lineno}): {e.msg}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_script(self, script_id):
        if self.is_folder_script(script_id):
            custom_dir = os.path.join(self.custom_dir, script_id)
            if os.path.exists(custom_dir):
                if script_id in Config.loaded_modules:
                    self.unload_script(script_id)
                shutil.rmtree(custom_dir)
                return {"success": True}
            return {"success": False, "error": f"Cannot delete built-in {script_id}"}
        else:
            fname = script_id if script_id.endswith(".py") else f"{script_id}.py"
            custom_path = os.path.join(self.custom_dir, fname)
            if os.path.exists(custom_path):
                if fname in Config.loaded_modules:
                    self.unload_script(script_id)
                os.remove(custom_path)
                return {"success": True}
            return {"success": False, "error": f"{script_id} not found or built-in"}

    # ═══════════════════════════════════════════════════════════════════
    #  Backups
    # ═══════════════════════════════════════════════════════════════════

    def create_backup(self):
        os.makedirs(Config.BACKUPS_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(Config.BACKUPS_DIR, f"backup_{timestamp}")
        os.makedirs(backup_dir, exist_ok=True)
        saved = 0
        for base in [self.custom_dir, self.builtin_dir]:
            if os.path.exists(base):
                for item in os.listdir(base):
                    src = os.path.join(base, item)
                    prefix = "custom_" if base == self.custom_dir else "builtin_"
                    dst = os.path.join(backup_dir, prefix + item)
                    if os.path.isdir(src):
                        shutil.copytree(src, dst)
                    elif os.path.isfile(src):
                        shutil.copy2(src, dst)
                    saved += 1
        Config.add_log(f"Backup created: backup_{timestamp}")
        return {"success": True, "backup_name": f"backup_{timestamp}", "files": saved}

    def get_backups(self):
        backups = []
        if os.path.exists(Config.BACKUPS_DIR):
            for d in sorted(os.listdir(Config.BACKUPS_DIR), reverse=True):
                p = os.path.join(Config.BACKUPS_DIR, d)
                if os.path.isdir(p):
                    backups.append({
                        "name": d,
                        "files": len([f for f in os.listdir(p) if not f.startswith(".")]),
                        "date": datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M:%S"),
                    })
        return backups

    # ═══════════════════════════════════════════════════════════════════
    #  Utilities
    # ═══════════════════════════════════════════════════════════════════

    @staticmethod
    def _fmt_size(n):
        if n < 1024:
            return f"{n} B"
        elif n < 1024 * 1024:
            return f"{n / 1024:.1f} KB"
        return f"{n / (1024 * 1024):.1f} MB"

    @staticmethod
    def _count_lines(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return sum(1 for _ in f)
        except Exception:
            return 0
