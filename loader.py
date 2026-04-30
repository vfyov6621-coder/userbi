import os
import sys
import ast
import importlib
import traceback
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

from config import Config

logger = logging.getLogger("userbot.loader")


class ScriptLoader:
    """
    Dynamic .py script loader for the userbot.

    Two directories:
      - scripts/            built-in scripts (tracked in git, read-only)
      - scripts_custom/     user-created scripts (gitignored, can be saved/deleted)
    Custom scripts override built-in ones by filename.
    """

    def __init__(self):
        self.builtin_dir = Config.SCRIPTS_DIR
        self.custom_dir = Config.CUSTOM_SCRIPTS_DIR
        os.makedirs(self.builtin_dir, exist_ok=True)
        os.makedirs(self.custom_dir, exist_ok=True)

    # ── helpers ──────────────────────────────────────────────────────────

    def _scan_dir(self, directory: str) -> list:
        """Return .py filenames (excluding _) from a directory."""
        if not os.path.exists(directory):
            return []
        return sorted(
            f for f in os.listdir(directory)
            if f.endswith(".py") and not f.startswith("_")
        )

    def _resolve_filepath(self, filename: str) -> Optional[Tuple[str, bool]]:
        """
        Find the real path for *filename*.

        Returns (absolute_path, is_custom) or None if not found anywhere.
        Priority: scripts_custom/ > scripts/
        """
        custom_path = os.path.join(self.custom_dir, filename)
        if os.path.exists(custom_path):
            return custom_path, True
        builtin_path = os.path.join(self.builtin_dir, filename)
        if os.path.exists(builtin_path):
            return builtin_path, False
        return None

    # ── public API ───────────────────────────────────────────────────────

    def get_available_scripts(self) -> list:
        """Return deduplicated list of .py files (custom overrides builtin)."""
        builtin = set(self._scan_dir(self.builtin_dir))
        custom = set(self._scan_dir(self.custom_dir))
        all_files = builtin | custom
        return sorted(all_files)

    def is_custom_script(self, filename: str) -> bool:
        """Return True if the script lives in scripts_custom/."""
        custom_path = os.path.join(self.custom_dir, filename)
        return os.path.exists(custom_path)

    def is_builtin_script(self, filename: str) -> bool:
        """Return True if a built-in (tracked) script exists with this name."""
        builtin_path = os.path.join(self.builtin_dir, filename)
        return os.path.exists(builtin_path)

    def get_script_info(self, filename: str) -> Optional[Dict[str, Any]]:
        resolved = self._resolve_filepath(filename)
        if resolved is None:
            return None

        filepath, is_custom = resolved

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                source = f.read()

            tree = ast.parse(source)
            docstring = ast.get_docstring(tree) or ""

            info: Dict[str, Any] = {"name": filename.replace(".py", "")}

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

            size_bytes = os.path.getsize(filepath)
            if size_bytes < 1024:
                info["size"] = f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                info["size"] = f"{size_bytes / 1024:.1f} KB"
            else:
                info["size"] = f"{size_bytes / (1024 * 1024):.1f} MB"

            mtime = os.path.getmtime(filepath)
            info["modified"] = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
            info["lines"] = len(source.splitlines())
            info["is_custom"] = is_custom

            return info
        except Exception as e:
            logger.error(f"Error reading script info {filename}: {e}")
            return None

    def get_script_source(self, filename: str) -> Optional[str]:
        resolved = self._resolve_filepath(filename)
        if resolved is None:
            return None
        filepath, _ = resolved
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return None

    def load_script(self, filename: str, client=None) -> Dict[str, Any]:
        resolved = self._resolve_filepath(filename)
        if resolved is None:
            return {"success": False, "error": f"File {filename} not found"}

        filepath, is_custom = resolved

        if filename in Config.loaded_modules:
            return {"success": False, "error": f"Script {filename} already loaded"}

        try:
            file_dir = os.path.dirname(filepath)
            if file_dir not in sys.path:
                sys.path.insert(0, file_dir)

            module_name = f"userbot_scripts_{filename.replace('.py', '')}"

            if module_name in sys.modules:
                del sys.modules[module_name]

            spec = importlib.util.spec_from_file_location(module_name, filepath)
            if spec is None or spec.loader is None:
                return {"success": False, "error": "Could not create spec for module"}

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            if hasattr(module, "register") and client is not None:
                try:
                    module.register(client)
                    logger.info(f"Script {filename}: register() called")
                except Exception as e:
                    logger.warning(f"Script {filename}: error in register(): {e}")

            if hasattr(module, "on_load"):
                try:
                    module.on_load()
                    logger.info(f"Script {filename}: on_load() called")
                except Exception as e:
                    logger.warning(f"Script {filename}: error in on_load(): {e}")

            Config.loaded_modules[filename] = module
            info = self.get_script_info(filename) or {}
            Config.loaded_modules_info[filename] = info

            logger.info(f"Script {filename} loaded successfully ({'custom' if is_custom else 'builtin'})")
            return {"success": True, "info": info}

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(f"Error loading script {filename}: {error_msg}")
            traceback.print_exc()
            return {"success": False, "error": error_msg}

    def unload_script(self, filename: str) -> Dict[str, Any]:
        if filename not in Config.loaded_modules:
            return {"success": False, "error": f"Script {filename} not loaded"}

        try:
            module = Config.loaded_modules[filename]

            if hasattr(module, "on_unload"):
                try:
                    module.on_unload()
                    logger.info(f"Script {filename}: on_unload() called")
                except Exception as e:
                    logger.warning(f"Script {filename}: error in on_unload(): {e}")

            module_name = f"userbot_scripts_{filename.replace('.py', '')}"
            if module_name in sys.modules:
                del sys.modules[module_name]

            del Config.loaded_modules[filename]
            if filename in Config.loaded_modules_info:
                del Config.loaded_modules_info[filename]

            logger.info(f"Script {filename} unloaded")
            return {"success": True}

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(f"Error unloading script {filename}: {error_msg}")
            return {"success": False, "error": error_msg}

    def delete_script(self, filename: str) -> Dict[str, Any]:
        """
        Delete a script.  Only custom scripts can be deleted;
        built-in scripts are protected.
        """
        custom_path = os.path.join(self.custom_dir, filename)
        if os.path.exists(custom_path):
            if filename in Config.loaded_modules:
                self.unload_script(filename)
            try:
                os.remove(custom_path)
                logger.info(f"Custom script {filename} deleted")
                return {"success": True}
            except Exception as e:
                return {"success": False, "error": str(e)}

        # check if it exists as builtin
        if self.is_builtin_script(filename):
            return {"success": False, "error": f"Cannot delete built-in script {filename}"}

        return {"success": False, "error": f"File {filename} not found"}

    def save_script(self, filename: str, source: str) -> Dict[str, Any]:
        """
        Save a script.  Always saves into scripts_custom/ so that
        built-in scripts are never overwritten and .gitignore needs
        no further changes.
        """
        if not filename.endswith(".py"):
            return {"success": False, "error": "File must have .py extension"}
        filepath = os.path.join(self.custom_dir, filename)
        try:
            compile(source, filename, "exec")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(source)
            logger.info(f"Script {filename} saved to scripts_custom/ ({len(source)} chars)")
            return {"success": True}
        except SyntaxError as e:
            return {"success": False, "error": f"Syntax error (line {e.lineno}): {e.msg}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def create_backup(self) -> Dict[str, Any]:
        os.makedirs(Config.BACKUPS_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(Config.BACKUPS_DIR, f"backup_{timestamp}")
        os.makedirs(backup_dir, exist_ok=True)

        saved_count = 0
        import shutil

        # backup custom scripts
        for f in self._scan_dir(self.custom_dir):
            src = os.path.join(self.custom_dir, f)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(backup_dir, f"custom_{f}"))
                saved_count += 1

        # backup builtin scripts
        for f in self._scan_dir(self.builtin_dir):
            src = os.path.join(self.builtin_dir, f)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(backup_dir, f"builtin_{f}"))
                saved_count += 1

        for f in os.listdir(Config.BASE_DIR):
            if f.endswith(".session"):
                shutil.copy2(
                    os.path.join(Config.BASE_DIR, f),
                    os.path.join(backup_dir, f)
                )
                saved_count += 1

        Config.add_log(f"Backup created: backup_{timestamp} ({saved_count} files)")
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
