"""
ScriptLoader — модульная загрузка скриптов для sandusr.
Переписан с нуля. Простой, надёжный, с понятным логированием.
"""

import os
import sys
import json
import ast
import importlib.util
import traceback
import shutil
import logging
from datetime import datetime

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

    def _find_script_dir(self, script_id):
        """Найти директорию скрипта (custom приоритетнее builtin)."""
        for d in [self.custom_dir, self.builtin_dir]:
            p = os.path.join(d, script_id)
            if os.path.isdir(p) and os.path.exists(os.path.join(p, "meta.json")):
                return p, d == self.custom_dir
        return None, None

    def _find_script_file(self, script_id):
        """Найти .py файл скрипта (legacy формат)."""
        fname = script_id if script_id.endswith(".py") else f"{script_id}.py"
        for d in [self.custom_dir, self.builtin_dir]:
            p = os.path.join(d, fname)
            if os.path.isfile(p):
                return p, d == self.custom_dir
        return None, None

    def get_available_scripts(self):
        """Список всех доступных script_id (без дубликатов)."""
        ids = set()
        # Папки с meta.json
        for d in [self.builtin_dir, self.custom_dir]:
            if not os.path.exists(d):
                continue
            for name in os.listdir(d):
                if os.path.isdir(os.path.join(d, name)):
                    if os.path.exists(os.path.join(d, name, "meta.json")):
                        ids.add(name)
        # Legacy .py файлы (только если нет папки с таким же именем)
        for d in [self.builtin_dir, self.custom_dir]:
            if not os.path.exists(d):
                continue
            for name in os.listdir(d):
                if name.endswith(".py") and not name.startswith("_"):
                    sid = name[:-3]  # убираем .py
                    if sid not in ids:
                        ids.add(sid)
        return sorted(ids)

    def is_folder_script(self, script_id):
        dirpath, _ = self._find_script_dir(script_id)
        return dirpath is not None

    def is_legacy_script(self, script_id):
        filepath, _ = self._find_script_file(script_id)
        return filepath is not None

    # ═══════════════════════════════════════════════════════════════════
    #  Meta & Info
    # ═══════════════════════════════════════════════════════════════════

    def _read_meta(self, script_id):
        """Прочитать meta.json. Возвращает (meta_dict, dirpath) или (None, None)."""
        dirpath, _ = self._find_script_dir(script_id)
        if dirpath is None:
            return None, None
        try:
            with open(os.path.join(dirpath, "meta.json"), "r", encoding="utf-8") as f:
                return json.load(f), dirpath
        except Exception:
            return None, None

    def get_script_meta(self, script_id):
        meta, dirpath = self._read_meta(script_id)
        if meta is None:
            return None
        _, is_custom = self._find_script_dir(script_id)
        meta["_is_custom"] = is_custom
        meta["_dir"] = dirpath
        return meta

    def get_addon_states(self, script_id):
        return Config.get_addon_states(script_id)

    def set_addon_state(self, script_id, addon_file, enabled):
        return Config.set_addon_state(script_id, addon_file, enabled)

    def get_script_info(self, script_id):
        """Полная информация о скрипте."""
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

        # Legacy script
        filepath, is_custom = self._find_script_file(script_id)
        if filepath is None:
            return None
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
                "loaded": script_id in Config.loaded_modules,
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
    #  Module import helper
    # ═══════════════════════════════════════════════════════════════════

    @staticmethod
    def _import_module(module_name, filepath):
        """Импортировать .py файл как модуль. Возвращает module или raises."""
        # Очищаем старый модуль из sys.modules
        if module_name in sys.modules:
            del sys.modules[module_name]

        spec = importlib.util.spec_from_file_location(module_name, filepath)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"spec_from_file_location вернул None для {filepath}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def _call_register(module, client):
        """Вызвать module.register(client) если функция существует."""
        if hasattr(module, "register") and callable(module.register):
            module.register(client)
            return True
        return False

    @staticmethod
    def _call_lifecycle(module, func_name):
        """Безопасно вызвать on_load/on_unload."""
        fn = getattr(module, func_name, None)
        if fn and callable(fn):
            try:
                fn()
            except Exception as e:
                print(f"  [!] {func_name}() error: {e}")

    # ═══════════════════════════════════════════════════════════════════
    #  Loading
    # ═══════════════════════════════════════════════════════════════════

    def load_script(self, script_id, client=None):
        """Загрузить скрипт по ID. Возвращает dict с результатом."""
        if script_id in Config.loaded_modules:
            return {"success": False, "error": f"{script_id} уже загружен"}

        if self.is_folder_script(script_id):
            return self._load_folder_script(script_id, client)
        elif self.is_legacy_script(script_id):
            return self._load_legacy_script(script_id, client)
        else:
            return {"success": False, "error": f"Скрипт '{script_id}' не найден"}

    def _load_folder_script(self, script_id, client=None):
        meta, dirpath = self._read_meta(script_id)
        if meta is None:
            return {"success": False, "error": f"{script_id}: meta.json не найден или ошибка"}

        main_path = os.path.join(dirpath, "main.py")
        if not os.path.exists(main_path):
            return {"success": False, "error": f"{script_id}: main.py не найден"}

        try:
            print(f"[loader] Загрузка: {script_id} ...")

            # Импортируем main.py
            module_name = f"sandusr_{script_id}"
            module = self._import_module(module_name, main_path)

            # Регистрируем хендлеры
            registered = False
            if client is not None:
                registered = self._call_register(module, client)
            if registered:
                print(f"[loader]   -> register() вызван")

            # on_load
            self._call_lifecycle(module, "on_load")

            # Сохраняем в Config
            Config.loaded_modules[script_id] = module
            Config.loaded_modules_info[script_id] = self.get_script_info(script_id) or {}

            # Загружаем аддоны
            addons_loaded = self._load_addons(script_id, dirpath, meta, client)

            cmd = meta.get("command", "")
            print(f"[loader]   OK: {script_id} {cmd} (аддоны: {addons_loaded or 'нет'})")
            return {"success": True, "info": meta, "addons_loaded": addons_loaded}

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            print(f"[loader]   ОШИБКА: {script_id} — {error_msg}")
            traceback.print_exc()
            # Убираем модуль из sys.modules если загрузка провалилась
            mod_name = f"sandusr_{script_id}"
            sys.modules.pop(mod_name, None)
            return {"success": False, "error": error_msg}

    def _load_legacy_script(self, script_id, client=None):
        filepath, is_custom = self._find_script_file(script_id)
        if filepath is None:
            return {"success": False, "error": f"Скрипт '{script_id}' не найден"}

        fname = os.path.basename(filepath)
        if fname in Config.loaded_modules:
            return {"success": False, "error": f"{fname} уже загружен"}

        try:
            print(f"[loader] Загрузка (legacy): {script_id} ...")

            module_name = f"sandusr_legacy_{script_id}"
            module = self._import_module(module_name, filepath)

            if client is not None:
                self._call_register(module, client)

            self._call_lifecycle(module, "on_load")

            Config.loaded_modules[fname] = module
            Config.loaded_modules_info[fname] = self.get_script_info(script_id) or {}

            print(f"[loader]   OK: {fname}")
            return {"success": True}

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            print(f"[loader]   ОШИБКА: {script_id} — {error_msg}")
            traceback.print_exc()
            mod_name = f"sandusr_legacy_{script_id}"
            sys.modules.pop(mod_name, None)
            return {"success": False, "error": error_msg}

    def _load_addons(self, script_id, dirpath, meta, client=None):
        """Загрузить включённые аддоны скрипта. Возвращает список загруженных файлов."""
        addons = meta.get("addons", [])
        if not addons:
            return []

        addon_states = Config.get_addon_states(script_id)
        loaded = []

        for addon in addons:
            addon_file = addon.get("file", "")
            if not addon_file:
                continue

            # Проверяем включён ли аддон
            is_enabled = addon_states.get(addon_file, addon.get("enabled", True))
            if not is_enabled:
                continue

            addon_path = os.path.join(dirpath, addon_file)
            if not os.path.exists(addon_path):
                print(f"[loader]   Аддон не найден: {addon_file}")
                continue

            try:
                addon_name = f"sandusr_{script_id}_addon_{addon_file.replace('/', '_').replace('.py', '')}"
                module = self._import_module(addon_name, addon_path)

                if client is not None:
                    self._call_register(module, client)

                self._call_lifecycle(module, "on_load")

                Config.loaded_addons.setdefault(script_id, {})[addon_file] = module
                loaded.append(addon_file)
                print(f"[loader]     Аддон OK: {addon_file}")

            except Exception as e:
                print(f"[loader]     Аддон ОШИБКА: {addon_file} — {e}")

        return loaded

    # ═══════════════════════════════════════════════════════════════════
    #  Unloading
    # ═══════════════════════════════════════════════════════════════════

    def unload_script(self, script_id):
        """Выгрузить скрипт. Ищет по script_id и по имени файла."""
        # Ищем ключ в loaded_modules
        key = None
        if script_id in Config.loaded_modules:
            key = script_id
        else:
            fname = script_id if script_id.endswith(".py") else f"{script_id}.py"
            if fname in Config.loaded_modules:
                key = fname

        if key is None:
            return {"success": False, "error": f"{script_id} не загружен"}

        module = Config.loaded_modules[key]
        try:
            # 1. Выгружаем аддоны
            addons = Config.loaded_addons.pop(key, {})
            for addon_file, addon_module in addons.items():
                self._call_lifecycle(addon_module, "on_unload")
                addon_name = f"sandusr_{key}_addon_{addon_file.replace('/', '_').replace('.py', '')}"
                sys.modules.pop(addon_name, None)

            # 2. on_unload главного модуля
            self._call_lifecycle(module, "on_unload")

            # 3. Убираем из sys.modules
            if key.endswith(".py"):
                mod_name = f"sandusr_legacy_{key.replace('.py', '')}"
            else:
                mod_name = f"sandusr_{key}"
            sys.modules.pop(mod_name, None)

            # 4. Убираем из Config
            del Config.loaded_modules[key]
            Config.loaded_modules_info.pop(key, None)

            print(f"[loader] Выгружен: {key}")
            return {"success": True}

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            print(f"[loader] Ошибка выгрузки {key}: {error_msg}")
            return {"success": False, "error": error_msg}

    # ═══════════════════════════════════════════════════════════════════
    #  Auto-start
    # ═══════════════════════════════════════════════════════════════════

    def auto_load_all(self, client=None):
        """Загрузить все скрипты при старте."""
        scripts = Config.get_auto_start()

        if scripts is None:
            # Нет auto_start.json — грузим ВСЕ доступные
            scripts = self.get_available_scripts()
            print(f"[loader] auto_start.json не найден, загружаем все {len(scripts)} скриптов")
        else:
            print(f"[loader] auto_start.json: {len(scripts)} скриптов")

        loaded = []
        failed = []

        for script_id in scripts:
            result = self.load_script(script_id, client)
            if result["success"]:
                loaded.append(script_id)
            else:
                failed.append({"file": script_id, "error": result.get("error", "?")})

        print(f"[loader] Итого: {len(loaded)}/{len(scripts)} загружено")
        if failed:
            print(f"[loader] Не загружены:")
            for f in failed:
                print(f"  - {f['file']}: {f['error']}")

        return {"success": True, "loaded": loaded, "failed": failed, "total": len(scripts)}

    # ═══════════════════════════════════════════════════════════════════
    #  Tabs (для веб-панели)
    # ═══════════════════════════════════════════════════════════════════

    def get_available_tabs(self):
        tabs = []
        for script_id in list(Config.loaded_modules.keys()):
            meta, _ = self._read_meta(script_id)
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
            dirpath, _ = self._find_script_dir(script_id)
            if dirpath is None:
                return None
            filepath = os.path.join(dirpath, subpath)
        else:
            filepath, _ = self._find_script_file(script_id)
            if filepath is None:
                return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
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
            return {"success": False, "error": f"Нельзя удалить встроенный {script_id}"}
        else:
            fname = script_id if script_id.endswith(".py") else f"{script_id}.py"
            custom_path = os.path.join(self.custom_dir, fname)
            if os.path.exists(custom_path):
                if fname in Config.loaded_modules:
                    self.unload_script(script_id)
                os.remove(custom_path)
                return {"success": True}
            return {"success": False, "error": f"{script_id} не найден или встроенный"}

    # ═══════════════════════════════════════════════════════════════════
    #  Backups
    # ═══════════════════════════════════════════════════════════════════

    def create_backup(self):
        os.makedirs(Config.BACKUPS_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(Config.BACKUPS_DIR, f"backup_{timestamp}")
        os.makedirs(backup_dir, exist_ok=True)
        saved = 0
        for base, prefix in [(self.custom_dir, "custom_"), (self.builtin_dir, "builtin_")]:
            if not os.path.exists(base):
                continue
            for item in os.listdir(base):
                if item.startswith("."):
                    continue
                src = os.path.join(base, item)
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
