"""
Yandex Music — "Сейчас слушает"
Показывает текущий трек из Яндекс Музыки с обложкой и ссылкой.

Команды:
  .np          — показать текущий трек
  .np auto     — автоматически обновлять каждые 30 сек
  .np stop     — остановить автообновление
  .np token XXX — установить токен

Токен берётся из:
  1. Файла scripts/yandex_music/token.txt
  2. Или через команду .np token XXX

Как получить токен:
  F12 → Network → любой запрос к api.music.yandex.net → Authorization: OAuth XXX
"""

import os
import json
import asyncio
import logging
import urllib.request
import urllib.error
import tempfile

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(SCRIPT_DIR, "token.txt")

API_BASE = "https://api.music.yandex.net"

logger = logging.getLogger("userbot.yandex_music")

# Состояние
_auto_enabled = False
_auto_task = None
_last_msg = None        # (chat_id, msg_id) для редактирования
_last_track_id = None   # чтобы не редактировать если трек не изменился
_no_music_shown = False  # флаг что показали "ничего не играет"


# ════════════════════════════════════════════════════════════════
# ТОКЕН
# ════════════════════════════════════════════════════════════════

def _get_token():
    """Прочитать токен из файла."""
    try:
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                token = f.read().strip()
                if token and not token.startswith("вставь"):
                    return token
    except Exception:
        pass
    return None


def _save_token(token):
    """Сохранить токен в файл."""
    os.makedirs(SCRIPT_DIR, exist_ok=True)
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(token.strip())


# ════════════════════════════════════════════════════════════════
# API ЯНДЕКС МУЗЫКИ
# ════════════════════════════════════════════════════════════════

def _api_request(path, token, timeout=10):
    """GET запрос к API Яндекс Музыки."""
    url = f"{API_BASE}{path}?oauth_token={token}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


async def _get_current_track(token):
    """
    Получить текущий играющий трек.
    Возвращает dict с track info или None если ничего не играет.
    """
    loop = asyncio.get_event_loop()

    try:
        # Получаем список очередей
        queues_data = await loop.run_in_executor(
            None, _api_request, "/queues", token
        )

        queues = queues_data.get("queues", [])
        if not queues:
            return None

        # Берём первую очередь (текущая)
        queue_id = queues[0].get("id", "")
        if not queue_id:
            return None

        # Получаем детали очереди
        queue_data = await loop.run_in_executor(
            None, _api_request, f"/queues/{queue_id}", token
        )

        tracks = queue_data.get("tracks", [])
        current_idx = queue_data.get("currentPlayingIndex", -1)

        if not tracks or current_idx < 0 or current_idx >= len(tracks):
            return None

        track = tracks[current_idx].get("track", {})
        if not track:
            return None

        return track

    except urllib.error.HTTPError as e:
        if e.code == 401:
            logger.error("Yandex Music: токен невалиден или истёк")
        elif e.code == 403:
            logger.error("Yandex Music: доступ запрещён")
        else:
            logger.error(f"Yandex Music API error: {e.code}")
    except Exception as e:
        logger.error(f"Yandex Music request error: {e}")

    return None


def _build_message(track):
    """
    Построить текст сообщения из данных трека.
    Возвращает (text, cover_url, track_id).
    """
    # Артисты
    artists = []
    for a in track.get("artists", []):
        name = a.get("name", "")
        if name:
            artists.append(name)
    artist_str = ", ".join(artists) if artists else "Неизвестный артист"

    # Название трека
    title = track.get("title", "Неизвестный трек")
    version = track.get("version", "")
    if version:
        title += f" ({version})"

    # Альбом
    album_title = track.get("album", {}).get("title", "")
    album_id = track.get("album", {}).get("id", "")

    # ID трека для ссылки
    track_id = track.get("id", "")

    # Ссылка на Яндекс Музыку
    if album_id and track_id:
        link = f"https://music.yandex.ru/album/{album_id}/track/{track_id}"
    else:
        link = "https://music.yandex.ru"

    # Обложка
    cover_uri = track.get("album", {}).get("coverUri", "")
    cover_url = None
    if cover_uri:
        # coverUri выглядит как "avatars.yandex.net/get-music-content/..."
        cover_url = f"https://{cover_uri.replace('%%', '300x300')}"

    # Текст сообщения
    text = f"🎵 <b>{artist_str} — {title}</b>"
    if album_title:
        text += f"\n💿 <i>{album_title}</i>"
    # Кликабельная ссылка "Я.музыка"
    text += f'\n<a href="{link}">Я.музыка</a>'

    return text, cover_url, track_id


# ════════════════════════════════════════════════════════════════
# ОТПРАВКА / РЕДАКТИРОВАНИЕ СООБЩЕНИЯ
# ════════════════════════════════════════════════════════════════

async def _send_now_playing(client, message: Message, token):
    """Отправить или показать текущий трек."""
    track = await _get_current_track(token)

    if not track:
        await message.edit_text(
            "🔇 <b>Сейчас ничего не играет</b>\n\n"
            "Включи трек в Яндекс Музыке и попробуй снова.",
            parse_mode=ParseMode.HTML,
        )
        return

    text, cover_url, track_id = _build_message(track)

    try:
        if cover_url:
            # Скачиваем обложку и отправляем как фото
            tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            tmp_path = tmp.name
            tmp.close()

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, _download_file, cover_url, tmp_path
            )

            await message.delete()
            await client.send_photo(
                chat_id=message.chat.id,
                photo=tmp_path,
                caption=text,
                parse_mode=ParseMode.HTML,
            )

            # Удаляем временный файл
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        else:
            await message.edit_text(text, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"Send now_playing error: {e}")
        # Fallback — текст без фото
        try:
            await message.edit_text(text, parse_mode=ParseMode.HTML)
        except Exception:
            pass


async def _update_now_playing(client, token):
    """Автообновление — редактирует сообщение если трек изменился."""
    global _last_msg, _last_track_id, _no_music_shown

    if not _last_msg:
        return

    chat_id, msg_id = _last_msg
    track = await _get_current_track(token)

    if not track:
        # Ничего не играет
        if not _no_music_shown:
            try:
                await client.edit_message_text(
                    chat_id, msg_id,
                    "🔇 <b>Сейчас ничего не играет</b>",
                    parse_mode=ParseMode.HTML,
                )
                _no_music_shown = True
                _last_track_id = None
            except Exception:
                pass
        return

    track_id = track.get("id", "")

    # Трек не изменился — ничего не делаем
    if track_id == _last_track_id:
        return

    # Трек изменился — обновляем сообщение
    text, cover_url, new_track_id = _build_message(track)
    _last_track_id = new_track_id
    _no_music_shown = False

    try:
        # Пытаемся отредактировать текст (без фото)
        await client.edit_message_text(
            chat_id, msg_id,
            text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as e:
        # Если сообщение с фото — edit_message_text не сработает
        # Отправляем новое сообщение
        logger.debug(f"Edit failed, sending new: {e}")
        try:
            new_msg = await client.send_message(
                chat_id, text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            _last_msg = (chat_id, new_msg.id)
            # Удаляем старое
            try:
                await client.delete_messages(chat_id, msg_id)
            except Exception:
                pass
        except Exception as e2:
            logger.error(f"Auto-update failed: {e2}")


def _download_file(url, path):
    """Скачать файл по URL."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        with open(path, "wb") as f:
            f.write(resp.read())


# ════════════════════════════════════════════════════════════════
# АВТООБНОВЛЕНИЕ
# ════════════════════════════════════════════════════════════════

async def _auto_loop(client, token):
    """Цикл автообновления каждые 30 секунд."""
    global _last_msg

    while True:
        try:
            await asyncio.sleep(30)
            if _last_msg and token:
                await _update_now_playing(client, token)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.debug(f"Auto-update error: {e}")


# ════════════════════════════════════════════════════════════════
# ХЕНДЛЕРЫ
# ════════════════════════════════════════════════════════════════

def register(client):

    @client.on_message(filters.command("np", prefixes=".") & filters.me)
    async def np_handler(client, message: Message):
        global _auto_enabled, _auto_task, _last_msg, _last_track_id, _no_music_shown

        args = message.text.split(maxsplit=1)
        action = args[1].strip().lower() if len(args) > 1 else ""

        # ── .np token XXX ──────────────────────────────────────
        if action.startswith("token "):
            token = action[6:].strip()
            if not token:
                await message.edit_text(
                    "❌ Укажи токен:\n<code>.np token XXXXX</code>",
                    parse_mode=ParseMode.HTML,
                )
                return
            _save_token(token)
            await message.edit_text(
                "✅ Токен сохранён!\n\n"
                "Теперь используй <code>.np</code> для показа текущего трека.",
                parse_mode=ParseMode.HTML,
            )
            return

        # ── .np auto ───────────────────────────────────────────
        if action == "auto":
            token = _get_token()
            if not token:
                await message.edit_text(
                    "❌ Токен не установлен!\n\n"
                    "<b>Как получить токен:</b>\n"
                    "1. Открой <a href='https://music.yandex.ru'>music.yandex.ru</a>\n"
                    "2. Зайди в свой аккаунт\n"
                    "3. F12 → вкладка <b>Network</b> (Сеть)\n"
                    "4. Включи трек\n"
                    "5. Найди запрос к <code>api.music.yandex.net</code>\n"
                    "6. В Headers → Authorization: OAuth <b>XXXXX</b>\n"
                    "7. Скопируй XXXXX\n\n"
                    "<code>.np token XXXXX</code> — сохранить токен",
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                return

            if _auto_enabled:
                await message.edit_text(
                    "⚠️ Автообновление уже включено!\n"
                    "<code>.np stop</code> — остановить",
                    parse_mode=ParseMode.HTML,
                )
                return

            # Останавливаем предыдущую задачу
            if _auto_task:
                _auto_task.cancel()

            # Получаем текущий трек и отправляем
            track = await _get_current_track(token)
            if not track:
                await message.edit_text(
                    "🔇 Сейчас ничего не играет.\n\n"
                    "Включи трек и отправь <code>.np auto</code> снова.",
                    parse_mode=ParseMode.HTML,
                )
                return

            text, cover_url, track_id = _build_message(track)
            _last_track_id = track_id
            _no_music_shown = False

            try:
                sent = await message.edit_text(
                    text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                _last_msg = (sent.chat.id, sent.id)
            except Exception:
                sent = await message.reply_text(
                    text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                _last_msg = (sent.chat.id, sent.id)

            _auto_enabled = True
            _auto_task = asyncio.create_task(_auto_loop(client, token))

            await client.send_message(
                message.chat.id,
                "✅ Автообновление включено!\n"
                f"Трек будет обновляться каждые 30 сек.\n\n"
                "<code>.np stop</code> — остановить",
                parse_mode=ParseMode.HTML,
            )
            return

        # ── .np stop ───────────────────────────────────────────
        if action == "stop":
            if _auto_task:
                _auto_task.cancel()
                _auto_task = None
            _auto_enabled = False
            _last_msg = None
            _last_track_id = None
            _no_music_shown = False
            await message.edit_text(
                "⏹ Автообновление выключено",
                parse_mode=ParseMode.HTML,
            )
            return

        # ── .np (без аргументов) ───────────────────────────────
        token = _get_token()
        if not token:
            await message.edit_text(
                "❌ Токен не установлен!\n\n"
                "<b>Как получить токен:</b>\n"
                "1. Открой <a href='https://music.yandex.ru'>music.yandex.ru</a>\n"
                "2. Зайди в свой аккаунт\n"
                "3. F12 → вкладка <b>Network</b> (Сеть)\n"
                "4. Включи трек\n"
                "5. Найди запрос к <code>api.music.yandex.net</code>\n"
                "6. В Headers → Authorization: OAuth <b>XXXXX</b>\n"
                "7. Скопируй XXXXX\n\n"
                "<code>.np token XXXXX</code> — сохранить токен",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            return

        await _send_now_playing(client, message, token)


def on_load():
    print("[YandexMusic] Loaded. .np — currently playing, .np auto — auto-update")


def on_unload():
    global _auto_enabled, _auto_task
    _auto_enabled = False
    if _auto_task:
        _auto_task.cancel()
        _auto_task = None
    print("[YandexMusic] Unloaded")
