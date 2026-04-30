"""
Name: Weather
Version: 1.0
Author: UserBot
Description: Weather info with city whitelist. Usage: .wea <city>, .wea add <city>, .wea del <city>, .wea list
"""

import os
import json
import asyncio
import urllib.request
import urllib.error

WHITELIST_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts_custom",
    "weather_whitelist.json",
)

# Weather descriptions -> emoji
WEATHER_ICONS = {
    "clear": "☀️",
    "sunny": "☀️",
    "partly cloudy": "⛅",
    "partlyCloudy": "⛅",
    "cloudy": "☁️",
    "overcast": "☁️",
    "fog": "🌫️",
    "mist": "🌫️",
    "haze": "🌫️",
    "light rain": "🌦️",
    "patchy rain": "🌦️",
    "moderate rain": "🌧️",
    "rain": "🌧️",
    "heavy rain": "🌧️",
    "light drizzle": "🌦️",
    "drizzle": "🌦️",
    "light snow": "🌨️",
    "patchy snow": "🌨️",
    "moderate snow": "❄️",
    "snow": "❄️",
    "heavy snow": "❄️",
    "blizzard": "🌬️",
    "blowing snow": "🌬️",
    "thunderstorm": "⛈️",
    "thunder": "⛈️",
    "thundery": "⛈️",
    "freezing": "🥶",
    "ice": "🥶",
    "sleet": "🌧️",
}


def _get_icon(condition: str) -> str:
    """Match weather condition text to an emoji."""
    cond_lower = condition.lower()
    for key, icon in WEATHER_ICONS.items():
        if key in cond_lower:
            return icon
    return "🌡️"


def _load_whitelist() -> list:
    """Load whitelist from JSON file."""
    try:
        if os.path.exists(WHITELIST_FILE):
            with open(WHITELIST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def _save_whitelist(wl: list) -> None:
    """Save whitelist to JSON file."""
    os.makedirs(os.path.dirname(WHITELIST_FILE), exist_ok=True)
    with open(WHITELIST_FILE, "w", encoding="utf-8") as f:
        json.dump(wl, f, indent=2, ensure_ascii=False)


def _check_whitelist(city: str, region: str = "") -> tuple:
    """
    Check if city or region is in whitelist.
    Returns (is_active: bool, match_type: str).
    """
    wl = _load_whitelist()
    wl_lower = [c.lower() for c in wl]

    if city.lower() in wl_lower:
        return True, "город"
    if region and region.lower() in wl_lower:
        return True, f"регион: {region}"
    return False, ""


def register(client):
    """Register handlers when script is loaded."""
    from pyrogram import filters
    from pyrogram.enums import ParseMode
    from pyrogram.types import Message

    @client.on_message(filters.command("wea", prefixes=".") & filters.me)
    async def wea_handler(client, message: Message):
        """Weather command with whitelist management."""
        args = message.text.split(maxsplit=1)

        if len(args) < 2:
            await message.edit_text(
                "<b>🌦 Погода</b>\n\n"
                "<code>.wea &lt;город&gt;</code> — погода в городе\n"
                "<code>.wea add &lt;город&gt;</code> — добавить в белый список\n"
                "<code>.wea del &lt;город&gt;</code> — убрать из белого списка\n"
                "<code>.wea list</code> — белый список",
                parse_mode=ParseMode.HTML,
            )
            return

        part = args[1].strip()

        # ── .wea list ───────────────────────────────────────────────
        if part.lower() == "list":
            wl = _load_whitelist()
            if not wl:
                await message.edit_text(
                    "📋 Белый список пуст.\n\n"
                    "<code>.wea add &lt;город&gt;</code>",
                    parse_mode=ParseMode.HTML,
                )
            else:
                lines = "\n".join(f"  {i}. <code>{c}</code>" for i, c in enumerate(wl, 1))
                await message.edit_text(
                    f"📋 <b>Белый список:</b>\n\n{lines}",
                    parse_mode=ParseMode.HTML,
                )
            return

        # ── .wea add <city> ────────────────────────────────────────
        if part.lower().startswith("add "):
            city = part[4:].strip()
            if not city:
                await message.edit_text(
                    "❌ Укажите город: <code>.wea add &lt;город&gt;</code>",
                    parse_mode=ParseMode.HTML,
                )
                return
            wl = _load_whitelist()
            if city.lower() in [c.lower() for c in wl]:
                await message.edit_text(
                    f"⚠️ <b>{city}</b> уже в белом списке",
                    parse_mode=ParseMode.HTML,
                )
            else:
                wl.append(city)
                _save_whitelist(wl)
                await message.edit_text(
                    f"✅ <b>{city}</b> добавлен в белый список",
                    parse_mode=ParseMode.HTML,
                )
            return

        # ── .wea del <city> ────────────────────────────────────────
        if part.lower().startswith("del ") or part.lower().startswith("rm "):
            city = part[4:].strip()
            if not city:
                await message.edit_text(
                    "❌ Укажите город: <code>.wea del &lt;город&gt;</code>",
                    parse_mode=ParseMode.HTML,
                )
                return
            wl = _load_whitelist()
            new_wl = [c for c in wl if c.lower() != city.lower()]
            if len(new_wl) < len(wl):
                _save_whitelist(new_wl)
                await message.edit_text(
                    f"✅ <b>{city}</b> убран из белого списка",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await message.edit_text(
                    f"❌ <b>{city}</b> не найден в белом списке",
                    parse_mode=ParseMode.HTML,
                )
            return

        # ── .wea <city> — weather lookup ───────────────────────────
        city = part
        await message.edit_text(
            f"🔄 Загрузка погоды: <b>{city}</b>...",
            parse_mode=ParseMode.HTML,
        )

        try:
            url = f"https://wttr.in/{city}?format=j1&lang=ru"

            def _fetch():
                req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return json.loads(resp.read().decode())

            data = await asyncio.get_event_loop().run_in_executor(None, _fetch)

            cur = data["current_condition"][0]

            temp = cur["temp_C"]
            feels = cur["FeelsLikeC"]
            humidity = cur["humidity"]
            wind = cur["windspeedKmph"]
            condition = cur.get("weatherDesc", [{}])[0].get("value", "Неизвестно")
            icon = _get_icon(condition)

            # Region / country from nearest_area
            area = data.get("nearest_area", [{}])[0]
            region = area.get("region", [{}])[0].get("value", "")
            country = area.get("country", [{}])[0].get("value", "")

            # Whitelist check (city or region)
            is_active, match = _check_whitelist(city, region)
            if is_active:
                wl_line = f"✅ <b>Активен</b> ({match})"
            else:
                wl_line = "⛔ <b>Не активен</b>"

            # Build output
            location = f"🌍 <b>{city}</b>"
            if region:
                location += f", {region}"
            if country:
                location += f", {country}"

            text = (
                f"{location}\n\n"
                f"{icon} <b>{condition}</b>\n"
                f"🌡 Температура: <b>{temp}°C</b>\n"
                f"🤒 Ощущается: <b>{feels}°C</b>\n"
                f"💧 Влажность: <b>{humidity}%</b>\n"
                f"💨 Ветер: <b>{wind} км/ч</b>\n\n"
                f"📋 Белый список: {wl_line}"
            )

            await message.edit_text(text, parse_mode=ParseMode.HTML)

        except (asyncio.TimeoutError, TimeoutError):
            await message.edit_text(
                "❌ Таймаут. Попробуйте позже.",
                parse_mode=ParseMode.HTML,
            )
        except urllib.error.URLError as e:
            await message.edit_text(
                f"❌ Ошибка сети: {e.reason}",
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            await message.edit_text(
                f"❌ Ошибка: {e}",
                parse_mode=ParseMode.HTML,
            )


def on_load():
    print("[weather] Loaded. Use .wea <city>")


def on_unload():
    print("[weather] Unloaded")
