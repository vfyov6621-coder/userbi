"""Translator addon: Belarusian (.trb)
Reply to a message or provide text to translate to Belarusian.
"""

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
            await message.edit_text(
                "<code>.trb</code> (адказ на паведамленне) альбо <code>.trb тэкст</code>",
                parse_mode=ParseMode.HTML
            )
            return

        await message.edit_text("Пераклад...")

        try:
            loop = asyncio.get_event_loop()
            translated = await loop.run_in_executor(
                None,
                lambda: GoogleTranslator(source="auto", target="be").translate(text)
            )

            await message.edit_text(
                f"<b>Пераклад (BE):</b>\n\n<code>{translated}</code>",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            await message.edit_text(f"Памылка: {e}")


def on_load():
    print("[Translator/BE] Addon loaded. .trb")


def on_unload():
    print("[Translator/BE] Addon unloaded")
