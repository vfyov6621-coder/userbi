"""
Action Logger — логирование команд юзербота.
Отслеживает все "." команды. Если ни один скрипт не обработал команду
(сообщение не было изменено за 2 секунды) — заносит в лог.

Команды:
  .al        — последние 20 проблемных команд
  .al all    — все логи
  .al clear  — очистить логи

Как работает:
  Скрипт перехватывает все "." команды с высоким приоритетом (group=9999),
  ждёт 2 секунды, потом проверяет — изменилось ли сообщение.
  Если нет → значит ни один обработчик не сработал → логирует.
"""

import os
import json
import asyncio
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, "action_logs.json")
MAX_LOGS = 500


def _load_logs():
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_logs(logs):
    os.makedirs(SCRIPT_DIR, exist_ok=True)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs[-MAX_LOGS:], f, indent=2, ensure_ascii=False)


def _get_known_commands():
    """Собрать все зарегистрированные команды из загруженных скриптов."""
    from config import Config
    from loader import ScriptLoader

    known = {"mm", "mf", "lm", "al"}  # встроенные команды

    # Из загруженных скриптов
    for sid, info in Config.loaded_modules_info.items():
        cmd = info.get("command", "")
        if cmd.startswith("."):
            known.add(cmd.lstrip("."))
        elif cmd:
            known.add(cmd)

    # Из аддонов загруженных скриптов
    loader = ScriptLoader()
    for sid, addons in Config.loaded_addons.items():
        meta = loader.get_script_meta(sid)
        if meta and meta.get("addons"):
            for addon in meta["addons"]:
                addon_file = addon.get("file", "")
                if addon_file in addons:
                    acmd = addon.get("command", "")
                    if acmd.startswith("."):
                        known.add(acmd.lstrip("."))
                    elif acmd:
                        known.add(acmd)

    return known


def register(client):
    from pyrogram import filters
    from pyrogram.handlers import MessageHandler
    from pyrogram.enums import ParseMode
    from pyrogram.types import Message

    async def _watcher(client, message: Message):
        """Перехватывает все "." команды, проверяет обработку."""
        original_text = message.text or ""
        msg_id = message.id
        chat_id = message.chat.id

        # Ждём пока другие хендлеры отработают
        await asyncio.sleep(2)

        try:
            # Получаем актуальное состояние сообщения
            fresh = await client.get_messages(chat_id, msg_id)
            current_text = fresh.text or ""

            # Сообщение было отредактировано → хендлер сработал
            if current_text != original_text:
                return

            # Сообщение не изменено → ни один скрипт не обработал
            cmd = original_text.split()[0].lstrip(".")

            known = _get_known_commands()
            is_known = cmd in known

            # Сохраняем в лог
            logs = _load_logs()
            logs.append({
                "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "command": original_text.strip(),
                "chat_id": chat_id,
                "type": "known_broken" if is_known else "unknown",
                "known": is_known,
            })
            _save_logs(logs)

            status = "BROKEN" if is_known else "UNKNOWN"
            print(f"[ActionLogger] {status}: {original_text.strip()}")

        except Exception:
            # Сообщение удалено → хендлер сработал (например .np удаляет оригинал)
            pass

    # Регистрируем watcher с высоким group, чтобы он выполнялся ПОСЛЕ всех скриптов
    watcher_handler = MessageHandler(
        _watcher,
        filters.me & filters.regex(r"^\.") & ~filters.regex(r"^\.al\b"),
    )
    client.add_handler(watcher_handler, group=9999)

    # ── .al ────────────────────────────────────────────────────
    @client.on_message(filters.command("al", prefixes=".") & filters.me)
    async def al_handler(client, message: Message):
        args = message.text.split(maxsplit=1)
        action = args[1].strip().lower() if len(args) > 1 else ""

        if action == "clear":
            _save_logs([])
            await message.edit_text(
                "📋 <b>Action Logger</b>\n\n✅ Логи очищены",
                parse_mode=ParseMode.HTML,
            )
            return

        logs = _load_logs()

        if not logs:
            await message.edit_text(
                "📋 <b>Action Logger</b>\n\n"
                "✅ Все команды работают!\n"
                "Проблем пока не обнаружено.",
                parse_mode=ParseMode.HTML,
            )
            return

        if action == "all":
            show = logs
        else:
            show = logs[-20:]

        broken = sum(1 for l in logs if l.get("known"))
        unknown = sum(1 for l in logs if not l.get("known"))

        text = f"📋 <b>Action Logger</b>\n\n"
        text += f"⚠️ Нерабочих: <b>{broken}</b> | ❓ Неизвестных: <b>{unknown}</b>\n\n"

        for log in reversed(show):
            ts = log.get("timestamp", "?")
            cmd = log.get("command", "?")
            if log.get("known"):
                status = "⚠️"
                label = "не работает"
            else:
                status = "❓"
                label = "неизвестная"

            text += f"{status} <code>{cmd}</code> — {label} [{ts}]\n"

        if len(logs) > 20 and action != "all":
            text += f"\n...и ещё {len(logs) - 20}\n<code>.al all</code> — показать все"

        text += f"\n\n<code>.al clear</code> — очистить"

        await message.edit_text(text, parse_mode=ParseMode.HTML)


def on_load():
    print("[ActionLogger] Loaded. Monitoring commands for errors...")


def on_unload():
    print("[ActionLogger] Unloaded")
