"""
Menu System — полная система inline-меню для Zaya userbot.
Архитектура: menu tree (словарь) → автоматическая генерация кнопок и роутинг.

Команды:
  .menu        — открыть главное меню
  .menu close  — закрыть меню (удалить сообщение)

Безопасность:
  - Только OWNER_ID может нажимать кнопки
  - Cooldown 1.5 сек между нажатиями
  - FloodWait обрабатывается автоматически
  - Обработка удалённых/изменённых сообщений
"""

import os
import time
import logging
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

logger = logging.getLogger("userbot.menu")

# ════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ════════════════════════════════════════════════════════════════

# ВНИМАНИЕ: OWNER_ID берётся из config.py бота.
# Если owner_id не задан — кнопки будут работать для любого пользователя юзербота.
# В продакшене ОБЯЗАТЕЛЬНО установи owner_id в настройках бота!

# Минимальная пауза между нажатиями callback-кнопок (секунды).
# Telegram банит за >30 callback/сек на одно сообщение.
# 1.5 сек — безопасный минимум.
COOLDOWN_SECONDS = 1.5

# Формат времени для отображения
TIME_FORMAT = "%d.%m.%Y %H:%M:%S"

# ════════════════════════════════════════════════════════════════
# ДЕРЕВО МЕНЮ — ЕДИНСТВЕННОЕ МЕСТО ДЛЯ РЕДАКТИРОВАНИЯ РАЗДЕЛОВ
# ════════════════════════════════════════════════════════════════
#
# Структура каждого пункта:
#   {
#     "label": "Текст кнопки",
#     "icon": "📊",                     # опционально, эмодзи перед label
#     "callback": "stats",              # callback_data (уникальный ID)
#     "text": "Текст сообщения при нажатии",  # тело сообщения
#     "submenu": { ... },               # вложенное меню (опционально)
#     "action": "func_name",            # имя функции-обработчика (опционально)
#   }
#
# Специальные callback_data:
#   "menu:main"       — вернуться в главное меню
#   "menu:back"       — на уровень назад
#   "menu:close"      — закрыть меню
#   "custom:XXX"      — вызов action-функции с именем XXX
#
# Чтобы добавить новый раздел — просто добавь его в MENU_TREE.

MENU_TREE: Dict[str, Any] = {
    "stats": {
        "icon": "📊",
        "label": "Статистика",
        "callback": "custom:show_stats",
        "text": None,  # генерируется динамически через action
    },
    "settings": {
        "icon": "⚙️",
        "label": "Настройки",
        "callback": "nav:settings",
        "submenu": {
            "language": {
                "icon": "🌐",
                "label": "Язык",
                "callback": "custom:toggle_language",
                "text": None,
            },
            "notifications": {
                "icon": "🔔",
                "label": "Уведомления",
                "callback": "custom:toggle_notifications",
                "text": None,
            },
            "autosave": {
                "icon": "💾",
                "label": "Автосейв",
                "callback": "custom:toggle_autosave",
                "text": None,
            },
            "back": {
                "icon": "🔙",
                "label": "Назад",
                "callback": "menu:back",
            },
        },
    },
    "scripts": {
        "icon": "📜",
        "label": "Скрипты",
        "callback": "custom:list_scripts",
        "text": None,
    },
    "logs": {
        "icon": "📋",
        "label": "Логи",
        "callback": "nav:logs",
        "submenu": {
            "recent": {
                "icon": "🕐",
                "label": "Последние",
                "callback": "custom:show_recent_logs",
                "text": None,
            },
            "errors": {
                "icon": "❌",
                "label": "Ошибки",
                "callback": "custom:show_errors",
                "text": None,
            },
            "clear": {
                "icon": "🗑️",
                "label": "Очистить",
                "callback": "custom:clear_logs",
                "text": None,
            },
            "back": {
                "icon": "🔙",
                "label": "Назад",
                "callback": "menu:back",
            },
        },
    },
    "close": {
        "icon": "🚫",
        "label": "Закрыть",
        "callback": "menu:close",
    },
}

# ════════════════════════════════════════════════════════════════
# СОСТОЯНИЕ
# ════════════════════════════════════════════════════════════════

# Храним последнее нажатие для cooldown: user_id -> timestamp
_last_callback_time: Dict[int, float] = {}

# Навигационный стек для каждого пользователя: user_id -> [menu_key, ...]
# Позволяет кнопке "Назад" возвращаться на предыдущий уровень.
_nav_stack: Dict[int, List[str]] = []

# ID сообщений меню: user_id -> message_id (чтобы закрывать)
_menu_messages: Dict[int, Tuple[int, int]] = {}  # user_id -> (chat_id, msg_id)

# Настройки пользователя (сохраняются в сессии, при рестарте сбрасываются)
_user_settings: Dict[int, Dict[str, Any]] = {
    # user_id: {"language": "ru", "notifications": True, "autosave": True}
}


def _get_user_settings(user_id: int) -> Dict[str, Any]:
    """Получить настройки пользователя (с дефолтами)."""
    if user_id not in _user_settings:
        _user_settings[user_id] = {
            "language": "ru",
            "notifications": True,
            "autosave": True,
        }
    return _user_settings[user_id]


# ════════════════════════════════════════════════════════════════
# ВЫВОД ТЕКСТА СТИЛЕМ (HTML)
# ════════════════════════════════════════════════════════════════

def _bold(text: str) -> str:
    return f"<b>{text}</b>"


def _code(text: str) -> str:
    return f"<code>{text}</code>"


def _italic(text: str) -> str:
    return f"<i>{text}</i>"


# ════════════════════════════════════════════════════════════════
# ПОСТРОЕНИЕ INLINE-КЛАВИАТУРЫ
# ════════════════════════════════════════════════════════════════

def _build_keyboard(menu_data: Dict[str, Any]) -> InlineKeyboardMarkup:
    """
    Построить InlineKeyboardMarkup из словаря меню.
    Каждый элемент словаря — одна кнопка (одна в ряд).
    Кнопка "close" добавляется в конец отдельной строкой.
    """
    buttons = []
    close_btn = None

    for key, item in menu_data.items():
        icon = item.get("icon", "")
        label = item.get("label", key)
        callback = item.get("callback", f"nav:{key}")
        text = f"{icon} {label}" if icon else label

        btn = InlineKeyboardButton(text, callback_data=callback)

        if callback == "menu:close":
            close_btn = btn
        else:
            buttons.append([btn])

    if close_btn:
        buttons.append([close_btn])

    return InlineKeyboardMarkup(buttons)


def _build_main_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура главного меню."""
    return _build_keyboard(MENU_TREE)


def _build_submenu_keyboard(submenu: Dict[str, Any]) -> InlineKeyboardMarkup:
    """Клавиатура вложенного меню (с кнопкой 'Назад' в конце)."""
    return _build_keyboard(submenu)


# ════════════════════════════════════════════════════════════════
# ПОИСК РАЗДЕЛА ПО CALLBACK_DATA
# ════════════════════════════════════════════════════════════════

def _find_menu_item(menu_data: Dict[str, Any], callback_data: str) -> Tuple[Optional[Dict], List[str]]:
    """
    Найти пункт меню по callback_data.
    Возвращает (item_or_None, path_to_item).
    """
    for key, item in menu_data.items():
        cb = item.get("callback", f"nav:{key}")
        if cb == callback_data:
            return item, [key]
        # Рекурсивно искать в подменю
        if "submenu" in item:
            found, sub_path = _find_menu_item(item["submenu"], callback_data)
            if found is not None:
                return found, [key] + sub_path
    return None, []


def _find_submenu_by_callback(menu_data: Dict[str, Any], callback_data: str) -> Optional[Dict[str, Any]]:
    """
    Найти подменю, в котором находится кнопка с данным callback_data.
    Возвращает словарь подменю или None.
    """
    for key, item in menu_data.items():
        cb = item.get("callback", f"nav:{key}")
        if cb == callback_data:
            return menu_data  # Это кнопка в текущем меню
        if "submenu" in item:
            if any(
                sub.get("callback") == callback_data
                for sub in item["submenu"].values()
            ):
                return item["submenu"]
    return None


# ════════════════════════════════════════════════════════════════
# ACTION-ФУНКЦИИ (обработчики custom:XXX)
# ════════════════════════════════════════════════════════════════
#
# Чтобы добавить новый action:
#   1. Создай async функцию с сигнатурой: async def action_xxx(client, callback, **kwargs) -> Tuple[str, Optional[InlineKeyboardMarkup]]
#   2. Добавь её в словарь ACTIONS ниже
#   3. В MENU_TREE укажи "callback": "custom:xxx"

async def action_show_stats(client, callback: CallbackQuery, **kwargs) -> Tuple[str, Optional[InlineKeyboardMarkup]]:
    """Показать статистику бота."""
    user = callback.from_user
    now = datetime.now().strftime(TIME_FORMAT)
    total_chats = 0
    total_scripts = 0

    try:
        from config import Config
        total_scripts = len(Config.loaded_modules)
        total_chats = len(Config.loaded_addons)
    except Exception:
        pass

    try:
        dialogs = await client.get_dialogs(limit=0)
        total_chats = len(dialogs)
    except Exception:
        pass

    text = (
        f"{_bold('📊 Статистика Zaya')}\n\n"
        f"👤 Владелец: {_code(user.first_name)} ({_code(str(user.id))})\n"
        f"🕐 Время: {_code(now)}\n"
        f"💻 Скриптов загружено: {_code(str(total_scripts))}\n"
        f"💬 Чатов: {_code(str(total_chats))}\n"
        f"⚡ Cooldown: {_code(f'{COOLDOWN_SECONDS}с')}"
    )
    return text, _build_main_keyboard()


async def action_toggle_language(client, callback: CallbackQuery, **kwargs) -> Tuple[str, Optional[InlineKeyboardMarkup]]:
    """Переключить язык (демо)."""
    user_id = callback.from_user.id
    settings = _get_user_settings(user_id)
    settings["language"] = "en" if settings["language"] == "ru" else "ru"
    lang_name = "Русский" if settings["language"] == "ru" else "English"

    text = (
        f"{_bold('🌐 Язык')}\n\n"
        f"Текущий язык: {_bold(lang_name)}\n\n"
        f" {_italic('(Демо — в полной версии здесь можно менять язык интерфейса)')}"
    )

    # Возвращаем клавиатуру подменю Настройки
    submenu = MENU_TREE.get("settings", {}).get("submenu", {})
    return text, _build_submenu_keyboard(submenu)


async def action_toggle_notifications(client, callback: CallbackQuery, **kwargs) -> Tuple[str, Optional[InlineKeyboardMarkup]]:
    """Переключить уведомления (демо)."""
    user_id = callback.from_user.id
    settings = _get_user_settings(user_id)
    settings["notifications"] = not settings["notifications"]
    status = "Включены" if settings["notifications"] else "Выключены"
    icon = "✅" if settings["notifications"] else "❌"

    text = (
        f"{_bold('🔔 Уведомления')}\n\n"
        f"Статус: {icon} {_bold(status)}\n\n"
        f"{_italic('(Демо — уведомления о новых сообщениях/обновлениях)')}"
    )

    submenu = MENU_TREE.get("settings", {}).get("submenu", {})
    return text, _build_submenu_keyboard(submenu)


async def action_toggle_autosave(client, callback: CallbackQuery, **kwargs) -> Tuple[str, Optional[InlineKeyboardMarkup]]:
    """Переключить автосейв (демо)."""
    user_id = callback.from_user.id
    settings = _get_user_settings(user_id)
    settings["autosave"] = not settings["autosave"]
    status = "Включён" if settings["autosave"] else "Выключен"
    icon = "✅" if settings["autosave"] else "❌"

    text = (
        f"{_bold('💾 Автосейв')}\n\n"
        f"Статус: {icon} {_bold(status)}\n\n"
        f"{_italic('(Демо — автосохранение данных каждые 5 минут)')}"
    )

    submenu = MENU_TREE.get("settings", {}).get("submenu", {})
    return text, _build_submenu_keyboard(submenu)


async def action_list_scripts(client, callback: CallbackQuery, **kwargs) -> Tuple[str, Optional[InlineKeyboardMarkup]]:
    """Показать список загруженных скриптов."""
    lines = []
    try:
        from config import Config
        for script_id, module in Config.loaded_modules.items():
            name = script_id
            if hasattr(module, "on_load"):
                try:
                    doc = module.on_load.__doc__
                    if doc:
                        first_line = doc.strip().split("\n")[0].strip()
                        if first_line:
                            name = first_line
                except Exception:
                    pass
            addon_count = len(Config.loaded_addons.get(script_id, {}))
            addon_str = f" ({_code(f'+{addon_count} адд.')})" if addon_count else ""
            lines.append(f"  ✅ {_code(script_id)} — {name}{addon_str}")
    except Exception:
        pass

    if not lines:
        lines.append("  {_italic('Нет загруженных скриптов')}")

    text = (
        f"{_bold('📜 Загруженные скрипты')}\n\n"
        + "\n".join(lines)
    )
    return text, _build_main_keyboard()


async def action_show_recent_logs(client, callback: CallbackQuery, **kwargs) -> Tuple[str, Optional[InlineKeyboardMarkup]]:
    """Показать последние логи."""
    log_lines = []
    try:
        from config import Config
        logs = getattr(Config, "log_buffer", [])
        recent = logs[-15:] if len(logs) > 15 else logs
        for entry in recent:
            log_lines.append(f"  {_code(entry)}")
    except Exception:
        pass

    if not log_lines:
        log_lines.append("  {_italic('Логи пусты')}")

    text = (
        f"{_bold('🕐 Последние логи')}\n\n"
        + "\n".join(log_lines)
    )

    submenu = MENU_TREE.get("logs", {}).get("submenu", {})
    return text, _build_submenu_keyboard(submenu)


async def action_show_errors(client, callback: CallbackQuery, **kwargs) -> Tuple[str, Optional[InlineKeyboardMarkup]]:
    """Показать ошибки из логов."""
    error_lines = []
    try:
        from config import Config
        logs = getattr(Config, "log_buffer", [])
        errors = [l for l in logs if "ERROR" in l or "error" in l.lower()]
        recent = errors[-10:] if len(errors) > 10 else errors
        for entry in recent:
            error_lines.append(f"  {_code(entry)}")
    except Exception:
        pass

    if not error_lines:
        error_lines.append("  {_italic('Ошибок нет 🎉')}")

    text = (
        f"{_bold('❌ Ошибки')}\n\n"
        + "\n".join(error_lines)
    )

    submenu = MENU_TREE.get("logs", {}).get("submenu", {})
    return text, _build_submenu_keyboard(submenu)


async def action_clear_logs(client, callback: CallbackQuery, **kwargs) -> Tuple[str, Optional[InlineKeyboardMarkup]]:
    """Очистить логи."""
    try:
        from config import Config
        if hasattr(Config, "log_buffer"):
            Config.log_buffer.clear()
    except Exception:
        pass

    text = (
        f"{_bold('🗑️ Логи очищены')}\n\n"
        f"{_italic('Буфер логов сброшен.')}"
    )

    submenu = MENU_TREE.get("logs", {}).get("submenu", {})
    return text, _build_submenu_keyboard(submenu)


# ════════════════════════════════════════════════════════════════
# СЛОВАРЬ ACTION-ФУНКЦИЙ
# ════════════════════════════════════════════════════════════════
# Чтобы добавить новый action — добавь функцию выше и пропиши тут.

ACTIONS: Dict[str, callable] = {
    "show_stats": action_show_stats,
    "toggle_language": action_toggle_language,
    "toggle_notifications": action_toggle_notifications,
    "toggle_autosave": action_toggle_autosave,
    "list_scripts": action_list_scripts,
    "show_recent_logs": action_show_recent_logs,
    "show_errors": action_show_errors,
    "clear_logs": action_clear_logs,
}


# ════════════════════════════════════════════════════════════════
# CORE: РЕГИСТРАЦИЯ ХЕНДЛЕРОВ
# ════════════════════════════════════════════════════════════════

def register(client):
    """Зарегистрировать хендлеры меню."""

    # ── .menu — открыть главное меню ────────────────────────────
    @client.on_message(filters.command("menu", prefixes=".") & filters.me)
    async def menu_cmd(client, message: Message):
        try:
            await _send_main_menu(client, message)
        except Exception as e:
            logger.error(f"menu_cmd error: {e}")
            try:
                await message.edit_text(f"❌ Ошибка меню: {_code(str(e)[:100])}", parse_mode=ParseMode.HTML)
            except Exception:
                pass

    # ── .menu close — закрыть меню ──────────────────────────────
    @client.on_message(filters.command("menu", prefixes=".") & filters.me)
    async def menu_close_cmd(client, message: Message):
        args = message.text.split(maxsplit=1)
        if len(args) > 1 and args[1].strip().lower() == "close":
            user_id = message.from_user.id
            if user_id in _menu_messages:
                chat_id, msg_id = _menu_messages[user_id]
                try:
                    await client.delete_messages(chat_id, msg_id)
                except Exception:
                    pass
                del _menu_messages[user_id]
            try:
                await message.delete()
            except Exception:
                pass
            return
        # Если не "close" — обработка выше

    # ── Callback-хендлер — обработка нажатий кнопок ─────────────
    @client.on_callback_query(filters.regex(r"^menu:|^nav:|^custom:"))
    async def menu_callback(client, callback: CallbackQuery):
        await _handle_callback(client, callback)


# ════════════════════════════════════════════════════════════════
# CORE: ОТПРАВКА ГЛАВНОГО МЕНЮ
# ════════════════════════════════════════════════════════════════

async def _send_main_menu(client, message: Message):
    """Отправить главное меню (или заменить текущее сообщение)."""
    user_id = message.from_user.id
    now = datetime.now().strftime(TIME_FORMAT)

    text = (
        f"{_bold('🤖 Zaya — Главное меню')}\n\n"
        f" {_italic('Выберите раздел:')}"
    )

    keyboard = _build_main_keyboard()

    try:
        sent = await message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        _menu_messages[user_id] = (sent.chat.id, sent.id)
        # Сбросить навигационный стек
        _nav_stack[user_id] = []
    except Exception:
        # Если не можем edit (например, сообщение старое) — отправляем новое
        sent = await message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        _menu_messages[user_id] = (sent.chat.id, sent.id)


# ════════════════════════════════════════════════════════════════
# CORE: ОБРАБОТКА CALLBACK
# ════════════════════════════════════════════════════════════════

async def _handle_callback(client, callback: CallbackQuery):
    """Центральный роутер callback-запросов."""

    # ── 1. Проверка: не удалено ли сообщение ────────────────────
    if not callback.message:
        try:
            await callback.answer("⚠️ Сообщение не найдено", show_alert=True)
        except Exception:
            pass
        return

    user_id = callback.from_user.id
    data = callback.data  # например "menu:main", "nav:settings", "custom:show_stats"

    # ── 2. Проверка OWNER_ID (если задан) ───────────────────────
    owner_id = _get_owner_id()
    if owner_id is not None and user_id != owner_id:
        logger.warning(f"Menu: unauthorized callback from {user_id} (owner={owner_id})")
        try:
            await callback.answer("⛔ Доступ запрещён", show_alert=True)
        except Exception:
            pass
        return

    # ── 3. Cooldown — защита от флуда ───────────────────────────
    # ВНИМАНИЕ: Telegram банит за >30 callback/сек.
    # 1.5 сек между нажатиями — безопасный минимум.
    now = time.time()
    last_time = _last_callback_time.get(user_id, 0)
    elapsed = now - last_time

    if elapsed < COOLDOWN_SECONDS:
        remaining = COOLDOWN_SECONDS - elapsed
        try:
            await callback.answer(
                f"⏳ Подождите {remaining:.1f}с",
                show_alert=False,
                cache_time=int(remaining)
            )
        except Exception:
            pass
        return

    _last_callback_time[user_id] = now

    # ── 4. Роутинг по типу callback_data ────────────────────────
    try:
        if data == "menu:close":
            await _action_close(client, callback)

        elif data == "menu:main":
            await _action_main(client, callback)

        elif data == "menu:back":
            await _action_back(client, callback)

        elif data.startswith("nav:"):
            target_key = data[4:]  # убираем "nav:"
            await _action_navigate(client, callback, target_key)

        elif data.startswith("custom:"):
            action_name = data[7:]  # убираем "custom:"
            await _action_custom(client, callback, action_name)

        else:
            logger.warning(f"Menu: unknown callback_data: {data}")
            try:
                await callback.answer("❓ Неизвестное действие", show_alert=False)
            except Exception:
                pass

    except Exception as e:
        logger.error(f"Menu callback error: {e}")
        try:
            await callback.answer(
                f"⚠️ Ошибка: {str(e)[:50]}",
                show_alert=True
            )
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════
# CORE: ДЕЙСТВИЯ (ACTIONS)
# ════════════════════════════════════════════════════════════════

async def _action_close(client, callback: CallbackQuery):
    """Закрыть меню — удалить сообщение."""
    user_id = callback.from_user.id
    try:
        await callback.message.delete()
    except Exception:
        pass

    _menu_messages.pop(user_id, None)
    _nav_stack.pop(user_id, None)

    try:
        await callback.answer()
    except Exception:
        pass


async def _action_main(client, callback: CallbackQuery):
    """Вернуться в главное меню."""
    user_id = callback.from_user.id
    _nav_stack[user_id] = []

    text = (
        f"{_bold('🤖 Zaya — Главное меню')}\n\n"
        f" {_italic('Выберите раздел:')}"
    )

    try:
        await _safe_edit(callback, text, _build_main_keyboard())
    except Exception:
        pass

    try:
        await callback.answer("🏠 Главное меню")
    except Exception:
        pass


async def _action_back(client, callback: CallbackQuery):
    """Вернуться на уровень назад."""
    user_id = callback.from_user.id
    stack = _nav_stack.get(user_id, [])

    if len(stack) >= 2:
        # Убираем текущий уровень
        stack.pop()
        parent_key = stack[-1] if stack else None
    elif len(stack) == 1:
        # Возвращаемся в главное меню
        stack.clear()
        parent_key = None
    else:
        # Уже в корне — показать главное меню
        await _action_main(client, callback)
        return

    if parent_key is None:
        await _action_main(client, callback)
        return

    parent_item = MENU_TREE.get(parent_key)
    if parent_item and "submenu" in parent_item:
        icon = parent_item.get("icon", "")
        label = parent_item.get("label", parent_key)

        text = f"{_bold(f'{icon} {label}')}\n\n {_italic('Выберите подраздел:')}"

        try:
            await _safe_edit(callback, text, _build_submenu_keyboard(parent_item["submenu"]))
        except Exception:
            pass
    else:
        await _action_main(client, callback)

    try:
        await callback.answer("🔙 Назад")
    except Exception:
        pass


async def _action_navigate(client, callback: CallbackQuery, target_key: str):
    """Перейти во вложенное меню."""
    user_id = callback.from_user.id
    item = MENU_TREE.get(target_key)

    if not item:
        logger.warning(f"Menu: nav target '{target_key}' not found")
        try:
            await callback.answer("❓ Раздел не найден", show_alert=True)
        except Exception:
            pass
        return

    if "submenu" not in item:
        # Нет подменю — возможно это пункт с текстом
        text = item.get("text") or f"{_bold(item.get('label', target_key))}\n\n {_italic('Нет содержимого')}"
        try:
            await _safe_edit(callback, text, _build_main_keyboard())
        except Exception:
            pass
        try:
            await callback.answer()
        except Exception:
            pass
        return

    # Обновляем навигационный стек
    if user_id not in _nav_stack:
        _nav_stack[user_id] = []
    _nav_stack[user_id].append(target_key)

    icon = item.get("icon", "")
    label = item.get("label", target_key)

    text = f"{_bold(f'{icon} {label}')}\n\n {_italic('Выберите подраздел:')}"

    try:
        await _safe_edit(callback, text, _build_submenu_keyboard(item["submenu"]))
    except Exception:
        pass

    try:
        await callback.answer(f"{'📌' if icon else ''} {label}")
    except Exception:
        pass


async def _action_custom(client, callback: CallbackQuery, action_name: str):
    """Вызвать action-функцию."""
    action_func = ACTIONS.get(action_name)
    if not action_func:
        logger.warning(f"Menu: custom action '{action_name}' not found")
        try:
            await callback.answer("❓ Действие не найдено", show_alert=True)
        except Exception:
            pass
        return

    try:
        text, keyboard = await action_func(client, callback)

        if text is None:
            text = "—"

        try:
            await _safe_edit(callback, text, keyboard)
        except Exception:
            pass

        try:
            await callback.answer()
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Menu action '{action_name}' error: {e}")
        try:
            await callback.answer(f"⚠️ {str(e)[:50]}", show_alert=True)
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════
# УТИЛИТЫ
# ════════════════════════════════════════════════════════════════

def _get_owner_id() -> Optional[int]:
    """Получить owner_id из конфига бота. None = все разрешены."""
    try:
        from config import Config
        owner = getattr(Config, "owner_id", None)
        if owner is not None:
            return int(owner)
    except Exception:
        pass
    return None


async def _safe_edit(
    callback: CallbackQuery,
    text: str,
    keyboard: Optional[InlineKeyboardMarkup] = None,
):
    """
    Безопасное редактирование сообщения.
    Обрабатывает:
    - MessageNotModified (текст не изменился)
    - MessageToDelete (сообщение удалено)
    - FloodWait (слишком много запросов)
    - BadRequest (неверный запрос)
    """
    from pyrogram.errors import (
        MessageNotModified,
        MessageIdInvalid,
        MessageDeleteForbidden,
        BadRequest,
        FloodWait,
    )

    for attempt in range(3):  # до 3 попыток при FloodWait
        try:
            await callback.message.edit_text(
                text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            return  # успех

        except MessageNotModified:
            # Текст не изменился — это не ошибка, просто ничего не делаем
            return

        except (MessageIdInvalid, MessageDeleteForbidden):
            # Сообщение удалено внешне — тихий лог
            logger.debug("Menu: message was deleted externally")
            user_id = callback.from_user.id
            _menu_messages.pop(user_id, None)
            return

        except FloodWait as e:
            # Telegram просит подождать — ждём и пробуем снова
            wait_time = e.value + 0.5  # +0.5с запас
            logger.warning(f"Menu: FloodWait {e.value}s, sleeping {wait_time}s")
            await asyncio.sleep(wait_time)
            continue

        except BadRequest as e:
            if "message is not modified" in str(e).lower():
                return
            logger.debug(f"Menu: BadRequest: {e}")
            return

        except Exception as e:
            logger.error(f"Menu: unexpected edit error: {e}")
            return

    logger.warning(f"Menu: failed to edit after 3 attempts")


# ════════════════════════════════════════════════════════════════
# LIFECYCLE
# ════════════════════════════════════════════════════════════════

def on_load():
    print("[Menu] Loaded. .menu — открыть меню")


def on_unload():
    # Очистка состояния
    _last_callback_time.clear()
    _nav_stack.clear()
    _menu_messages.clear()
    print("[Menu] Unloaded")
