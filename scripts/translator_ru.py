"""
Name: Translate to Russian
Version: 1.0
Author: UserBot
Description: Translates replied message to Russian. Usage: .tra (reply to a message)
"""

from deep_translator import GoogleTranslator


def register(client):
    """Register handlers when script is loaded."""
    from pyrogram import filters
    from pyrogram.enums import ParseMode
    from pyrogram.types import Message
    import asyncio

    @client.on_message(filters.command("tra", prefixes=".") & filters.reply & filters.me)
    async def tra_handler(client, message: Message):
        """Reply to a message with .tra to translate it to Russian."""
        reply = message.reply_to_message
        if not reply:
            await message.edit_text("Ответьте на сообщение для перевода.")
            return

        # Extract text from the replied message
        text = reply.text or reply.caption
        if not text:
            await message.edit_text("Нет текста для перевода.")
            return

        await message.edit_text("Перевод...")

        try:
            loop = asyncio.get_event_loop()
            translated = await loop.run_in_executor(
                None,
                lambda: GoogleTranslator(source="auto", target="ru").translate(text)
            )

            await message.edit_text(
                f"<b>Перевод:</b>\n\n<code>{translated}</code>",
                parse_mode=ParseMode.HTML
            )

        except Exception as e:
            await message.edit_text(f"Ошибка перевода: {e}")


def on_load():
    print("[tra] Script loaded. Use .tra (reply to message)")


def on_unload():
    print("[tra] Script unloaded")
