"""Translator addon: Belarusian (.trb)
Reply to a message or provide text to translate to Belarusian.
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

    @client.on_message(filters.command("trb", prefixes=".") & filters.me)
    async def trb_handler(client, message: Message):
        args = message.text.split(maxsplit=1)
        text = None

        if message.reply_to_message:
            text = message.reply_to_message.text or message.reply_to_message.caption

        if not text and len(args) > 1:
            text = args[1]

        if not text:
            await safe_edit(message,
                "<code>.trb</code> (адказ на паведамленне) альбо <code>.trb тэкст</code>",
                parse_mode=ParseMode.HTML
            )
            return

        await safe_edit(message, "Пераклад...")

        try:
            loop = asyncio.get_running_loop()
            translated = await loop.run_in_executor(
                None,
                lambda: GoogleTranslator(source="auto", target="be").translate(text)
            )

            await safe_edit(message,
                f"<b>Пераклад (BE):</b>\n\n<code>{translated}</code>",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            await safe_edit(message, f"Памылка: {e}")


def on_load():
    print("[Translator/BE] Addon loaded. .trb")


def on_unload():
    print("[Translator/BE] Addon unloaded")
