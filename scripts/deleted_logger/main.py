"""
Deleted Logger - main module
Caches all messages and logs deleted ones. Provides web panel tab data.

Commands:
  .dl on   - enable monitoring
  .dl off  - disable monitoring
  .dl status - show status
  .dl clear - clear all logged data
"""

import os
import json
import asyncio
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")
MAX_MESSAGES_PER_CHAT = 500
MAX_CACHE_AGE_HOURS = 24

# Module-level state
_enabled = False
_cache = {}       # (chat_id, msg_id) -> message_data
_log = {}         # chat_id -> {title, type, messages: []}
_save_task = None
_cleanup_task = None


def _load_data():
    global _log
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                _log = json.load(f)
    except Exception:
        _log = {}


def _save_data():
    os.makedirs(SCRIPT_DIR, exist_ok=True)
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(_log, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def _cache_message(msg):
    """Cache a message for later deletion detection."""
    chat_id = str(msg.chat.id)
    msg_id = msg.id

    media_type = None
    if msg.photo:
        media_type = "photo"
    elif msg.video:
        media_type = "video"
    elif msg.document:
        media_type = "document"
    elif msg.audio:
        media_type = "audio"
    elif msg.voice:
        media_type = "voice"
    elif msg.video_note:
        media_type = "video_note"
    elif msg.sticker:
        media_type = "sticker"
    elif msg.animation:
        media_type = "animation"

    sender_name = ""
    sender_id = None
    if msg.from_user:
        sender_name = msg.from_user.first_name or ""
        if msg.from_user.last_name:
            sender_name += f" {msg.from_user.last_name}"
        if msg.from_user.username:
            sender_name += f" (@{msg.from_user.username})"
        sender_id = msg.from_user.id

    _cache[(chat_id, msg_id)] = {
        "text": msg.text or msg.caption or "",
        "sender_name": sender_name,
        "sender_id": sender_id,
        "chat_id": chat_id,
        "chat_title": msg.chat.title or msg.chat.first_name or "",
        "date": msg.date.isoformat() if msg.date else datetime.utcnow().isoformat(),
        "media_type": media_type,
        "has_media": media_type is not None,
    }


def _log_deleted(chat_id, msg_ids):
    """Log deleted messages by looking them up in cache."""
    chat_id_str = str(chat_id)
    logged = []

    for msg_id in msg_ids:
        key = (chat_id_str, msg_id)
        cached = _cache.pop(key, None)
        if not cached:
            continue

        # Get or create chat entry
        if chat_id_str not in _log:
            _log[chat_id_str] = {
                "title": cached.get("chat_title", "Unknown"),
                "type": "group" if cached.get("chat_id", "").startswith("-") else "private",
                "messages": [],
            }

        chat_data = _log[chat_id_str]
        # Keep chat title updated
        if cached.get("chat_title"):
            chat_data["title"] = cached["chat_title"]

        entry = {
            "id": msg_id,
            "text": cached["text"],
            "sender_name": cached.get("sender_name", ""),
            "sender_id": cached.get("sender_id"),
            "date": cached["date"],
            "deleted_at": datetime.utcnow().isoformat(),
            "has_media": cached.get("has_media", False),
            "media_type": cached.get("media_type"),
        }

        chat_data["messages"].insert(0, entry)
        logged.append(entry)

        # Limit messages per chat
        if len(chat_data["messages"]) > MAX_MESSAGES_PER_CHAT:
            chat_data["messages"] = chat_data["messages"][:MAX_MESSAGES_PER_CHAT]

    if logged:
        _save_data()

    return logged


def register(client):
    """Register all handlers."""
    from pyrogram import filters
    from pyrogram.enums import ParseMode
    from pyrogram.types import Message

    # ── Cache ALL incoming messages ───────────────────────────────
    @client.on_message(~filters.me & ~filters.service, group=-1)
    async def cache_handler(client, message: Message):
        if not _enabled:
            return
        try:
            _cache_message(message)
        except Exception:
            pass

    # ── Also cache own messages ───────────────────────────────────
    @client.on_message(filters.me & ~filters.command("dl", prefixes="."), group=-1)
    async def cache_own_handler(client, message: Message):
        if not _enabled:
            return
        try:
            _cache_message(message)
        except Exception:
            pass

    # ── Detect deleted messages ───────────────────────────────────
    @client.on_deleted_messages(group=-1)
    async def deleted_handler(client, messages):
        if not _enabled:
            return
        try:
            for msg in messages:
                _log_deleted(msg.chat.id, [msg.id])
        except Exception:
            pass

    @client.on_user_status(group=-1)
    async def _noop(client, user, status):
        pass  # workaround for some pyrofork versions

    # ── .dl command ───────────────────────────────────────────────
    @client.on_message(filters.command("dl", prefixes=".") & filters.me)
    async def dl_handler(client, message: Message):
        global _enabled, _save_task, _cleanup_task
        args = message.text.split(maxsplit=1)
        action = (args[1] or "").strip().lower() if len(args) > 1 else ""

        if action == "on":
            if _enabled:
                await message.edit_text("🗑 Логгер уже включён", parse_mode=ParseMode.HTML)
                return
            _enabled = True
            _load_data()
            _save_task = asyncio.create_task(_periodic_save())
            _cleanup_task = asyncio.create_task(_periodic_cleanup())
            await message.edit_text(
                "✅ Логгер удалённых сообщений <b>включён</b>\n\n"
                "🗑 Все входящие сообщения кешируются.\n"
                "При удалении — сохраняются во вкладку веб-панели.\n\n"
                "<code>.dl off</code> — выключить\n"
                "<code>.dl status</code> — статус\n"
                "<code>.dl clear</code> — очистить лог",
                parse_mode=ParseMode.HTML,
            )
            return

        if action == "off":
            _enabled = False
            if _save_task:
                _save_task.cancel()
                _save_task = None
            if _cleanup_task:
                _cleanup_task.cancel()
                _cleanup_task = None
            _cache.clear()
            await message.edit_text("⏹ Логгер <b>выключен</b>", parse_mode=ParseMode.HTML)
            return

        if action == "clear":
            global _log
            _log = {}
            _save_data()
            await message.edit_text("✅ Лог очищен", parse_mode=ParseMode.HTML)
            return

        if action == "status":
            total_msgs = sum(len(c.get("messages", [])) for c in _log.values())
            total_chats = len(_log)
            cached = len(_cache)
            status = "Включён" if _enabled else "Выключен"
            await message.edit_text(
                f"🗑 <b>Deleted Logger</b>\n\n"
                f"Статус: <b>{status}</b>\n"
                f"Чатов: <b>{total_chats}</b>\n"
                f"Удалённых сообщений: <b>{total_msgs}</b>\n"
                f"Кеш: <b>{cached}</b> сообщений",
                parse_mode=ParseMode.HTML,
            )
            return

        await message.edit_text(
            "<b>🗑 Deleted Logger</b>\n\n"
            "<code>.dl on</code> — включить\n"
            "<code>.dl off</code> — выключить\n"
            "<code>.dl status</code> — статус\n"
            "<code>.dl clear</code> — очистить лог",
            parse_mode=ParseMode.HTML,
        )


async def _periodic_save():
    """Periodically save data to disk."""
    while True:
        try:
            await asyncio.sleep(30)
            if _enabled:
                _save_data()
        except asyncio.CancelledError:
            break
        except Exception:
            pass


async def _periodic_cleanup():
    """Periodically clean old cache entries."""
    while True:
        try:
            await asyncio.sleep(300)  # every 5 min
            if _enabled:
                now = datetime.utcnow()
                to_remove = []
                for key, data in _cache.items():
                    try:
                        msg_date = datetime.fromisoformat(data["date"])
                        age = (now - msg_date).total_seconds() / 3600
                        if age > MAX_CACHE_AGE_HOURS:
                            to_remove.append(key)
                    except Exception:
                        to_remove.append(key)
                for key in to_remove:
                    _cache.pop(key, None)
        except asyncio.CancelledError:
            break
        except Exception:
            pass


def get_tab_data(tab_id, **params):
    """Return data for the web panel tab."""
    action = params.get("action", "list_chats")
    chat_id = params.get("chat_id")

    if action == "list_chats":
        chats = []
        for cid, data in _log.items():
            msg_count = len(data.get("messages", []))
            if msg_count > 0:
                chats.append({
                    "id": cid,
                    "title": data.get("title", "Unknown"),
                    "type": data.get("type", "group"),
                    "count": msg_count,
                    "last_deleted": data["messages"][0].get("deleted_at", "") if data["messages"] else "",
                })
        chats.sort(key=lambda x: x.get("last_deleted", ""), reverse=True)
        return {"success": True, "chats": chats, "enabled": _enabled}

    if action == "chat_messages" and chat_id:
        chat_data = _log.get(str(chat_id))
        if not chat_data:
            return {"success": True, "chat": None, "messages": []}
        return {
            "success": True,
            "chat": {
                "id": chat_id,
                "title": chat_data.get("title", ""),
                "type": chat_data.get("type", ""),
                "count": len(chat_data.get("messages", [])),
            },
            "messages": chat_data.get("messages", []),
        }

    return {"success": True, "chats": [], "enabled": _enabled}


def on_load():
    print("[DeletedLogger] Loaded. .dl on/off/status/clear")


def on_unload():
    global _enabled, _save_task, _cleanup_task
    _enabled = False
    if _save_task:
        _save_task.cancel()
        _save_task = None
    if _cleanup_task:
        _cleanup_task.cancel()
        _cleanup_task = None
    _cache.clear()
    _save_data()
    print("[DeletedLogger] Unloaded")
