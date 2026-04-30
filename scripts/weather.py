"""
Name: Weather
Version: 2.0
Author: UserBot
Description: Weather info with city whitelist. Usage: .wea <city>, .wea add <city>, .wea del <city>, .wea list
"""

import os
import json
import asyncio
import urllib.request
import urllib.parse
import urllib.error

WHITELIST_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts_custom",
    "weather_whitelist.json",
)

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather codes -> (description, emoji)
WMO_CODES = {
    0:  ("Ясно", "☀️"),
    1:  ("Преимущественно ясно", "🌤️"),
    2:  ("Переменная облачность", "⛅"),
    3:  ("Пасмурно", "☁️"),
    45: ("Туман", "🌫️"),
    48: ("Изморозь", "🌫️"),
    51: ("Лёгкая морось", "🌦️"),
    53: ("Морось", "🌦️"),
    55: ("Сильная морось", "🌧️"),
    56: ("Ледяная морось", "🌧️"),
    57: ("Сильная ледяная морось", "🌧️"),
    61: ("Небольшой дождь", "🌦️"),
    63: ("Дождь", "🌧️"),
    65: ("Сильный дождь", "🌧️"),
    66: ("Ледяной дождь", "🌧️"),
    67: ("Сильный ледяной дождь", "🌧️"),
    71: ("Небольшой снег", "🌨️"),
    73: ("Снег", "❄️"),
    75: ("Сильный снег", "❄️"),
    77: ("Снежные зёрна", "❄️"),
    80: ("Небольшой ливень", "🌦️"),
    81: ("Ливень", "🌧️"),
    82: ("Сильный ливень", "🌧️"),
    85: ("Небольшой снегопад", "🌨️"),
    86: ("Сильный снегопад", "❄️"),
    95: ("Гроза", "⛈️"),
    96: ("Гроза с градом", "⛈️"),
    99: ("Сильная гроза с градом", "⛈️"),
}


def _wmo(code: int) -> tuple:
    return WMO_CODES.get(code, ("Неизвестно", "🌡️"))


def _load_whitelist() -> list:
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
    os.makedirs(os.path.dirname(WHITELIST_FILE), exist_ok=True)
    with open(WHITELIST_FILE, "w", encoding="utf-8") as f:
        json.dump(wl, f, indent=2, ensure_ascii=False)


def _check_whitelist(city: str, region: str = "") -> tuple:
    wl = _load_whitelist()
    wl_lower = [c.lower() for c in wl]
    if city.lower() in wl_lower:
        return True, "город"
    if region and region.lower() in wl_lower:
        return True, f"регион: {region}"
    return False, ""


def _http_get(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def register(client):
    from pyrogram import filters
    from pyrogram.enums import ParseMode
    from pyrogram.types import Message

    @client.on_message(filters.command("wea", prefixes=".") & filters.me)
    async def wea_handler(client, message: Message):
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
            loop = asyncio.get_event_loop()

            # 1) Geocode the city (supports Russian + English names)
            geo_params = urllib.parse.urlencode({
                "name": city,
                "count": 1,
                "language": "ru",
                "format": "json",
            })
            geo_data = await loop.run_in_executor(
                None, _http_get, f"{GEO_URL}?{geo_params}"
            )

            results = geo_data.get("results")
            if not results:
                await message.edit_text(
                    f"❌ Город <b>{city}</b> не найден",
                    parse_mode=ParseMode.HTML,
                )
                return

            loc = results[0]
            lat = loc["latitude"]
            lon = loc["longitude"]
            found_name = loc.get("name", city)
            found_country = loc.get("country", "")
            region = loc.get("admin1", "")

            # 2) Fetch weather by coordinates
            w_params = urllib.parse.urlencode({
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
            })
            w_data = await loop.run_in_executor(
                None, _http_get, f"{WEATHER_URL}?{w_params}"
            )

            cur = w_data["current"]
            temp = cur.get("temperature_2m", "?")
            feels = cur.get("apparent_temperature", "?")
            humidity = cur.get("relative_humidity_2m", "?")
            wind = cur.get("wind_speed_10m", "?")
            wmo_code = cur.get("weather_code", 0)

            condition, icon = _wmo(wmo_code)

            # Whitelist check (city or region)
            is_active, match = _check_whitelist(found_name, region)
            if is_active:
                wl_line = f"✅ <b>Активен</b> ({match})"
            else:
                wl_line = "⛔ <b>Не активен</b>"

            # Build output
            location = f"🌍 <b>{found_name}</b>"
            if region:
                location += f", {region}"
            if found_country:
                location += f", {found_country}"

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
