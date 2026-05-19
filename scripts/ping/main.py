"""Ping - main module"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts._utils import safe_edit

def register(client):
    from pyrogram import filters
    from pyrogram.types import Message

    @client.on_message(filters.command("ping", prefixes=".") & filters.me)
    async def ping_handler(client, message: Message):
        import time
        start = time.time()
        await safe_edit(message, "**Pong!**")
        end = time.time()
        ms = int((end - start) * 1000)
        await safe_edit(message, f"**Pong!** `{ms}ms`")


def on_load():
    print("[ping] Script loaded. Use .ping")


def on_unload():
    print("[ping] Script unloaded")
