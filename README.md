# TG UserBot

Telegram userbot with dynamic script loading, web panel, and Heroku support.

## Setup

1. Copy `.env.example` to `.env` and fill in your API credentials
2. Run `start.bat` (Windows) or `bash start.sh` (Linux)
3. Open http://localhost:8080 for web panel

## Commands (in Telegram)

- `.lm` - show help
- `.lm load <file>` - load a script
- `.lm unload <file>` - unload a script
- `.lm reload <file>` - reload a script
- `.lm list` - list all scripts
- `.lm info <file>` - script info
- `.lm unload_all` - unload all scripts

## Script Format

Scripts go in `scripts/` folder as `.py` files.

```python
def register(client):
    from pyrogram import filters
    @client.on_message(filters.command("cmd", prefixes=".") & filters.me)
    async def handler(client, message):
        await message.edit_text("Hello!")

def on_load():
    print("Loaded")

def on_unload():
    print("Unloaded")
```
