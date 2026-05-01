"""Translator addon: Russian (.tra)
Reply to a message to translate it to Russian.
"""

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
            await message.edit_text("Ответьте на сообщение для перевода.")
            return

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
                f"<b>Перевод (RU):</b>\n\n<code>{translated}</code>",
                parse_mode=ParseMode.HTML
            )

        except Exception as e:
            await message.edit_text(f"Ошибка перевода: {e}")


def on_load():
    print("[Translator/RU] Addon loaded. .tra")


def on_unload():
    print("[Translator/RU] Addon unloaded")
