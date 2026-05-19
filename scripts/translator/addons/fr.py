"""Translator addon: French (.trf)
Reply to a message or provide text to translate to French.
"""

from deep_translator import GoogleTranslator


def register(client):
    from pyrogram import filters
    from pyrogram.enums import ParseMode
    from pyrogram.types import Message
    import asyncio

    @client.on_message(filters.command("trf", prefixes=".") & filters.me)
    async def trf_handler(client, message: Message):
        args = message.text.split(maxsplit=1)
        text = None

        if message.reply_to_message:
            text = message.reply_to_message.text or message.reply_to_message.caption

        if not text and len(args) > 1:
            text = args[1]

        if not text:
            await message.edit_text(
                "<code>.trf</code> (repondre a un message) ou <code>.trf texte</code>",
                parse_mode=ParseMode.HTML
            )
            return

        await message.edit_text("Traduction...")

        try:
            loop = asyncio.get_running_loop()
            translated = await loop.run_in_executor(
                None,
                lambda: GoogleTranslator(source="auto", target="fr").translate(text)
            )

            await message.edit_text(
                f"<b>Traduction (FR):</b>\n\n<code>{translated}</code>",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            await message.edit_text(f"Erreur: {e}")


def on_load():
    print("[Translator/FR] Addon loaded. .trf")


def on_unload():
    print("[Translator/FR] Addon unloaded")
