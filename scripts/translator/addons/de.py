"""Translator addon: German (.trd)
Reply to a message to translate it to German.
"""

from deep_translator import GoogleTranslator


def register(client):
    from pyrogram import filters
    from pyrogram.enums import ParseMode
    from pyrogram.types import Message
    import asyncio

    @client.on_message(filters.command("trd", prefixes=".") & filters.me)
    async def trd_handler(client, message: Message):
        args = message.text.split(maxsplit=1)
        text = None

        if message.reply_to_message:
            text = message.reply_to_message.text or message.reply_to_message.caption

        if not text and len(args) > 1:
            text = args[1]

        if not text:
            await message.edit_text(
                "<code>.trd</code> (ответ на соо) или <code>.trd текст</code>",
                parse_mode=ParseMode.HTML
            )
            return

        await message.edit_text("Ubersetzung...")

        try:
            loop = asyncio.get_event_loop()
            translated = await loop.run_in_executor(
                None,
                lambda: GoogleTranslator(source="auto", target="de").translate(text)
            )

            await message.edit_text(
                f"<b>Ubersetzung (DE):</b>\n\n<code>{translated}</code>",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            await message.edit_text(f"Fehler: {e}")


def on_load():
    print("[Translator/DE] Addon loaded. .trd")


def on_unload():
    print("[Translator/DE] Addon unloaded")
