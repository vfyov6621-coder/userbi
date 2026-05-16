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

BOT_NAME = "sandusr"
INFO_FILE = os.path.join(Config.CUSTOM_SCRIPTS_DIR, "bot_info.json")
PHOTO_FILE = os.path.join(Config.BASE_DIR, "scripts", "bot_photo.jpg")


# ═══════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════

def _load_info() -> dict:
    try:
        if os.path.exists(INFO_FILE):
            with open(INFO_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"name": BOT_NAME, "bio": "", "owner": "", "info": "Инфо не настроена."}


def _is_owner(user_id: int, client: Client) -> bool:
    """Owner = the userbot account itself."""
    return user_id == client.me.id if client.me else False


# ═══════════════════════════════════════════════════════════════════════
#  .mm  —  built-in menu (с фото)
# ═══════════════════════════════════════════════════════════════════════

MM_KEYBOARD = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("🏓 Пинг", callback_data="mm_ping")],
        [InlineKeyboardButton("ℹ️ Инфо", callback_data="mm_info")],
        [InlineKeyboardButton("👤 Владелец", callback_data="mm_owner")],
    ]
)


async def mm_command(client: Client, message: Message):
    """Show the main menu with photo header."""
    info = _load_info()
    name = info.get("name", BOT_NAME)
    bio = info.get("bio", "")

    text = f"🤖 <b>{name}</b>"
    if bio:
        text += f"\n<i>{bio}</i>"
    text += "\n\nВыберите действие:"

    # Если есть фото — отправляем с фото
    if os.path.exists(PHOTO_FILE):
        try:
            await message.edit_text(text, reply_markup=MM_KEYBOARD, parse_mode=ParseMode.HTML)
            # Отправляем фото отдельным сообщением (edited message не может стать photo)
            # Но лучше: удаляем текст и отправляем фото + caption
            await message.delete()
            await client.send_photo(
                chat_id=message.chat.id,
                photo=PHOTO_FILE,
                caption=text,
                reply_markup=MM_KEYBOARD,
                parse_mode=ParseMode.HTML,
                reply_to_message_id=message.reply_to_message_id if message.reply_to_message else None,
            )
        except Exception as e:
            # Если не удалось с фото — fallback на текст
            logger.warning(f"Could not send .mm with photo: {e}")
            await message.edit_text(text, reply_markup=MM_KEYBOARD, parse_mode=ParseMode.HTML)
    else:
        await message.edit_text(text, reply_markup=MM_KEYBOARD, parse_mode=ParseMode.HTML)


async def mm_callback(client: Client, callback: CallbackQuery):
    """Handle inline keyboard presses from .mm menu."""
    data = callback.data
    from_user_id = callback.from_user.id

    if data == "mm_ping":
        start = time.time()
        msg = await callback.message.edit_text("🏓 Пинг...")
        end = time.time()
        ms = int((end - start) * 1000)
        await msg.edit_text(f"🏓 <b>Пинг: {ms}ms</b>", parse_mode=ParseMode.HTML)
        await callback.answer(show_alert=False)

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

    elif data == "mm_owner":
        if not _is_owner(from_user_id, client):
            await callback.answer("⛔ Только для владельца", show_alert=True)
            return

        me = client.me
        text = (
            f"👤 <b>Владелец</b>\n\n"
            f"📌 Имя: <b>{me.first_name}</b>\n"
            f"📌 ID: <code>{me.id}</code>\n"
        )
        if me.username:
            text += f"📌 Username: @{me.username}\n"
        if me.last_name:
            text += f"📌 Фамилия: {me.last_name}\n"
        if me.bio:
            text += f"📌 Bio: <i>{me.bio}</i>\n"

        text += (
            f"\n📌 Статус: <code>{me.status.value if me.status else '?'}</code>\n"
            f"📌 Премиум: {'✅' if me.is_premium else '❌'}"
        )

        await callback.message.edit_text(text, parse_mode=ParseMode.HTML)
        await callback.answer(show_alert=False)

    else:
        await callback.answer()


# ═══════════════════════════════════════════════════════════════════════
#  .mf  —  set menu photo from reply
# ═══════════════════════════════════════════════════════════════════════

async def mf_command(client: Client, message: Message):
    """Reply to a photo to set it as the bot menu photo."""
    if not message.reply_to_message:
        await message.edit_text(
            "❌ Ответьте на сообщение с фото:\n<code>.mf</code> (ответ на фото)",
            parse_mode=ParseMode.HTML,
        )
        return

    reply = message.reply_to_message
    if not reply.photo and not reply.sticker:
        await message.edit_text(
            "❌ В ответе должно быть фото или стикер",
            parse_mode=ParseMode.HTML,
        )
        return

    await message.edit_text("📸 Сохранение фото...", parse_mode=ParseMode.HTML)

    try:
        if reply.photo:
            file = await client.download_media(reply.photo.file_id, file_name=PHOTO_FILE)
        else:
            file = await client.download_media(reply.sticker.file_id, file_name=PHOTO_FILE)

        if file:
            await message.edit_text(
                "✅ Фото установлено!\n\nТеперь <code>.mm</code> покажет это фото.",
                parse_mode=ParseMode.HTML,
            )
        else:
            await message.edit_text("❌ Не удалось скачать фото", parse_mode=ParseMode.HTML)

    except Exception as e:
        await message.edit_text(f"❌ Ошибка: {e}", parse_mode=ParseMode.HTML)


# ═══════════════════════════════════════════════════════════════════════
#  .lm  —  script management
# ═══════════════════════════════════════════════════════════════════════

async def lm_command(client: Client, message: Message):
    """Handler for .lm command - script management."""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.edit_text(
            "<b>Управление скриптами:</b>\n\n"
            "  <code>.lm load &lt;id&gt;</code> — загрузить скрипт\n"
            "  <code>.lm unload &lt;id&gt;</code> — выгрузить\n"
            "  <code>.lm reload &lt;id&gt;</code> — перезагрузить\n"
            "  <code>.lm list</code> — список скриптов\n"
            "  <code>.lm info &lt;id&gt;</code> — инфо о скрипте\n"
            "  <code>.lm unload_all</code> — выгрузить все",
            parse_mode=ParseMode.HTML,
        )
        return

    action = args[1].strip()
    Config.add_log(f".lm {action} from {message.from_user.id}")

    if action == "list":
        await _cmd_list(client, message)
    elif action.startswith("load "):
        sid = action[5:].strip()
        await _cmd_load(client, message, sid)
    elif action.startswith("unload "):
        sid = action[7:].strip()
        await _cmd_unload(client, message, sid)
    elif action.startswith("reload "):
        sid = action[7:].strip()
        await _cmd_reload(client, message, sid)
    elif action.startswith("info "):
        sid = action[5:].strip()
        await _cmd_info(client, message, sid)
    elif action == "unload_all":
        await _cmd_unload_all(client, message)
    else:
        await message.edit_text(f"Неизвестная команда: <code>{action}</code>", parse_mode=ParseMode.HTML)


async def _cmd_list(client: Client, message: Message):
    loader = ScriptLoader()
    available = loader.get_available_scripts()
    loaded = list(Config.loaded_modules.keys())

    text = "<b>Скрипты:</b>\n\n"
    text += "<b>Загружены:</b>\n"
    if loaded:
        for sid in loaded:
            info = Config.loaded_modules_info.get(sid, {})
            name = info.get("name", sid)
            cmd = info.get("command", "")
            text += f"  <code>{sid}</code>"
            if cmd:
                text += f" ({cmd})"
            text += "\n"
    else:
        text += "  <i>Нет</i>\n"

    text += "\n<b>Доступны:</b>\n"
    not_loaded = [s for s in available if s not in loaded]
    if not_loaded:
        for sid in not_loaded:
            text += f"  <code>{sid}</code>\n"
    else:
        text += "  <i>Все загружены</i>\n"

    text += f"\nВсего: {len(available)}"
    await message.edit_text(text, parse_mode=ParseMode.HTML)


async def _cmd_load(client: Client, message: Message, script_id: str):
    loader = ScriptLoader()
    result = loader.load_script(script_id, client)

    if result["success"]:
        info = result.get("info", {})
        addons = result.get("addons_loaded", [])
        text = f"✅ Скрипт <code>{script_id}</code> загружен!\n\n"
        text += f"📝 Имя: {info.get('name', script_id)}\n"
        text += f"📋 Версия: {info.get('version', '?')}\n"
        if addons:
            text += f"🔌 Аддоны: {', '.join(addons)}\n"
        await message.edit_text(text, parse_mode=ParseMode.HTML)
        Config.add_log(f"Script {script_id} loaded")
    else:
        await message.edit_text(f"❌ Ошибка: <code>{result['error']}</code>", parse_mode=ParseMode.HTML)
        Config.add_log(f"Error loading {script_id}: {result['error']}", "ERROR")


async def _cmd_unload(client: Client, message: Message, script_id: str):
    loader = ScriptLoader()
    result = loader.unload_script(script_id)
    if result["success"]:
        await message.edit_text(f"✅ Скрипт <code>{script_id}</code> выгружен", parse_mode=ParseMode.HTML)
        Config.add_log(f"Script {script_id} unloaded")
    else:
        await message.edit_text(f"❌ Ошибка: <code>{result['error']}</code>", parse_mode=ParseMode.HTML)


async def _cmd_reload(client: Client, message: Message, script_id: str):
    loader = ScriptLoader()
    loader.unload_script(script_id)
    result = loader.load_script(script_id, client)
    if result["success"]:
        addons = result.get("addons_loaded", [])
        text = f"✅ Скрипт <code>{script_id}</code> перезагружен!"
        if addons:
            text += f"\n🔌 Аддоны: {', '.join(addons)}"
        await message.edit_text(text, parse_mode=ParseMode.HTML)
        Config.add_log(f"Script {script_id} reloaded")
    else:
        await message.edit_text(f"❌ Ошибка: <code>{result['error']}</code>", parse_mode=ParseMode.HTML)


async def _cmd_info(client: Client, message: Message, script_id: str):
    loader = ScriptLoader()
    info = loader.get_script_info(script_id)

    if info:
        text = (
            f"<b>{info.get('name', script_id)}</b>\n\n"
            f"ID: <code>{script_id}</code>\n"
            f"Версия: {info.get('version', '?')}\n"
            f"Автор: {info.get('author', '?')}\n"
            f"Описание: {info.get('description', '?')}\n"
            f"Команда: {info.get('command', '?')}\n"
            f"Загружен: {'Да' if info.get('loaded') else 'Нет'}\n"
            f"Тип: {'Папка' if info.get('is_folder') else 'Файл'}\n"
            f"Кастомный: {'Да' if info.get('is_custom') else 'Нет'}\n"
        )
        if info.get("addons"):
            text += "\n<b>Аддоны:</b>\n"
            for addon in info["addons"]:
                status = "✅" if addon.get("enabled") else "❌"
                text += f"  {status} {addon.get('name', '?')} ({addon.get('command', '?')})\n"
        if info.get("tabs"):
            text += "\n<b>Веб-вкладки:</b>\n"
            for tab in info["tabs"]:
                text += f"  {tab.get('icon', '')} {tab.get('name', '?')}\n"
    else:
        text = f"❌ Скрипт <code>{script_id}</code> не найден"
    await message.edit_text(text, parse_mode=ParseMode.HTML)


async def _cmd_unload_all(client: Client, message: Message):
    loader = ScriptLoader()
    loaded = list(Config.loaded_modules.keys())
    count = 0
    for sid in loaded:
        result = loader.unload_script(sid)
        if result["success"]:
            count += 1
    await message.edit_text(f"Выгружено: {count}/{len(loaded)}")
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

    # ── Built-in commands ───────────────────────────────────────────────
    client.add_handler(
        MessageHandler(mm_command, filters.command("mm", prefixes=".") & filters.me)
    )
    client.add_handler(
        CallbackQueryHandler(mm_callback, filters.regex(r"^mm_"))
    )
    client.add_handler(
        MessageHandler(mf_command, filters.command("mf", prefixes=".") & filters.me & filters.reply)
    )
    client.add_handler(
        MessageHandler(lm_command, filters.command("lm", prefixes=".") & filters.me)
    )

    # ── Auto-start scripts ───────────────────────────────────────────────
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
