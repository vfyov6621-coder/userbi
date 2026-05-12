"""
Yandex Music - "Сейчас слушает"
Показывает текущий трек из Яндекс Музыки с обложкой и ссылкой.

Команды:
  .np          - показать текущий трек
  .np auto     - автоматически обновлять каждые 30 сек
  .np stop     - остановить автообновление
  .np token XXX - установить sessar токен

Как получить токен:
  F12 -> Network -> включи трек -> кликни на запрос к api.music.yandex.ru
  -> Headers -> Request Headers -> Cookie -> найди sessar=XXX
  Или: правый клик на запрос -> Copy as cURL -> найди sessar=
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

_auto_enabled = False
_auto_task = None
_last_msg = None
_last_track_id = None
_no_music_shown = False


def _get_token():
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
    os.makedirs(SCRIPT_DIR, exist_ok=True)
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(token.strip())


def _api_get(path, token, timeout=10):
    """GET запрос к API Яндекс Музыки через sessar cookie."""
    url = f"{API_BASE}{path}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Cookie": f"sessar={token}",
        "Origin": "https://music.yandex.ru",
        "Referer": "https://music.yandex.ru/",
        "X-Yandex-Music-Client": "YandexMusicWebNext/1.0.0",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


async def _get_current_track(token):
    """Получить текущий играющий трек. Пробуем несколько эндпоинтов."""
    loop = asyncio.get_event_loop()

    # Метод 1: /queues
    try:
        queues_data = await loop.run_in_executor(
            None, _api_get, "/queues", token
        )
        queues = queues_data.get("queues", [])
        if queues:
            queue_id = queues[0].get("id", "")
            if queue_id:
                queue_data = await loop.run_in_executor(
                    None, _api_get, f"/queues/{queue_id}", token
                )
                tracks = queue_data.get("tracks", [])
                current_idx = queue_data.get("currentPlayingIndex", -1)
                if tracks and 0 <= current_idx < len(tracks):
                    track = tracks[current_idx].get("track", {})
                    if track:
                        return track
    except urllib.error.HTTPError as e:
        logger.error(f"Yandex Music API error: {e.code}")
    except Exception as e:
        logger.debug(f"Queues method failed: {e}")

    # Метод 2: /player/queue
    try:
        player_data = await loop.run_in_executor(
            None, _api_get, "/player/queue", token
        )
        if player_data:
            queue = player_data.get("queue", {})
            tracks = queue.get("tracks", []) if queue else []
            current_idx = player_data.get("currentIndex", -1)
            if tracks and 0 <= current_idx < len(tracks):
                track = tracks[current_idx].get("track", {})
                if track:
                    return track
    except Exception as e:
        logger.debug(f"Player method failed: {e}")

    return None


def _build_message(track):
    """Построить текст из данных трека. Возвращает (text, cover_url, track_id)."""
    artists = []
    for a in track.get("artists", []):
        name = a.get("name", "")
        if name:
            artists.append(name)
    artist_str = ", ".join(artists) if artists else "Неизвестный артист"

    title = track.get("title", "Неизвестный трек")
    version = track.get("version", "")
    if version:
        title += f" ({version})"

    album_title = track.get("album", {}).get("title", "")
    album_id = track.get("album", {}).get("id", "")
    track_id = track.get("id", "")

    if album_id and track_id:
        link = f"https://music.yandex.ru/album/{album_id}/track/{track_id}"
    else:
        link = "https://music.yandex.ru"

    cover_uri = track.get("album", {}).get("coverUri", "")
    cover_url = None
    if cover_uri:
        cover_url = f"https://{cover_uri.replace('%%', '300x300')}"

    text = f"🎵 <b>{artist_str} — {title}</b>"
    if album_title:
        text += f"\n💿 <i>{album_title}</i>"
    text += f'\n<a href="{link}">Я.музыка</a>'

    return text, cover_url, track_id


def _download_file(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        with open(path, "wb") as f:
            f.write(resp.read())


async def _send_now_playing(client, message, token):
    """Отправить текущий трек с обложкой."""
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
            tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            tmp_path = tmp.name
            tmp.close()
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _download_file, cover_url, tmp_path)

            await message.delete()
            await client.send_photo(
                chat_id=message.chat.id,
                photo=tmp_path,
                caption=text,
                parse_mode=ParseMode.HTML,
            )
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        else:
            await message.edit_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Send error: {e}")
        try:
            await message.edit_text(text, parse_mode=ParseMode.HTML)
        except Exception:
            pass


async def _update_now_playing(client, token):
    """Автообновление сообщения."""
    global _last_msg, _last_track_id, _no_music_shown

    if not _last_msg:
        return

    chat_id, msg_id = _last_msg
    track = await _get_current_track(token)

    if not track:
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
    if track_id == _last_track_id:
        return

    text, cover_url, new_track_id = _build_message(track)
    _last_track_id = new_track_id
    _no_music_shown = False

    try:
        await client.edit_message_text(
            chat_id, msg_id, text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception:
        try:
            new_msg = await client.send_message(
                chat_id, text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            _last_msg = (chat_id, new_msg.id)
            try:
                await client.delete_messages(chat_id, msg_id)
            except Exception:
                pass
        except Exception as e2:
            logger.error(f"Auto-update failed: {e2}")


async def _auto_loop(client, token):
    """Цикл автообновления."""
    while True:
        try:
            await asyncio.sleep(30)
            if _last_msg and token:
                await _update_now_playing(client, token)
        except asyncio.CancelledError:
            break
        except Exception:
            pass


def register(client):

    @client.on_message(filters.command("np", prefixes=".") & filters.me)
    async def np_handler(client, message: Message):
        global _auto_enabled, _auto_task, _last_msg, _last_track_id, _no_music_shown

        args = message.text.split(maxsplit=1)
        action = args[1].strip().lower() if len(args) > 1 else ""

        # .np token XXX
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

        # .np auto
        if action == "auto":
            token = _get_token()
            if not token:
                await message.edit_text(
                    "❌ Токен не установлен!\n\n"
                    "1. Открой <a href='https://music.yandex.ru'>music.yandex.ru</a>\n"
                    "2. F12 → вкладка <b>Network</b>\n"
                    "3. Включи трек\n"
                    "4. Кликни на запрос к <code>api.music.yandex.net</code>\n"
                    "5. Найди <b>Cookie</b> → <code>sessar=XXX</code>\n"
                    "6. Скопируй XXX\n\n"
                    "<code>.np token XXX</code>",
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                return

            if _auto_enabled:
                await message.edit_text(
                    "⚠️ Уже включено!\n<code>.np stop</code> — остановить",
                    parse_mode=ParseMode.HTML,
                )
                return

            if _auto_task:
                _auto_task.cancel()

            track = await _get_current_track(token)
            if not track:
                await message.edit_text(
                    "🔇 Сейчас ничего не играет.\nВключи трек и попробуй снова.",
                    parse_mode=ParseMode.HTML,
                )
                return

            text, cover_url, track_id = _build_message(track)
            _last_track_id = track_id
            _no_music_shown = False

            try:
                sent = await message.edit_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                _last_msg = (sent.chat.id, sent.id)
            except Exception:
                sent = await message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                _last_msg = (sent.chat.id, sent.id)

            _auto_enabled = True
            _auto_task = asyncio.create_task(_auto_loop(client, token))

            await client.send_message(
                message.chat.id,
                "✅ Автообновление включено (каждые 30 сек)\n"
                "<code>.np stop</code> — остановить",
                parse_mode=ParseMode.HTML,
            )
            return

        # .np stop
        if action == "stop":
            if _auto_task:
                _auto_task.cancel()
                _auto_task = None
            _auto_enabled = False
            _last_msg = None
            _last_track_id = None
            _no_music_shown = False
            await message.edit_text("⏹ Автообновление выключено", parse_mode=ParseMode.HTML)
            return

        # .np (без аргументов)
        token = _get_token()
        if not token:
            await message.edit_text(
                "❌ Токен не установлен!\n\n"
                "1. Открой <a href='https://music.yandex.ru'>music.yandex.ru</a>\n"
                "2. F12 → вкладка <b>Network</b>\n"
                "3. Включи трек\n"
                "4. Кликни на запрос к <code>api.music.yandex.net</code>\n"
                "5. Найди <b>Cookie</b> → <code>sessar=XXX</code>\n"
                "6. Скопируй XXX\n\n"
                "<code>.np token XXX</code>",
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            return

        await _send_now_playing(client, message, token)


def on_load():
    print("[YandexMusic] Loaded. .np — currently playing")


def on_unload():
    global _auto_enabled, _auto_task
    _auto_enabled = False
    if _auto_task:
        _auto_task.cancel()
        _auto_task = None
    print("[YandexMusic] Unloaded")
