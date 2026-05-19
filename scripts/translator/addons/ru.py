"""Translator addon: Russian (.tra)
Reply to a message to translate it to Russian.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from scripts._utils import safe_edit

from deep_translator import GoogleTranslator


def register(client):
    from pyrogram import filters
    from pyrogram.enums import ParseMode
    from pyrogram.types import Message
    import asyncio

    @client.on_message(filters.command("tra", prefixes=".") & filters.reply & filters.me)
    async def tra_handler(client, message: Message):
        reply = message.reply_to_message
        if not reply:
            await safe_edit(message, "Ответьте на сообщение для перевода.")
            return

        text = reply.text or reply.caption
        if not text:
            await safe_edit(message, "Нет текста для перевода.")
            return

        await safe_edit(message, "Перевод...")

        try:
            loop = asyncio.get_running_loop()
            translated = await loop.run_in_executor(
                None,
                lambda: GoogleTranslator(source="auto", target="ru").translate(text)
            )

            await safe_edit(message,
                f"<b>Перевод (RU):</b>\n\n<code>{translated}</code>",
                parse_mode=ParseMode.HTML
            )

        except Exception as e:
            await safe_edit(message, f"Ошибка перевода: {e}")


def on_load():
    print("[Translator/RU] Addon loaded. .tra")


def on_unload():
    print("[Translator/RU] Addon unloaded")
