"""
Name: ping
Version: 1.0
Author: UserBot
Description: Simple example script. Replies to .ping with "Pong!"
"""


def register(client):
    """Register handlers when script is loaded."""
    from pyrofork import filters
    from pyrofork.types import Message

    @client.on_message(filters.command("ping", prefixes=".") & filters.me)
    async def ping_handler(client, message: Message):
        await message.edit_text("**Pong!**")


def on_load():
    print("[ping] Script loaded. Use .ping")


def on_unload():
    print("[ping] Script unloaded")
