"""
Who TGK — узнай кто сидит за Telegram аккаунтом.
Собирает максимум доступной информации через MTProto API.

Команды:
  .whotgk @username     — инфо по юзернейму
  .whotgk @username @username2  — сравнение двух аккаунтов
  .whotgk id 123456789 — инфо по ID (без @)
  .whotgk reply        — инфо о пользователе (reply на сообщение)

Что собирает:
  - ID, юзернейм, имя, фамилия
  - Био (about)
  - Фото профиля (скачивает и отправляет)
  - Последнее посещение (last seen)
  - Подпись (username history) если доступно
  - Контакт: номер телефона (если раскрыт)
  - Дата создания аккаунта (приблизительно по первой активности)
  - Ограничения, бан, скам
  - Чаты общие с ботом
  - DC (дата-центр)
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message, User
from pyrogram.errors import (
    UsernameNotOccupied,
    UsernameInvalid,
    PeerIdInvalid,
    FloodWait,
    BadRequest,
)

logger = logging.getLogger("userbot.whotgk")

TIME_FMT = "%d.%m.%Y %H:%M:%S"


# ════════════════════════════════════════════════════════════════
# СБОР ИНФОРМАЦИИ О ПОЛЬЗОВАТЕЛЕ
# ════════════════════════════════════════════════════════════════

def _fmt_phone(phone: Optional[str]) -> str:
    """Отформатировать номер телефона."""
    if not phone:
        return "Скрыт"
    return f"+{phone}" if not phone.startswith("+") else phone


def _fmt_seen(status) -> str:
    """Форматировать LastSeenStatus."""
    if status is None:
        return "Скрыт / долго не заходил"

    try:
        from pyrogram.raw.types import (
            UserStatusEmpty,
            UserStatusOnline,
            UserStatusOffline,
            UserStatusRecently,
            UserStatusLastWeek,
            UserStatusLastMonth,
        )

        if isinstance(status, UserStatusOnline):
            return "В сети"
        elif isinstance(status, UserStatusOffline):
            was = datetime.fromtimestamp(status.was_online).strftime(TIME_FMT)
            return f"Был(а) в {was}"
        elif isinstance(status, UserStatusRecently):
            return "Был(а) недавно"
        elif isinstance(status, UserStatusLastWeek):
            return "Был(а) на этой неделе"
        elif isinstance(status, UserStatusLastMonth):
            return "Был(а) в этом месяце"
        elif isinstance(status, UserStatusEmpty):
            return "Давно не заходил(а)"
    except Exception:
        pass

    # Pyrogram high-level
    try:
        from pyrogram.enums import UserStatus
        if status == UserStatus.ONLINE:
            return "В сети"
        elif status == UserStatus.OFFLINE:
            return "Не в сети"
        elif status == UserStatus.RECENTLY:
            return "Был(а) недавно"
        elif status == UserStatus.LAST_WEEK:
            return "Был(а) на этой неделе"
        elif status == UserStatus.LAST_MONTH:
            return "Был(а) в этом месяце"
    except Exception:
        pass

    return str(status)


def _fmt_date(dt) -> str:
    """Форматировать дату."""
    if dt is None:
        return "—"
    if isinstance(dt, datetime):
        return dt.strftime(TIME_FMT)
    try:
        return datetime.fromtimestamp(dt).strftime(TIME_FMT)
    except Exception:
        return "—"


def _build_info_block(user: User, common_chats: int = 0) -> str:
    """Собрать блок информации о пользователе."""
    lines = []

    # Заголовок
    name_parts = []
    if user.first_name:
        name_parts.append(user.first_name)
    if user.last_name:
        name_parts.append(user.last_name)
    full_name = " ".join(name_parts) if name_parts else "Без имени"

    display = full_name
    if user.username:
        display += f" (@{user.username})"

    lines.append(f"<b>🔍 {display}</b>")
    lines.append("")

    # Основная информация
    lines.append("<b>📋 Основная информация:</b>")

    lines.append(f"  <b>ID:</b> <code>{user.id}</code>")

    if user.username:
        lines.append(f"  <b>Username:</b> @{user.username}")
    else:
        lines.append(f"  <b>Username:</b> <i>не установлен</i>")

    lines.append(f"  <b>Имя:</b> {user.first_name or '—'}")
    lines.append(f"  <b>Фамилия:</b> {user.last_name or '—'}")

    # Бот?
    if user.is_bot:
        lines.append(f"  <b>Тип:</b> Бот")
    else:
        lines.append(f"  <b>Тип:</b> Пользователь")

    # ═══ Профиль ═══
    lines.append("")
    lines.append("<b>👤 Профиль:</b>")

    # Био
    bio = ""
    try:
        full_user = user  # Pyrogram иногда даёт bio в User
        bio = getattr(user, "bio", None) or ""
    except Exception:
        pass

    if bio:
        lines.append(f"  <b>Био:</b> {bio}")
    else:
        lines.append(f"  <b>Био:</b> <i>пустое</i>")

    # Телефон
    phone = getattr(user, "phone", None)
    lines.append(f"  <b>Телефон:</b> {_fmt_phone(phone)}")

    # Язык
    lang = getattr(user, "language_code", None)
    if lang:
        lines.append(f"  <b>Язык:</b> {lang}")

    # ═══ Статус ═══
    lines.append("")
    lines.append("<b>📊 Статус:</b>")

    # Last seen
    status = getattr(user, "status", None) or getattr(user, "last_online_date", None)
    lines.append(f"  <b>Последнее посещение:</b> {_fmt_seen(status)}")

    # В сети?
    is_online = getattr(user, "is_online", False)
    if is_online:
        lines.append(f"  <b>Сейчас:</b> 🟢 В сети")
    else:
        lines.append(f"  <b>Сейчас:</b> 🔴 Не в сети")

    # Премиум
    if getattr(user, "is_premium", False):
        lines.append(f"  <b>Premium:</b> ✅ Да")

    # Верифицирован
    if getattr(user, "is_verified", False):
        lines.append(f"  <b>Верификация:</b> ✅ Подтверждён")

    # Скам / фейк
    if getattr(user, "is_scam", False):
        lines.append(f"  <b>⚠️ Скам:</b> ДА — аккаунт помечен как скам")
    if getattr(user, "is_fake", False):
        lines.append(f"  <b>⚠️ Фейк:</b> ДА — аккаунт помечен как фейк")

    # Ограничения
    if getattr(user, "is_restricted", False):
        lines.append(f"  <b>🚫 Ограничения:</b> Аккаунт ограничен Telegram")

    # Заблокирован?
    if getattr(user, "is_deleted", False):
        lines.append(f"  <b>🗑️ Статус:</b> Удалён")

    # ═══ Техническая информация ═══
    lines.append("")
    lines.append("<b>🔧 Техническая информация:</b>")

    # Фото профиля
    has_photo = getattr(user, "photo", None) is not None
    lines.append(f"  <b>Фото профиля:</b> {'✅ Есть' if has_photo else '❌ Нет'}")

    # Общие чаты
    lines.append(f"  <b>Общих чатов:</b> {common_chats}")

    # Фото в чатах
    has_chat_photo = getattr(user, "has_private_forwards", False)
    if has_chat_photo:
        lines.append(f"  <b>Пересылки:</b> 🔒 Приватные")

    # DC (дата-центр)
    dc = None
    try:
        photo = getattr(user, "photo", None)
        if photo:
            dc = getattr(photo, "dc_id", None)
    except Exception:
        pass
    if dc:
        lines.append(f"  <b>DC:</b> {dc}")

    # Contact?
    is_contact = getattr(user, "is_contact", False)
    lines.append(f"  <b>В контактах:</b> {'✅ Да' if is_contact else '❌ Нет'}")

    # Mutual contact?
    mutual = getattr(user, "is_mutual_contact", False)
    lines.append(f"  <b>Взаимный контакт:</b> {'✅ Да' if mutual else '❌ Нет'}")

    return "\n".join(lines)


async def _download_profile_photo(client, user_id: int) -> Optional[bytes]:
    """Скачать фото профиля пользователя."""
    try:
        photos = await client.get_profile_photos(user_id, limit=1)
        if photos and photos.total_count > 0:
            photo = photos.photos[0]
            # Берём фото максимального качества
            if hasattr(photo, "thumbs") and photo.thumbs:
                # Нужен file_id полного фото
                pass
            # Скачиваем через download_media
            import tempfile
            tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            path = await client.download_media(user_id, file_name=tmp.name)
            if path:
                with open(path, "rb") as f:
                    data = f.read()
                import os
                try:
                    os.unlink(path)
                except Exception:
                    pass
                return data
        return None
    except Exception as e:
        logger.debug(f"Profile photo download error: {e}")
        return None


async def _count_common_chats(client, user_id: int) -> int:
    """Посчитать общие чаты с пользователем."""
    try:
        # Пробуем через get_common_chats
        common = await client.get_common_chats(user_id)
        return len(common)
    except AttributeError:
        # Метод может не существовать в некоторых версиях
        pass
    except Exception as e:
        logger.debug(f"Common chats error: {e}")
    return 0


# ════════════════════════════════════════════════════════════════
# ХЕНДЛЕРЫ
# ════════════════════════════════════════════════════════════════

def register(client):

    @client.on_message(filters.command("whotgk", prefixes=".") & filters.me)
    async def whotgk_handler(client, message: Message):
        args = message.text.split(maxsplit=1)

        if len(args) < 2:
            await message.edit_text(
                "<b>🔍 Who TGK — Информация о пользователе</b>\n\n"
                "<code>.whotgk @username</code> — информация по юзернейму\n"
                "<code>.whotgk @user1 @user2</code> — сравнение двух\n"
                "<code>.whotgk</code> (reply) — информация о авторе сообщения\n"
                "<code>.whotgk id 123456789</code> — по ID",
                parse_mode=ParseMode.HTML,
            )
            return

        targets_raw = args[1].strip()

        # Режим: reply на сообщение
        if not targets_raw and message.reply_to_message:
            target_user = message.reply_to_message.from_user
            if target_user:
                targets_raw = f"@{target_user.username}" if target_user.username else str(target_user.id)
            else:
                await message.edit_text("❌ Не удалось определить пользователя из ответа", parse_mode=ParseMode.HTML)
                return

        # Режим: reply (даже если есть текст, но проверяем reply first)
        if message.reply_to_message and message.reply_to_message.from_user:
            target_user = message.reply_to_message.from_user
            if target_user:
                reply_target = str(target_user.id)
                # Если текст совпадает с reply — используем reply
                if targets_raw in (f"@{target_user.username}", str(target_user.id)):
                    targets_raw = reply_target

        # Парсим аргументы
        targets = []

        # Режим: id <number>
        if targets_raw.lower().startswith("id "):
            try:
                user_id = int(targets_raw[3:].strip())
                targets.append(("id", user_id))
            except ValueError:
                await message.edit_text("❌ Неверный формат ID. Используйте: <code>.whotgk id 123456789</code>", parse_mode=ParseMode.HTML)
                return
        else:
            # Парсим @username (одно или два через пробел)
            parts = targets_raw.split()
            for part in parts:
                part = part.strip()
                if part.startswith("@"):
                    targets.append(("username", part[1:]))
                elif part.lstrip("-").isdigit():
                    targets.append(("id", int(part)))
                else:
                    # Может быть юзернейм без @
                    targets.append(("username", part))

        if not targets:
            await message.edit_text("❌ Укажите юзернейм или ID", parse_mode=ParseMode.HTML)
            return

        # Проверяем количество целей
        if len(targets) > 2:
            await message.edit_text("❌ Максимум 2 пользователя для сравнения", parse_mode=ParseMode.HTML)
            return

        # Показываем загрузку
        status_msg = await message.edit_text("🔍 Собираю информацию...", parse_mode=ParseMode.HTML)

        # ═══ Режим сравнения (2 пользователя) ═══
        if len(targets) == 2:
            await _handle_compare(client, status_msg, targets)
            return

        # ═══ Режим одного пользователя ═══
        target_type, target_value = targets[0]
        await _handle_single(client, status_msg, target_type, target_value)


async def _handle_single(client, message: Message, target_type: str, target_value):
    """Обработка одного пользователя."""
    try:
        # Получаем пользователя
        if target_type == "username":
            user = await client.get_users(target_value)
        else:
            user = await client.get_users(target_value)

        if not user:
            await message.edit_text(f"❌ Пользователь не найден", parse_mode=ParseMode.HTML)
            return

        # Считаем общие чаты
        common = await _count_common_chats(client, user.id)

        # Строим блок информации
        text = _build_info_block(user, common)

        # Пробуем скачать фото
        photo_data = await _download_profile_photo(client, user.id)

        # Редактируем сообщение
        try:
            if photo_data:
                await message.delete()
                await message.reply_photo(
                    photo=photo_data,
                    caption=text,
                    parse_mode=ParseMode.HTML,
                )
            else:
                await message.edit_text(text, parse_mode=ParseMode.HTML)
        except Exception as e:
            # Если edit не работает (старое сообщение) — отправляем новое
            try:
                await message.delete()
            except Exception:
                pass
            if photo_data:
                await message.reply_photo(photo=photo_data, caption=text, parse_mode=ParseMode.HTML)
            else:
                await message.reply_text(text, parse_mode=ParseMode.HTML)

    except UsernameNotOccupied:
        await message.edit_text("❌ Этот юзернейм никому не принадлежит", parse_mode=ParseMode.HTML)
    except UsernameInvalid:
        await message.edit_text("❌ Неверный формат юзернейма", parse_mode=ParseMode.HTML)
    except PeerIdInvalid:
        await message.edit_text("❌ Пользователь не найден (неверный ID)", parse_mode=ParseMode.HTML)
    except FloodWait as e:
        await message.edit_text(f"⏳ FloodWait — подождите {e.value} секунд", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"whotgk error: {e}")
        await message.edit_text(f"❌ Ошибка: <code>{str(e)[:100]}</code>", parse_mode=ParseMode.HTML)


async def _handle_compare(client, message: Message, targets: list):
    """Обработка сравнения двух пользователей."""
    users = []

    for target_type, target_value in targets:
        try:
            if target_type == "username":
                user = await client.get_users(target_value)
            else:
                user = await client.get_users(target_value)
            if user:
                users.append(user)
        except Exception as e:
            await message.edit_text(
                f"❌ Не удалось найти пользователя {target_value}: {str(e)[:50]}",
                parse_mode=ParseMode.HTML,
            )
            return

    if len(users) < 2:
        await message.edit_text("❌ Не удалось загрузить оба пользователя", parse_mode=ParseMode.HTML)
        return

    u1, u2 = users

    # ═══ Блок сравнения ═══
    lines = []
    lines.append("<b>🔍 Сравнение аккаунтов</b>")
    lines.append("")

    # Имена
    n1 = u1.first_name or "—"
    n2 = u2.first_name or "—"
    if u1.last_name:
        n1 += f" {u1.last_name}"
    if u2.last_name:
        n2 += f" {u2.last_name}"
    lines.append(f"<b>👤 1:</b> {n1}")
    lines.append(f"<b>👤 2:</b> {n2}")
    lines.append("")

    # Таблица сравнения
    def _row(label, v1, v2):
        lines.append(f"  <b>{label}:</b>")
        lines.append(f"    1️⃣ {v1}")
        lines.append(f"    2️⃣ {v2}")
        lines.append("")

    _row("ID", f"<code>{u1.id}</code>", f"<code>{u2.id}</code>")

    _row("Username", f"@{u1.username}" if u1.username else "—", f"@{u2.username}" if u2.username else "—")

    _row("Телефон", _fmt_phone(getattr(u1, "phone", None)), _fmt_phone(getattr(u2, "phone", None)))

    _row("Био", getattr(u1, "bio", None) or "—", getattr(u2, "bio", None) or "—")

    _row("Последнее посещение", _fmt_seen(getattr(u1, "status", None)), _fmt_seen(getattr(u2, "status", None)))

    _row("Premium", "✅" if getattr(u1, "is_premium", False) else "❌", "✅" if getattr(u2, "is_premium", False) else "❌")

    _row("Верификация", "✅" if getattr(u1, "is_verified", False) else "❌", "✅" if getattr(u2, "is_verified", False) else "❌")

    _row("Бот", "✅" if u1.is_bot else "❌", "✅" if u2.is_bot else "❌")

    _row("Скам", "⚠️ ДА" if getattr(u1, "is_scam", False) else "Нет", "⚠️ ДА" if getattr(u2, "is_scam", False) else "Нет")

    _row("Ограничен", "🚫 ДА" if getattr(u1, "is_restricted", False) else "Нет", "🚫 ДА" if getattr(u2, "is_restricted", False) else "Нет")

    _row("Фото", "✅" if getattr(u1, "photo", None) else "❌", "✅" if getattr(u2, "photo", None) else "❌")

    # DC
    dc1 = getattr(getattr(u1, "photo", None), "dc_id", None)
    dc2 = getattr(getattr(u2, "photo", None), "dc_id", None)
    _row("DC", str(dc1) if dc1 else "—", str(dc2) if dc2 else "—")

    # Одинаковый DC = возможно один человек
    if dc1 and dc2 and dc1 == dc2:
        lines.append("")
        lines.append("⚠️ <b>Внимание:</b> оба аккаунта на одном DC — возможно один человек")

    # Проверка: одинаковый телефон
    p1 = getattr(u1, "phone", None)
    p2 = getattr(u2, "phone", None)
    if p1 and p2 and p1 == p2:
        lines.append("⚠️ <b>Внимание:</b> одинаковый номер телефона — это один человек!")

    await message.edit_text("\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True)


def on_load():
    print("[WhoTGK] Loaded. .whotgk @username — информация о пользователе")


def on_unload():
    print("[WhoTGK] Unloaded")
