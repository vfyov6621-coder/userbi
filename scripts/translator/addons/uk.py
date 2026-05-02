"""Translator addon: Ukrainian (.tru)
Reply to a message or provide text to translate to Ukrainian.
"""

from deep_translator import GoogleTranslator


def register(client):
    from pyrogram import filters
    from pyrogram.enums import ParseMode
    from pyrogram.types import Message
    import asyncio

    @client.on_message(filters.command("tru", prefixes=".") & filters.me)
    async def tru_handler(client, message: Message):
        args = message.text.split(maxsplit=1)
        text = None

        if message.reply_to_message:
            text = message.reply_to_message.text or message.reply_to_message.caption

        if not text and len(args) > 1:
            text = args[1]

        if not text:
            await message.edit_text(
                "<code>.tru</code> (відповідь на повідомлення) або <code>.tru текст</code>",
                parse_mode=ParseMode.HTML
            )
            return

        await message.edit_text("Переклад...")

        try:
            loop = asyncio.get_event_loop()
            translated = await loop.run_in_executor(
                None,
                lambda: GoogleTranslator(source="auto", target="uk").translate(text)
            )

            await message.edit_text(
                f"<b>Переклад (UK):</b>\n\n<code>{translated}</code>",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            await message.edit_text(f"Помилка: {e}")


def on_load():
    print("[Translator/UK] Addon loaded. .tru")


def on_unload():
    print("[Translator/UK] Addon unloaded")
