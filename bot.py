import os
import json
import time
import logging
from pyrogram import Client, filters, idle
from pyrogram.enums import ParseMode
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from config import Config
from loader import ScriptLoader

logger = logging.getLogger("userbot.bot")

# Global reference to the client (needed for script register())
bot_client = None

BOT_NAME = "Zaya"
INFO_FILE = os.path.join(Config.CUSTOM_SCRIPTS_DIR, "bot_info.json")
PHOTO_FILE = os.path.join(Config.CUSTOM_SCRIPTS_DIR, "bot_photo.jpg")


# ═══════════════════════════════════════════════════════════════════════
#  .mm  —  built-in menu
# ═══════════════════════════════════════════════════════════════════════

def _load_info() -> dict:
    try:
        if os.path.exists(INFO_FILE):
            with open(INFO_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"name": BOT_NAME, "bio": "", "owner": "", "info": "Инфо не настроена."}


MM_KEYBOARD = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("📷 Фото", callback_data="mm_photo")],
        [InlineKeyboardButton("🏓 Пинг", callback_data="mm_ping")],
        [InlineKeyboardButton("ℹ️ Инфо", callback_data="mm_info")],
    ]
)


async def mm_command(client: Client, message: Message):
    """Show the main menu."""
    info = _load_info()
    name = info.get("name", BOT_NAME)
    bio = info.get("bio", "")

    text = f"🤖 <b>{name}</b>"
    if bio:
        text += f"\n<i>{bio}</i>"
    text += "\n\nВыберите действие:"

    await message.edit_text(text, reply_markup=MM_KEYBOARD, parse_mode=ParseMode.HTML)


async def mm_callback(client: Client, callback: CallbackQuery):
    """Handle inline keyboard presses from .mm menu."""
    data = callback.data

    # ── Photo ──────────────────────────────────────────────────────
    if data == "mm_photo":
        if os.path.exists(PHOTO_FILE):
            try:
                await callback.message.reply_photo(PHOTO_FILE, caption="📷 Фото")
                await callback.answer("Фото отправлено!", show_alert=False)
            except Exception as e:
                await callback.answer(f"Ошибка: {e}", show_alert=True)
        else:
            await callback.answer(
                "Файл bot_photo.jpg не найден.\nПоложите фото в scripts_custom/bot_photo.jpg",
                show_alert=True,
            )

    # ── Ping ───────────────────────────────────────────────────────
    elif data == "mm_ping":
        start = time.time()
        msg = await callback.message.edit_text("🏓 Пинг...")
        end = time.time()
        ms = int((end - start) * 1000)
        await msg.edit_text(f"🏓 <b>Пинг: {ms}ms</b>", parse_mode=ParseMode.HTML)
        await callback.answer(show_alert=False)

    # ── Info ───────────────────────────────────────────────────────
    elif data == "mm_info":
        info = _load_info()

        lines = [f"🤖 <b>{info.get('name', BOT_NAME)}</b>"]
        if info.get("owner"):
            lines.append(f"👤 Владелец: <b>{info['owner']}</b>")
        if info.get("bio"):
            lines.append(f"📝 <i>{info['bio']}</i>")
        if info.get("info"):
            lines.append(f"\n{info['info']}")

        lines.append(f"\n📁 Файл: <code>{INFO_FILE}</code>")
        lines.append("ℹ️ Отредактируйте bot_info.json чтобы изменить инфо")

        text = "\n".join(lines)
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML)
        await callback.answer(show_alert=False)

    else:
        await callback.answer()


# ═══════════════════════════════════════════════════════════════════════
#  .lm  —  script management
# ═══════════════════════════════════════════════════════════════════════

async def lm_command(client: Client, message: Message):
    """Handler for .lm command - script management."""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.edit_text(
            "<b>Available .lm commands:</b>\n\n"
            "  <code>.lm load &lt;file&gt;</code> - load script\n"
            "  <code>.lm unload &lt;file&gt;</code> - unload script\n"
            "  <code>.lm list</code> - list scripts\n"
            "  <code>.lm reload &lt;file&gt;</code> - reload script\n"
            "  <code>.lm info &lt;file&gt;</code> - script info\n"
            "  <code>.lm unload_all</code> - unload all scripts",
            parse_mode=ParseMode.HTML,
        )
        return

    action = args[1].strip()
    Config.add_log(f".lm {action} from {message.from_user.id}")

    if action == "list":
        await _cmd_list(client, message)
    elif action.startswith("load "):
        filename = action[5:].strip()
        await _cmd_load(client, message, filename)
    elif action.startswith("unload "):
        filename = action[7:].strip()
        await _cmd_unload(client, message, filename)
    elif action.startswith("reload "):
        filename = action[7:].strip()
        await _cmd_reload(client, message, filename)
    elif action.startswith("info "):
        filename = action[5:].strip()
        await _cmd_info(client, message, filename)
    elif action == "unload_all":
        await _cmd_unload_all(client, message)
    else:
        await message.edit_text(f"Unknown command: <code>{action}</code>", parse_mode=ParseMode.HTML)


async def _cmd_list(client: Client, message: Message):
    loader = ScriptLoader()
    available = loader.get_available_scripts()
    loaded = list(Config.loaded_modules.keys())

    text = "<b>Scripts:</b>\n\n"
    text += "<b>Loaded:</b>\n"
    if loaded:
        for name in loaded:
            info = Config.loaded_modules_info.get(name, {})
            text += f"  <code>{name}</code>"
            if info.get("version"):
                text += f" v{info['version']}"
            text += "\n"
    else:
        text += "  <i>None</i>\n"

    text += "\n<b>Available:</b>\n"
    not_loaded = [s for s in available if s not in loaded]
    if not_loaded:
        for name in not_loaded:
            text += f"  <code>{name}</code>\n"
    else:
        text += "  <i>All loaded</i>\n"

    text += f"\nTotal files: {len(available)}"
    await message.edit_text(text, parse_mode=ParseMode.HTML)


async def _cmd_load(client: Client, message: Message, filename: str):
    if not filename.endswith(".py"):
        filename += ".py"

    loader = ScriptLoader()
    result = loader.load_script(filename, client)

    if result["success"]:
        await message.edit_text(
            f"Script <code>{filename}</code> loaded!\n\n"
            f"Name: {result.get('info', {}).get('name', filename)}\n"
            f"Version: {result.get('info', {}).get('version', 'N/A')}\n"
            f"Author: {result.get('info', {}).get('author', 'N/A')}\n"
            f"Description: {result.get('info', {}).get('description', 'N/A')}",
            parse_mode=ParseMode.HTML,
        )
        Config.add_log(f"Script {filename} loaded")
    else:
        await message.edit_text(f"Error: <code>{result['error']}</code>", parse_mode=ParseMode.HTML)
        Config.add_log(f"Error loading {filename}: {result['error']}", "ERROR")


async def _cmd_unload(client: Client, message: Message, filename: str):
    if not filename.endswith(".py"):
        filename += ".py"

    loader = ScriptLoader()
    result = loader.unload_script(filename)

    if result["success"]:
        await message.edit_text(f"Script <code>{filename}</code> unloaded.", parse_mode=ParseMode.HTML)
        Config.add_log(f"Script {filename} unloaded")
    else:
        await message.edit_text(f"Error: <code>{result['error']}</code>", parse_mode=ParseMode.HTML)


async def _cmd_reload(client: Client, message: Message, filename: str):
    if not filename.endswith(".py"):
        filename += ".py"

    loader = ScriptLoader()
    loader.unload_script(filename)
    result = loader.load_script(filename, client)
    if result["success"]:
        await message.edit_text(f"Script <code>{filename}</code> reloaded!", parse_mode=ParseMode.HTML)
        Config.add_log(f"Script {filename} reloaded")
    else:
        await message.edit_text(f"Error: <code>{result['error']}</code>", parse_mode=ParseMode.HTML)


async def _cmd_info(client: Client, message: Message, filename: str):
    if not filename.endswith(".py"):
        filename += ".py"

    loader = ScriptLoader()
    info = loader.get_script_info(filename)

    if info:
        text = (
            f"<b>{info.get('name', filename)}</b>\n\n"
            f"File: <code>{filename}</code>\n"
            f"Version: {info.get('version', 'N/A')}\n"
            f"Author: {info.get('author', 'N/A')}\n"
            f"Description: {info.get('description', 'N/A')}\n"
            f"Loaded: {'Yes' if filename in Config.loaded_modules else 'No'}\n"
            f"Size: {info.get('size', 'N/A')}\n"
        )
    else:
        text = f"Script <code>{filename}</code> not found."
    await message.edit_text(text, parse_mode=ParseMode.HTML)


async def _cmd_unload_all(client: Client, message: Message):
    loader = ScriptLoader()
    loaded = list(Config.loaded_modules.keys())
    count = 0
    for name in loaded:
        result = loader.unload_script(name)
        if result["success"]:
            count += 1
    await message.edit_text(f"Unloaded: {count}/{len(loaded)}")
    Config.add_log(f"Unloaded {count} scripts")


# ═══════════════════════════════════════════════════════════════════════
#  Bot startup
# ═══════════════════════════════════════════════════════════════════════

async def run_bot():
    """Start the userbot. Client is created here in the same event loop."""
    global bot_client

    Config.add_log(f"Initializing {BOT_NAME}...")
    logger.info(f"Starting {BOT_NAME}...")

    if not Config.API_ID or not Config.API_HASH:
        Config.add_log("ERROR: API_ID and API_HASH not configured!", "ERROR")
        logger.error("API_ID and API_HASH not configured")
        return

    client = Client(
        name="userbot_session",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        phone_number=Config.PHONE or None,
        session_string=Config.SESSION_STRING or None,
        workdir=Config.BASE_DIR,
    )

    bot_client = client

    # ── Built-in commands ───────────────────────────────────────────
    client.add_handler(
        MessageHandler(mm_command, filters.command("mm", prefixes=".") & filters.me)
    )
    client.add_handler(
        CallbackQueryHandler(mm_callback, filters.regex(r"^mm_"))
    )
    client.add_handler(
        MessageHandler(lm_command, filters.command("lm", prefixes=".") & filters.me)
    )

    # ── Auto-start scripts ───────────────────────────────────────────
    loader = ScriptLoader()
    auto_result = loader.auto_load_all(client)
    if auto_result["total"] > 0:
        Config.add_log(
            f"Auto-start: {len(auto_result['loaded'])}/{auto_result['total']} scripts loaded"
        )
        for fail in auto_result.get("failed", []):
            Config.add_log(
                f"Auto-start failed: {fail['file']} — {fail['error']}", "WARNING"
            )
    else:
        Config.add_log("Auto-start: no scripts configured")

    try:
        async with client:
            me = await client.get_me()
            Config.add_log(
                f"{BOT_NAME} started! Account: @{me.username or me.first_name} (ID: {me.id})"
            )
            logger.info(f"{BOT_NAME} started as @{me.username or me.first_name}")
            await idle()
    except Exception as e:
        Config.add_log(f"Bot error: {e}", "ERROR")
        logger.error(f"Error: {e}")
    finally:
        bot_client = None
