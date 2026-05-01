"""
Name: ping
Version: 1.0
Author: UserBot
Description: Simple example script. Replies to .ping with "Pong!"
"""


def register(client):
    """Register handlers when script is loaded."""
    from pyrogram import filters
    from pyrogram.types import Message

    @client.on_message(filters.command("ping", prefixes=".") & filters.me)
    async def ping_handler(client, message: Message):
        import time
        start = time.time()
        await message.edit_text("**Pong!**")
        end = time.time()
        ms = int((end - start) * 1000)
        await message.edit_text(f"**Pong!** `{ms}ms`")


def on_load():
    print("[ping] Script loaded. Use .ping")


def on_unload():
    print("[ping] Script unloaded")
