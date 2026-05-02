"""
Translator - main module
Generic translation: .tr [lang] <text> or reply
"""

from deep_translator import GoogleTranslator


def register(client):
    """Register handlers when script is loaded."""
    from pyrogram import filters
    from pyrogram.enums import ParseMode
    from pyrogram.types import Message
    import asyncio

    @client.on_message(filters.command("tr", prefixes=".") & filters.me)
    async def tr_handler(client, message: Message):
        """[lang] <text> - Translate text or reply to a message"""
        args = message.text.split(maxsplit=1)

        # Parse language and text
        if len(args) < 2:
            text = None
            lang = "en"
        else:
            potential_lang = args[1].split()[0] if len(args) > 1 else ""
            if len(potential_lang) == 2 and potential_lang.isalpha():
                lang = potential_lang
                try:
                    text = args[1].split(maxsplit=1)[1]
                except IndexError:
                    text = None
            else:
                text = args[1] if len(args) > 1 else None
                lang = "en"

        # If no text provided, try to get from reply
        if not text:
            if message.reply_to_message:
                text = message.reply_to_message.text
                if not text:
                    await message.edit_text("Нет текста для перевода")
                    return
            else:
                await message.edit_text(
                    "Используйте: <code>.tr [lang] &lt;текст&gt;</code>\n"
                    "Или ответьте на сообщение командой <code>.tr [lang]</code>\n\n"
                    "Примеры:\n"
                    "<code>.tr en привет</code> - перевести на английский\n"
                    "<code>.tr de</code> (ответ на сообщение) - перевести на немецкий",
                    parse_mode=ParseMode.HTML
                )
                return

        await message.edit_text("Перевод...")

        try:
            loop = asyncio.get_event_loop()
            translated_text = await loop.run_in_executor(
                None,
                lambda: GoogleTranslator(source="auto", target=lang).translate(text)
            )

            await message.edit_text(
                f"<b>Перевод ({lang}):</b>\n\n"
                f"<code>{translated_text}</code>",
                parse_mode=ParseMode.HTML
            )

        except Exception as e:
            await message.edit_text(f"Ошибка перевода: {str(e)}")


def on_load():
    print("[Translator] Script loaded. Use .tr [lang] <text>")


def on_unload():
    print("[Translator] Script unloaded")
