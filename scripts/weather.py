"""
Name: Weather
Version: 3.0
Author: UserBot
Description: Weather info. Usage: .wea <city>
"""

import asyncio
import urllib.request
import urllib.parse
import urllib.error

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

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


def _wmo(code):
    return WMO_CODES.get(code, ("Неизвестно", "🌡️"))


def _http_get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        import json
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
                "<code>.wea &lt;город&gt;</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        city = args[1].strip()
        await message.edit_text(
            f"🔄 Загрузка погоды: <b>{city}</b>...",
            parse_mode=ParseMode.HTML,
        )

        try:
            loop = asyncio.get_event_loop()

            geo_params = urllib.parse.urlencode({
                "name": city, "count": 1,
                "language": "ru", "format": "json",
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
            lat, lon = loc["latitude"], loc["longitude"]
            found_name = loc.get("name", city)
            region = loc.get("admin1", "")
            country = loc.get("country", "")

            w_params = urllib.parse.urlencode({
                "latitude": lat, "longitude": lon,
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
            condition, icon = _wmo(cur.get("weather_code", 0))

            location = f"🌍 <b>{found_name}</b>"
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
                f"💨 Ветер: <b>{wind} км/ч</b>"
            )

            await message.edit_text(text, parse_mode=ParseMode.HTML)

        except (asyncio.TimeoutError, TimeoutError):
            await message.edit_text("❌ Таймаут.", parse_mode=ParseMode.HTML)
        except urllib.error.URLError as e:
            await message.edit_text(
                f"❌ Ошибка сети: {e.reason}", parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            await message.edit_text(
                f"❌ Ошибка: {e}", parse_mode=ParseMode.HTML,
            )


def on_load():
    print("[weather] Loaded. Use .wea <city>")


def on_unload():
    print("[weather] Unloaded")
