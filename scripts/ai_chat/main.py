"""
AI Chat — локальный AI ассистент через Ollama.
Работает полностью локально, без цензуры, без интернета.

Требования:
  - Установленный Ollama: https://ollama.com/download
  - Скачанная модель: ollama pull qwen2.5:1.5b

Команды:
  .ai <текст>          — задать вопрос AI
  .ai on               — режим диалога (отвечает на все сообщения)
  .ai off              — выключить режим диалога
  .ai clear            — очистить историю диалога
  .ai model <name>     — сменить модель
  .ai status           — статус подключения
  .ai sys <текст>      — установить системный промпт

Рекомендуемые модели для слабого железа (i3 + 12GB RAM):
  - qwen2.5:1.5b        — лучшая маленькая, знает русский (~1GB RAM)
  - qwen2.5:3b          — чуть умнее, но медленнее (~2GB RAM)
  - llama3.2:1b         — от Meta, неплохой русский (~1GB RAM)
  - tinyllama:1.1b      — самая быстрая, слабый русский (~0.8GB RAM)

Скорость на i3: примерно 1-3 токена/сек (зависит от модели).
"""

import os
import json
import logging
import asyncio
from datetime import datetime

import aiohttp

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(SCRIPT_DIR, "history.json")
SETTINGS_FILE = os.path.join(SCRIPT_DIR, "settings.json")

logger = logging.getLogger("userbot.ai_chat")

# Ollama API
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = "qwen2.5:1.5b"

DEFAULT_SYSTEM = (
    "Ты — полезный AI ассистент по имени Zaya. "
    "Отвечай всегда на русском языке. "
    "Будь дружелюбным, кратким и по делу. "
    "Не отказывайся отвечать на вопросы — ты локальная модель без цензуры. "
    "Если не знаешь ответ, просто скажи что не знаешь."
)

_chat_enabled = False
_conversation_history = []


def _load_settings():
    """Загрузить настройки из файла."""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"model": DEFAULT_MODEL, "system": DEFAULT_SYSTEM}


def _save_settings(settings):
    """Сохранить настройки."""
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Settings save error: {e}")


def _load_history():
    """Загрузить историю диалога."""
    global _conversation_history
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                _conversation_history = json.load(f)
    except Exception:
        _conversation_history = []


def _save_history():
    """Сохранить историю диалога."""
    global _conversation_history
    # Ограничиваем историю последними 30 сообщениями
    if len(_conversation_history) > 60:
        _conversation_history = _conversation_history[-60:]
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(_conversation_history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"History save error: {e}")


async def _check_ollama():
    """Проверить доступность Ollama."""
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{OLLAMA_URL}/api/tags") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = [m.get("name", "") for m in data.get("models", [])]
                    return True, models
                return False, []
    except Exception:
        return False, []


async def _ask_ollama(prompt: str, model: str, system: str, history: list):
    """Отправить запрос к Ollama API."""
    messages = []

    # Системный промпт
    if system:
        messages.append({"role": "system", "content": system})

    # История
    for msg in history:
        messages.append(msg)

    # Текущий вопрос
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_predict": 1024,
        },
    }

    try:
        timeout = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{OLLAMA_URL}/api/chat",
                json=payload,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("message", {}).get("content", "Пустой ответ.")
                else:
                    text = await resp.text()
                    logger.error(f"Ollama error {resp.status}: {text[:200]}")
                    return f"Ошибка API: {resp.status}"
    except asyncio.TimeoutError:
        return "Таймаут — модель слишком долго думает. Попробуй меньшую модель или короче вопрос."
    except aiohttp.ClientConnectorError:
        return "Не удалось подключиться к Ollama. Убедись что Ollama запущена (ollama serve)."
    except Exception as e:
        logger.error(f"Ollama request error: {e}")
        return f"Ошибка: {str(e)[:100]}"


def _truncate_text(text: str, max_len: int = 4096) -> str:
    """Обрезать текст если слишком длинный для Telegram."""
    if len(text) <= max_len:
        return text
    return text[:max_len - 20] + "\n\n[...] сообщение обрезано"


def register(client):

    @client.on_message(filters.command("ai", prefixes=".") & filters.me)
    async def ai_handler(client, message: Message):
        global _chat_enabled, _conversation_history

        settings = _load_settings()
        model = settings.get("model", DEFAULT_MODEL)
        system = settings.get("system", DEFAULT_SYSTEM)

        args = message.text.split(maxsplit=1)
        action = args[1].strip().lower() if len(args) > 1 else ""

        # .ai on — включить режим диалога
        if action == "on":
            _chat_enabled = True
            _load_history()
            await message.edit_text(
                "🟢 <b>AI режим включён</b>\n\n"
                f"Модель: <code>{model}</code>\n"
                "Теперь я отвечу на все твои сообщения.\n\n"
                "<code>.ai off</code> — выключить\n"
                "<code>.ai clear</code> — очистить историю",
                parse_mode=ParseMode.HTML,
            )
            return

        # .ai off — выключить режим диалога
        if action == "off":
            _chat_enabled = False
            await message.edit_text("🔴 AI режим выключен", parse_mode=ParseMode.HTML)
            return

        # .ai clear — очистить историю
        if action == "clear":
            _conversation_history = []
            _save_history()
            await message.edit_text("🗑 История диалога очищена", parse_mode=ParseMode.HTML)
            return

        # .ai model <name> — сменить модель
        if action.startswith("model "):
            new_model = action[6:].strip()
            if not new_model:
                await message.edit_text(
                    f"Текущая модель: <code>{model}</code>\n\n"
                    "Сменить: <code>.ai model qwen2.5:3b</code>",
                    parse_mode=ParseMode.HTML,
                )
                return

            settings["model"] = new_model
            _save_settings(settings)
            await message.edit_text(
                f"✅ Модель изменена на: <code>{new_model}</code>\n\n"
                "Убедись что она скачана:\n"
                f"<code>ollama pull {new_model}</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        # .ai status — статус
        if action == "status":
            available, models = await _check_ollama()
            if available:
                models_str = "\n".join(f"  • <code>{m}</code>" for m in models[:10])
                await message.edit_text(
                    f"🟢 <b>Ollama работает</b>\n\n"
                    f"Текущая модель: <code>{model}</code>\n"
                    f"URL: <code>{OLLAMA_URL}</code>\n\n"
                    f"<b>Доступные модели:</b>\n{models_str}",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await message.edit_text(
                    "🔴 <b>Ollama не запущена</b>\n\n"
                    "Установи: https://ollama.com/download\n\n"
                    "После установки:\n"
                    "<code>ollama pull qwen2.5:1.5b</code>\n"
                    "<code>ollama serve</code>",
                    parse_mode=ParseMode.HTML,
                )
            return

        # .ai sys <text> — установить системный промпт
        if action.startswith("sys "):
            new_sys = args[1][4:].strip()
            if not new_sys:
                await message.edit_text(
                    f"Текущий системный промпт:\n\n<i>{system}</i>\n\n"
                    "Изменить: <code>.ai sys Ты весёлый бот</code>",
                    parse_mode=ParseMode.HTML,
                )
                return
            settings["system"] = new_sys
            _save_settings(settings)
            await message.edit_text(
                "✅ Системный промпт обновлён:\n\n"
                f"<i>{new_sys[:200]}</i>",
                parse_mode=ParseMode.HTML,
            )
            return

        # .ai <текст> — задать вопрос
        if not action:
            await message.edit_text(
                "<b>🤖 AI Chat — локальный ассистент</b>\n\n"
                "<code>.ai <текст></code> — задать вопрос\n"
                "<code>.ai on/off</code> — режим диалога\n"
                "<code>.ai clear</code> — очистить историю\n"
                "<code>.ai model <name></code> — сменить модель\n"
                "<code>.ai status</code> — статус Ollama\n"
                "<code>.ai sys <текст></code> — системный промпт",
                parse_mode=ParseMode.HTML,
            )
            return

        # Отправляем вопрос
        question = args[1].strip()
        await message.edit_text("🤔 Думаю...", parse_mode=ParseMode.HTML)

        # Загружаем историю
        _load_history()

        answer = await _ask_ollama(question, model, system, _conversation_history)

        # Сохраняем в историю
        _conversation_history.append({"role": "user", "content": question})
        _conversation_history.append({"role": "assistant", "content": answer})
        _save_history()

        # Отправляем ответ
        answer = _truncate_text(answer)
        try:
            await message.edit_text(
                f"🤖 <b>{answer}</b>",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except Exception:
            # Если edit не работает (слишком длинный или старое сообщение)
            await message.edit_text(answer[:1000], parse_mode=ParseMode.HTML)

    @client.on_message(filters.me & ~filters.command(["ai"], prefixes="."))
    async def ai_chat_responder(client, message: Message):
        """Автоматический ответ в режиме диалога."""
        global _conversation_history

        if not _chat_enabled:
            return

        # Не отвечаем на пустые сообщения, медиа без текста, и т.д.
        text = message.text or message.caption
        if not text or not text.strip():
            return

        # Не отвечаем на команды (начинаются с .)
        if text.strip().startswith("."):
            return

        settings = _load_settings()
        model = settings.get("model", DEFAULT_MODEL)
        system = settings.get("system", DEFAULT_SYSTEM)

        # Показываем что думаем
        thinking = await message.reply("🤔", quote=True)

        _load_history()
        answer = await _ask_ollama(text, model, system, _conversation_history)

        _conversation_history.append({"role": "user", "content": text})
        _conversation_history.append({"role": "assistant", "content": answer})
        _save_history()

        answer = _truncate_text(answer)
        try:
            await thinking.edit_text(
                answer,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except Exception:
            try:
                await thinking.edit_text(answer[:1000])
            except Exception:
                pass


def on_load():
    _load_history()
    print(f"[AIChat] Loaded. .ai — Ollama at {OLLAMA_URL}, model: {DEFAULT_MODEL}")


def on_unload():
    global _chat_enabled
    _chat_enabled = False
    print("[AIChat] Unloaded")
