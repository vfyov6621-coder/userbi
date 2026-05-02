"""TimeName - main module
Adds MSK time to profile name. Usage: .tn on / .tn off
"""

import os
import asyncio
from datetime import datetime

TASK_KEY = "time_name"


def _get_time() -> str:
    msk = datetime.utcnow().hour + 3
    if msk >= 24:
        msk -= 24
    return f"{msk:02d}:{datetime.utcnow().strftime('%M')}"


def register(client):
    from pyrogram import filters
    from pyrogram.enums import ParseMode
    from pyrogram.types import Message

    @client.on_message(filters.command("tn", prefixes=".") & filters.me)
    async def tn_handler(client, message: Message):
        args = message.text.split(maxsplit=1)
        action = (args[1] or "").strip().lower() if len(args) > 1 else ""

        if action == "off":
            if TASK_KEY in _tasks:
                _tasks[TASK_KEY].cancel()
                del _tasks[TASK_KEY]
            try:
                original = _original_name.get(message.from_user.id, "")
                if original:
                    await client.update_profile(first_name=original)
                    await message.edit_text("⏹ Время в нике выключено", parse_mode=ParseMode.HTML)
                else:
                    await message.edit_text("⏹ Выключено", parse_mode=ParseMode.HTML)
            except Exception as e:
                await message.edit_text(f"❌ Ошибка: {e}", parse_mode=ParseMode.HTML)
            return

        if action == "on" or action == "":
            if TASK_KEY in _tasks:
                await message.edit_text("⚠️ Уже включено", parse_mode=ParseMode.HTML)
                return

            me = await client.get_me()
            full = me.first_name or ""

            for sep in [" | ", " |", "| "]:
                if sep in full:
                    full = full.split(sep)[0].strip()

            _original_name[message.from_user.id] = full

            async def _loop():
                while True:
                    try:
                        name = f"{full} | {_get_time()}"
                        await client.update_profile(first_name=name)
                    except Exception:
                        pass
                    await asyncio.sleep(60)

            _tasks[TASK_KEY] = asyncio.create_task(_loop())

            name = f"{full} | {_get_time()}"
            await client.update_profile(first_name=name)
            await message.edit_text(
                f"✅ Время в нике включено\n\n<i>Оригинал: {full}</i>\n<b>{name}</b>",
                parse_mode=ParseMode.HTML,
            )
            return

        await message.edit_text(
            "<b>⏰ TimeName</b>\n\n"
            "<code>.tn on</code> — включить\n"
            "<code>.tn off</code> — выключить (вернёт оригинал)",
            parse_mode=ParseMode.HTML,
        )


_tasks = {}
_original_name = {}


def on_load():
    print("[TimeName] Loaded. Use .tn on / .tn off")


def on_unload():
    if TASK_KEY in _tasks:
        _tasks[TASK_KEY].cancel()
        del _tasks[TASK_KEY]
    print("[TimeName] Unloaded")
