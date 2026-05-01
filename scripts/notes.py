"""
Name: Notes
Version: 1.0
Author: UserBot
Description: Quick notes in Telegram. .note save <name> <text>, .note get <name>, .note list, .note del <name>
  Also: .note set — save from reply, .n <name> — shortcut for .note get
"""

import os
import json

NOTES_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts_custom",
    "notes.json",
)


def _load() -> dict:
    try:
        if os.path.exists(NOTES_FILE):
            with open(NOTES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save(data: dict):
    os.makedirs(os.path.dirname(NOTES_FILE), exist_ok=True)
    with open(NOTES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def register(client):
    from pyrogram import filters
    from pyrogram.enums import ParseMode
    from pyrogram.types import Message

    @client.on_message(filters.command("note", prefixes=".") & filters.me)
    async def note_handler(client, message: Message):
        args = message.text.split(maxsplit=2)
        if len(args) < 2:
            await message.edit_text(
                "<b>📝 Заметки</b>\n\n"
                "<code>.note save &lt;имя&gt; &lt;текст&gt;</code>\n"
                "<code>.note set &lt;имя&gt;</code> (ответ на соо)\n"
                "<code>.note get &lt;имя&gt;</code>\n"
                "<code>.note list</code>\n"
                "<code>.note del &lt;имя&gt;</code>\n\n"
                "<code>.n &lt;имя&gt;</code> — быстрый вызов",
                parse_mode=ParseMode.HTML,
            )
            return

        action = args[1].lower()

        # ── .note list ─────────────────────────────────────────────
        if action == "list":
            notes = _load()
            if not notes:
                await message.edit_text(
                    "📝 Заметок нет.\n\n<code>.note save имя текст</code>",
                    parse_mode=ParseMode.HTML,
                )
                return
            lines = "\n".join(
                f"  {i}. <code>{k}</code>" for i, k in enumerate(sorted(notes.keys()), 1)
            )
            await message.edit_text(
                f"📝 <b>Заметки ({len(notes)}):</b>\n\n{lines}",
                parse_mode=ParseMode.HTML,
            )
            return

        # ── .note del ──────────────────────────────────────────────
        if action == "del":
            if len(args) < 3:
                await message.edit_text("❌ <code>.note del &lt;имя&gt;</code>", parse_mode=ParseMode.HTML)
                return
            name = args[2].strip()
            notes = _load()
            if name in notes:
                del notes[name]
                _save(notes)
                await message.edit_text(f"✅ Заметка <b>{name}</b> удалена", parse_mode=ParseMode.HTML)
            else:
                await message.edit_text(f"❌ Заметка <b>{name}</b> не найдена", parse_mode=ParseMode.HTML)
            return

        # ── .note get ──────────────────────────────────────────────
        if action == "get":
            if len(args) < 3:
                await message.edit_text("❌ <code>.note get &lt;имя&gt;</code>", parse_mode=ParseMode.HTML)
                return
            name = args[2].strip()
            notes = _load()
            if name in notes:
                text = notes[name]
                await message.edit_text(
                    f"📝 <b>{name}:</b>\n\n{text}",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await message.edit_text(f"❌ Заметка <b>{name}</b> не найдена", parse_mode=ParseMode.HTML)
            return

        # ── .note set <name> (reply) ──────────────────────────────
        if action == "set":
            if len(args) < 3:
                await message.edit_text("❌ <code>.note set &lt;имя&gt;</code> (ответ на соо)", parse_mode=ParseMode.HTML)
                return
            name = args[2].strip()
            reply = message.reply_to_message
            if not reply:
                await message.edit_text("❌ Ответьте на сообщение", parse_mode=ParseMode.HTML)
                return
            text = reply.text or reply.caption or ""
            if not text:
                await message.edit_text("❌ Нет текста в ответе", parse_mode=ParseMode.HTML)
                return
            notes = _load()
            notes[name] = text
            _save(notes)
            await message.edit_text(f"✅ Заметка <b>{name}</b> сохранена", parse_mode=ParseMode.HTML)
            return

        # ── .note save <name> <text> ──────────────────────────────
        if action == "save":
            if len(args) < 3:
                await message.edit_text("❌ <code>.note save &lt;имя&gt; &lt;текст&gt;</code>", parse_mode=ParseMode.HTML)
                return
            rest = args[2].strip()
            parts = rest.split(maxsplit=1)
            name = parts[0]
            text = parts[1] if len(parts) > 1 else ""
            if not text:
                await message.edit_text("❌ Укажите текст", parse_mode=ParseMode.HTML)
                return
            notes = _load()
            notes[name] = text
            _save(notes)
            await message.edit_text(f"✅ Заметка <b>{name}</b> сохранена", parse_mode=ParseMode.HTML)
            return

        await message.edit_text("❌ Неизвестное действие. .note для справки", parse_mode=ParseMode.HTML)

    # ── shortcut: .n <name> ───────────────────────────────────────
    @client.on_message(filters.command("n", prefixes=".") & filters.me)
    async def n_shortcut(client, message: Message):
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            return
        name = args[1].strip()
        notes = _load()
        if name in notes:
            await message.edit_text(
                f"📝 <b>{name}:</b>\n\n{notes[name]}",
                parse_mode=ParseMode.HTML,
            )
        else:
            await message.edit_text(f"❌ Заметка <b>{name}</b> не найдена", parse_mode=ParseMode.HTML)


def on_load():
    print("[Notes] Loaded. .note save/get/list/del/set, .n <name>")


def on_unload():
    print("[Notes] Unloaded")
