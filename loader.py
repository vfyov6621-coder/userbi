import os
import sys
import json
import ast
import importlib
import traceback
import shutil
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List

from config import Config

logger = logging.getLogger("userbot.loader")


class ScriptLoader:
    """
    Folder-based script loader.

    Structure per script:
      scripts/<script_id>/
        meta.json      — metadata (name, version, addons, tabs, ...)
        main.py        — main script code
        addons/        — optional addon scripts
          lang_ru.py
          ...

    Custom override: scripts_custom/<script_id>/meta.json takes priority.
    Legacy flat .py files in scripts/ are still supported.
    """

    def __init__(self):
        self.builtin_dir = Config.SCRIPTS_DIR
        self.custom_dir = Config.CUSTOM_SCRIPTS_DIR
        os.makedirs(self.builtin_dir, exist_ok=True)
        os.makedirs(self.custom_dir, exist_ok=True)

    # ── Directory scanning ────────────────────────────────────────────

    def _scan_script_dirs(self, directory: str) -> List[str]:
        """Return folder names that contain meta.json (script folders)."""
        result = []
        if not os.path.exists(directory):
            return result
        for name in sorted(os.listdir(directory)):
            folder = os.path.join(directory, name)
            meta = os.path.join(folder, "meta.json")
            if os.path.isdir(folder) and os.path.exists(meta):
                result.append(name)
        return result

    def _scan_legacy_files(self, directory: str) -> List[str]:
        """Return flat .py files (legacy scripts)."""
        if not os.path.exists(directory):
            return []
        return sorted(
            f for f in os.listdir(directory)
            if f.endswith(".py") and not f.startswith("_")
        )

    def get_available_scripts(self) -> List[str]:
        """
        Return all script IDs.
        Folder scripts + legacy .py names (without .py).
        Custom folders override builtin folders.
        """
        builtin_folders = set(self._scan_script_dirs(self.builtin_dir))
        custom_folders = set(self._scan_script_dirs(self.custom_dir))
        all_folders = builtin_folders | custom_folders

        # Also scan for legacy .py files (not in any folder)
        builtin_files = set(self._scan_legacy_files(self.builtin_dir))
        custom_files = set(self._scan_legacy_files(self.custom_dir))
        all_files = builtin_files | custom_files

        # Filter out .py files that are part of a folder (main.py etc.)
        folder_main_files = set()
        for folder_name in all_folders:
            folder_main_files.add(f"{folder_name}/")
        # Strip folder names from flat file list
        for folder_name in all_folders:
            all_files.discard(folder_name)

        ids = set()
        for name in all_folders:
            ids.add(name)
        for fname in all_files:
            ids.add(fname.replace(".py", ""))

        return sorted(ids)

    def is_folder_script(self, script_id: str) -> bool:
        """Check if a script is a folder-based script."""
        for d in [self.custom_dir, self.builtin_dir]:
            if os.path.exists(os.path.join(d, script_id, "meta.json")):
                return True
        return False

    def is_legacy_script(self, script_id: str) -> bool:
        """Check if a script is a legacy flat .py file."""
        fname = script_id if script_id.endswith(".py") else f"{script_id}.py"
        for d in [self.custom_dir, self.builtin_dir]:
            if os.path.exists(os.path.join(d, fname)):
                return True
        return False

    def is_custom_script(self, script_id: str) -> bool:
        """Check if a script lives in scripts_custom/."""
        for d in [self.custom_dir]:
            if os.path.exists(os.path.join(d, script_id, "meta.json")):
                return True
            fname = script_id if script_id.endswith(".py") else f"{script_id}.py"
            if os.path.exists(os.path.join(d, fname)):
                return True
        return False

    # ── Meta / Info ───────────────────────────────────────────────────

    def _resolve_script_dir(self, script_id: str) -> Optional[Tuple[str, bool]]:
        """Find the script directory. Returns (path, is_custom) or None."""
        custom_path = os.path.join(self.custom_dir, script_id)
        if os.path.exists(os.path.join(custom_path, "meta.json")):
            return custom_path, True
        builtin_path = os.path.join(self.builtin_dir, script_id)
        if os.path.exists(os.path.join(builtin_path, "meta.json")):
            return builtin_path, False
        return None

    def _resolve_legacy_file(self, script_id: str) -> Optional[Tuple[str, bool]]:
        """Find a legacy .py file. Returns (path, is_custom) or None."""
        fname = script_id if script_id.endswith(".py") else f"{script_id}.py"
        custom_path = os.path.join(self.custom_dir, fname)
        if os.path.exists(custom_path):
            return custom_path, True
        builtin_path = os.path.join(self.builtin_dir, fname)
        if os.path.exists(builtin_path):
            return builtin_path, False
        return None

    def get_script_meta(self, script_id: str) -> Optional[Dict[str, Any]]:
        """Read meta.json for a folder script."""
        resolved = self._resolve_script_dir(script_id)
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

    def get_addon_states(self, script_id: str) -> Dict[str, bool]:
        """Get addon enabled/disabled states from config."""
        return Config.get_addon_states(script_id)

    def set_addon_state(self, script_id: str, addon_file: str, enabled: bool) -> bool:
        """Set addon enabled/disabled state."""
        return Config.set_addon_state(script_id, addon_file, enabled)

    def get_script_info(self, script_id: str) -> Optional[Dict[str, Any]]:
        """Get full info for a script (meta + stats)."""
        # Folder script
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
            # Get main.py size
            main_path = os.path.join(meta["_dir"], "main.py")
            if os.path.exists(main_path):
                info["size"] = self._format_size(os.path.getsize(main_path))
                info["lines"] = self._count_lines(main_path)
                info["modified"] = datetime.fromtimestamp(
                    os.path.getmtime(main_path)
                ).strftime("%Y-%m-%d %H:%M:%S")
            return info

        # Legacy script
        resolved = self._resolve_legacy_file(script_id)
        if resolved is None:
            return None
        filepath, is_custom = resolved
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                source = f.read()
            tree = ast.parse(source)
            docstring = ast.get_docstring(tree) or ""
            info: Dict[str, Any] = {
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
                "size": self._format_size(os.path.getsize(filepath)),
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

    # ── Loading / Unloading ───────────────────────────────────────────

    def load_script(self, script_id: str, client=None) -> Dict[str, Any]:
        """Load a script (folder or legacy)."""
        # Check already loaded
        load_key = self._get_load_key(script_id)
        if load_key in Config.loaded_modules:
            return {"success": False, "error": f"Script {script_id} already loaded"}

        # Folder script
        if self.is_folder_script(script_id):
            return self._load_folder_script(script_id, client)
        # Legacy script
        elif self.is_legacy_script(script_id):
            return self._load_legacy_script(script_id, client)
        else:
            return {"success": False, "error": f"Script {script_id} not found"}

    def _get_load_key(self, script_id: str) -> str:
        """Get the key used in loaded_modules dict."""
        if self.is_folder_script(script_id):
            return script_id
        else:
            return script_id if script_id.endswith(".py") else f"{script_id}.py"

    def _load_folder_script(self, script_id: str, client=None) -> Dict[str, Any]:
        """Load a folder-based script: main.py + enabled addons."""
        resolved = self._resolve_script_dir(script_id)
        if resolved is None:
            return {"success": False, "error": f"Script {script_id} not found"}
        dirpath, is_custom = resolved

        meta = self.get_script_meta(script_id)
        if not meta:
            return {"success": False, "error": f"Cannot read meta.json for {script_id}"}

        main_path = os.path.join(dirpath, "main.py")
        if not os.path.exists(main_path):
            return {"success": False, "error": f"main.py not found in {script_id}"}

        try:
            module_name = f"zaya_{script_id}"
            if module_name in sys.modules:
                del sys.modules[module_name]

            spec = importlib.util.spec_from_file_location(module_name, main_path)
            if spec is None or spec.loader is None:
                return {"success": False, "error": "Cannot create spec"}

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Call register() for main module
            if hasattr(module, "register") and client is not None:
                module.register(client)
                logger.info(f"[{script_id}] register() called")

            if hasattr(module, "on_load"):
                module.on_load()

            Config.loaded_modules[script_id] = module
            Config.loaded_modules_info[script_id] = self.get_script_info(script_id) or {}

            # Load enabled addons
            addon_states = self.get_addon_states(script_id)
            loaded_addons = []
            for addon in meta.get("addons", []):
                addon_file = addon.get("file", "")
                addon_default = addon.get("enabled", True)
                is_enabled = addon_states.get(addon_file, addon_default)

                if not is_enabled:
                    continue

                addon_result = self._load_addon(script_id, dirpath, addon_file, client)
                if addon_result["success"]:
                    loaded_addons.append(addon_file)

            logger.info(f"[{script_id}] loaded (addons: {loaded_addons})")
            return {
                "success": True,
                "info": meta,
                "addons_loaded": loaded_addons,
            }

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(f"Error loading {script_id}: {error_msg}")
            traceback.print_exc()
            return {"success": False, "error": error_msg}

    def _load_addon(self, script_id: str, dirpath: str, addon_file: str, client=None) -> Dict[str, Any]:
        """Load a single addon module."""
        addon_path = os.path.join(dirpath, addon_file)
        if not os.path.exists(addon_path):
            return {"success": False, "error": f"Addon {addon_file} not found"}

        try:
            addon_module_name = f"zaya_{script_id}_{addon_file.replace('/', '_').replace('.py', '')}"
            if addon_module_name in sys.modules:
                del sys.modules[addon_module_name]

            spec = importlib.util.spec_from_file_location(addon_module_name, addon_path)
            if spec is None or spec.loader is None:
                return {"success": False, "error": "Cannot create addon spec"}

            module = importlib.util.module_from_spec(spec)
            sys.modules[addon_module_name] = module
            spec.loader.exec_module(module)

            if hasattr(module, "register") and client is not None:
                module.register(client)

            if hasattr(module, "on_load"):
                module.on_load()

            # Track addon in config
            Config.loaded_addons.setdefault(script_id, {})[addon_file] = module
            logger.info(f"[{script_id}/{addon_file}] addon loaded")
            return {"success": True}

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(f"Error loading addon {script_id}/{addon_file}: {error_msg}")
            return {"success": False, "error": error_msg}

    def _load_legacy_script(self, script_id: str, client=None) -> Dict[str, Any]:
        """Load a legacy flat .py script."""
        resolved = self._resolve_legacy_file(script_id)
        if resolved is None:
            return {"success": False, "error": f"Script {script_id} not found"}
        filepath, is_custom = resolved
        filename = os.path.basename(filepath)

        if filename in Config.loaded_modules:
            return {"success": False, "error": f"Script {filename} already loaded"}

        try:
            module_name = f"zaya_legacy_{filename.replace('.py', '')}"
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

    def unload_script(self, script_id: str) -> Dict[str, Any]:
        """Unload a script and all its addons."""
        load_key = self._get_load_key(script_id)

        if load_key not in Config.loaded_modules:
            # Try script_id directly (for folder scripts)
            if script_id not in Config.loaded_modules:
                return {"success": False, "error": f"Script {script_id} not loaded"}

        actual_key = load_key if load_key in Config.loaded_modules else script_id
        module = Config.loaded_modules[actual_key]

        try:
            # Unload addons first
            addons = Config.loaded_addons.get(actual_key, {})
            for addon_file, addon_module in addons.items():
                if hasattr(addon_module, "on_unload"):
                    addon_module.on_unload()
                # Remove from sys.modules
                addon_mod_name = f"zaya_{actual_key}_{addon_file.replace('/', '_').replace('.py', '')}"
                sys.modules.pop(addon_mod_name, None)
            Config.loaded_addons.pop(actual_key, None)

            # Unload main module
            if hasattr(module, "on_unload"):
                module.on_unload()

            mod_name = f"zaya_{actual_key}" if not actual_key.endswith(".py") else f"zaya_legacy_{actual_key.replace('.py', '')}"
            sys.modules.pop(mod_name, None)

            del Config.loaded_modules[actual_key]
            Config.loaded_modules_info.pop(actual_key, None)

            logger.info(f"[{actual_key}] unloaded")
            return {"success": True}

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(f"Error unloading {script_id}: {error_msg}")
            return {"success": False, "error": error_msg}

    # ── Auto-start ────────────────────────────────────────────────────

    def auto_load_all(self, client=None) -> Dict[str, Any]:
        """Load all scripts listed in auto_start.json."""
        scripts = Config.get_auto_start()
        loaded, failed = [], []
        for item in scripts:
            result = self.load_script(item, client)
            if result["success"]:
                loaded.append(item)
            else:
                failed.append({"file": item, "error": result.get("error", "?")})
        return {"success": True, "loaded": loaded, "failed": failed, "total": len(scripts)}

    # ── Tabs system ───────────────────────────────────────────────────

    def get_available_tabs(self) -> List[Dict[str, Any]]:
        """Get all tabs from loaded folder scripts."""
        tabs = []
        for script_id, module in Config.loaded_modules.items():
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

    def get_tab_data(self, tab_id: str, **params) -> Any:
        """Call get_tab_data() on the owning script module."""
        for script_id, module in Config.loaded_modules.items():
            if hasattr(module, "get_tab_data"):
                try:
                    result = module.get_tab_data(tab_id, **params)
                    if result is not None:
                        return result
                except Exception as e:
                    logger.error(f"Error getting tab data from {script_id}: {e}")
        return {"success": False, "error": "Tab not found"}

    # ── Source / Save / Delete ─────────────────────────────────────────

    def get_script_source(self, script_id: str, subpath: str = "main.py") -> Optional[str]:
        """Get source code of main.py or an addon."""
        if self.is_folder_script(script_id):
            resolved = self._resolve_script_dir(script_id)
            if resolved is None:
                return None
            filepath = os.path.join(resolved[0], subpath)
            if os.path.exists(filepath):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        return f.read()
                except Exception:
                    return None
        else:
            resolved = self._resolve_legacy_file(script_id)
            if resolved is None:
                return None
            try:
                with open(resolved[0], "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                return None
        return None

    def save_script(self, script_id: str, source: str, subpath: str = "main.py") -> Dict[str, Any]:
        """Save source code. Always to scripts_custom/."""
        if self.is_folder_script(script_id):
            # Save to scripts_custom/<script_id>/<subpath>
            target_dir = os.path.join(self.custom_dir, script_id)
            os.makedirs(target_dir, exist_ok=True)
            # Also copy meta.json if not present in custom
            if not os.path.exists(os.path.join(target_dir, "meta.json")):
                builtin_meta = os.path.join(self.builtin_dir, script_id, "meta.json")
                if os.path.exists(builtin_meta):
                    import shutil
                    shutil.copy2(builtin_meta, os.path.join(target_dir, "meta.json"))
            filepath = os.path.join(target_dir, subpath)
        else:
            # Save as legacy .py in scripts_custom/
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

    def delete_script(self, script_id: str) -> Dict[str, Any]:
        """Delete a custom script. Built-in scripts cannot be deleted."""
        if self.is_folder_script(script_id):
            custom_dir = os.path.join(self.custom_dir, script_id)
            if os.path.exists(custom_dir):
                if script_id in Config.loaded_modules:
                    self.unload_script(script_id)
                try:
                    shutil.rmtree(custom_dir)
                    logger.info(f"Deleted custom script folder: {script_id}")
                    return {"success": True}
                except Exception as e:
                    return {"success": False, "error": str(e)}
            # Check builtin
            builtin_dir = os.path.join(self.builtin_dir, script_id)
            if os.path.exists(builtin_dir):
                return {"success": False, "error": f"Cannot delete built-in script {script_id}"}
            return {"success": False, "error": f"Script {script_id} not found"}
        else:
            fname = script_id if script_id.endswith(".py") else f"{script_id}.py"
            custom_path = os.path.join(self.custom_dir, fname)
            if os.path.exists(custom_path):
                load_key = fname
                if load_key in Config.loaded_modules:
                    self.unload_script(script_id)
                try:
                    os.remove(custom_path)
                    logger.info(f"Deleted legacy script: {fname}")
                    return {"success": True}
                except Exception as e:
                    return {"success": False, "error": str(e)}
            return {"success": False, "error": f"Script {script_id} not found or is built-in"}

    # ── Backup ────────────────────────────────────────────────────────

    def create_backup(self) -> Dict[str, Any]:
        os.makedirs(Config.BACKUPS_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(Config.BACKUPS_DIR, f"backup_{timestamp}")
        os.makedirs(backup_dir, exist_ok=True)

        saved_count = 0
        # Backup custom scripts (folders + files)
        if os.path.exists(self.custom_dir):
            for item in os.listdir(self.custom_dir):
                src = os.path.join(self.custom_dir, item)
                if os.path.isdir(src):
                    dst = os.path.join(backup_dir, f"custom_{item}")
                    shutil.copytree(src, dst)
                    saved_count += 1
                elif os.path.isfile(src):
                    shutil.copy2(src, os.path.join(backup_dir, f"custom_{item}"))
                    saved_count += 1

        # Backup builtin scripts (folders)
        if os.path.exists(self.builtin_dir):
            for item in os.listdir(self.builtin_dir):
                src = os.path.join(self.builtin_dir, item)
                if os.path.isdir(src):
                    dst = os.path.join(backup_dir, f"builtin_{item}")
                    shutil.copytree(src, dst)
                    saved_count += 1
                elif item.endswith(".py") and not item.startswith("_"):
                    shutil.copy2(src, os.path.join(backup_dir, f"builtin_{item}"))
                    saved_count += 1

        # Backup session files
        for f in os.listdir(Config.BASE_DIR):
            if f.endswith(".session"):
                shutil.copy2(os.path.join(Config.BASE_DIR, f), os.path.join(backup_dir, f))

        Config.add_log(f"Backup created: backup_{timestamp} ({saved_count} items)")
        return {
            "success": True,
            "backup_name": f"backup_{timestamp}",
            "files_count": saved_count,
            "timestamp": timestamp,
        }

    def get_backups(self) -> list:
        backups = []
        if os.path.exists(Config.BACKUPS_DIR):
            for d in sorted(os.listdir(Config.BACKUPS_DIR), reverse=True):
                backup_path = os.path.join(Config.BACKUPS_DIR, d)
                if os.path.isdir(backup_path):
                    file_count = len([f for f in os.listdir(backup_path) if not f.startswith(".")])
                    mtime = os.path.getmtime(backup_path)
                    backups.append({
                        "name": d,
                        "files": file_count,
                        "date": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    })
        return backups

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"

    @staticmethod
    def _count_lines(filepath: str) -> int:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return sum(1 for _ in f)
        except Exception:
            return 0
