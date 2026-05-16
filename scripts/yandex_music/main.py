"""
Yandex Music - "Сейчас слушает"
Показывает текущий трек из Яндекс Музыки с обложкой и ссылкой.

Команды:
  .np            — показать текущий трек
  .np auto       — автоматически обновлять каждые 30 сек
  .np stop       — остановить автообновление
  .np token XXX  — установить OAuth токен

Как получить OAuth токен:
  1. Зайди в Яндекс (mail.yandex.ru) и авторизуйся
  2. Открой ЭТУ ссылку в ТОМ ЖЕ браузере:
     https://oauth.yandex.ru/authorize?response_type=token&client_id=23cabbbdc6cd418abb4b39c32c41185d
  3. Нажми "Разрешить"
  4. Браузер перейдёт на страницу, в адресной строке:
     ...verification_code#access_token=XXXXX&...
  5. Скопируй только XXXXX (без &...)
  6. .np token XXXXX

ВАЖНО: Если видишь ошибку 400 — ты не залогинен в Яндекс!
  Сначала зайди на mail.yandex.ru, потом открывай ссылку.

Токен привязан к аккаунту, работает со всех устройств (телефон, десктоп, браузер).
"""

import os
import asyncio
import logging
import tempfile

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(SCRIPT_DIR, "token.txt")

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


def _get_current_track(token):
    """Получить текущий играющий трек через библиотеку yandex-music."""
    try:
        from yandex_music import Client
        loop = asyncio.get_event_loop()

        def _fetch():
            client = Client(token).init()
            # Получаем список очередей
            queues = client.queues_list()
            if not queues:
                return None

            # Берём первую очередь (текущую)
            queue_id = queues[0].id
            if not queue_id:
                return None

            # Получаем треки из очереди
            queue = client.queue(queue_id)
            if not queue:
                return None

            tracks = queue.tracks
            if not tracks:
                return None

            # Определяем индекс текущего трека
            current_idx = getattr(queue, 'current_index', 0)
            if current_idx < 0 or current_idx >= len(tracks):
                return None

            item = tracks[current_idx]
            track = getattr(item, 'track', item)
            if not track:
                return None

            return track

        return loop.run_in_executor(None, _fetch)

    except Exception as e:
        logger.error(f"Yandex Music API error: {e}")
        return None


def _build_message(track):
    """Построить текст из данных трека. Возвращает (text, cover_url, track_id)."""
    artists = []
    for a in track.artists or []:
        name = getattr(a, 'name', '')
        if name:
            artists.append(name)
    artist_str = ", ".join(artists) if artists else "Неизвестный артист"

    title = getattr(track, 'title', 'Неизвестный трек') or 'Неизвестный трек'
    version = getattr(track, 'version', '')
    if version:
        title += f" ({version})"

    album = getattr(track, 'albums', [])
    album_title = album[0].title if album and hasattr(album[0], 'title') else ''
    album_id = album[0].id if album and hasattr(album[0], 'id') else ''
    track_id = getattr(track, 'id', '')

    if album_id and track_id:
        link = f"https://music.yandex.ru/album/{album_id}/track/{track_id}"
    else:
        link = "https://music.yandex.ru"

    # Обложка
    cover_url = None
    if album and hasattr(album[0], 'cover_uri') and album[0].cover_uri:
        cover_url = album[0].cover_uri.replace("%%", "300x300")
        if not cover_url.startswith("https://"):
            cover_url = "https://" + cover_url

    text = f"🎵 <b>{artist_str} — {title}</b>"
    if album_title:
        text += f"\n💿 <i>{album_title}</i>"
    text += f'\n<a href="{link}">Я.музыка</a>'

    return text, cover_url, track_id


def _download_file(url, path):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        with open(path, "wb") as f:
            f.write(resp.read())


async def _send_now_playing(client, message, token):
    """Отправить текущий трек с обложкой."""
    await message.edit_text("🎵 Загрузка...", parse_mode=ParseMode.HTML)

    track_future = _get_current_track(token)
    track = await track_future if asyncio.isfuture(track_future) else track_future

    if not track:
        await message.edit_text(
            "🔇 <b>Сейчас ничего не играет</b>\n\n"
            "Включи трек в Яндекс Музыке и попробуй снова.\n\n"
            "Убедись что OAuth токен правильный.\n"
            "Если токен устарел — получи новый.",
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

    track_future = _get_current_track(token)
    track = await track_future if asyncio.isfuture(track_future) else track_future

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

    track_id = getattr(track, 'id', '')
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
                    "1. Зайди на <b>mail.yandex.ru</b> (авторизуйся!)\n"
                    "2. Открой в том же браузере:\n"
                    "<code>https://oauth.yandex.ru/authorize?response_type=token&client_id=23cabbbdc6cd418abb4b39c32c41185d</code>\n"
                    "3. Нажми <b>Разрешить</b>\n"
                    "4. В адресной строке: <b>access_token=XXXXX</b>\n"
                    "5. <code>.np token XXXXX</code>\n\n"
                    "Ошибка 400? Ты не залогинен в Яндекс!",
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

            await message.edit_text("🎵 Проверяю...", parse_mode=ParseMode.HTML)

            track_future = _get_current_track(token)
            track = await track_future if asyncio.isfuture(track_future) else track_future

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
                "1. Зайди на <b>mail.yandex.ru</b> (авторизуйся!)\n"
                "2. Открой в том же браузере:\n"
                "<code>https://oauth.yandex.ru/authorize?response_type=token&client_id=23cabbbdc6cd418abb4b39c32c41185d</code>\n"
                "3. Нажми <b>Разрешить</b>\n"
                "4. В адресной строке: <b>access_token=XXXXX</b>\n"
                "5. <code>.np token XXXXX</code>\n\n"
                "Ошибка 400? Ты не залогинен в Яндекс!",
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
