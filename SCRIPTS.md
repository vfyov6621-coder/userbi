# Zaya UserBot — Руководство по скриптам

## Содержание

- [Структура скрипта](#структура-скрипта)
- [meta.json](#metajson)
- [main.py](#mainpy)
- [Аддоны (дополнения)](#аддоны-дополнения)
- [Веб-вкладки](#веб-вкладки)
- [Доступные API](#доступные-api)
- [Полный пример](#полный-пример)
- [Бесплатные скрипты (gitignored)](#бесплатные-скрипты-gitignored)

---

## Структура скрипта

Каждый скрипт — это отдельная папка в `scripts/` с минимум 2 файлами:

```
scripts/
  my_script/
    meta.json      — метаданные (имя, версия, команда, аддоны, вкладки)
    main.py        — основной код скрипта
    addons/        — (опционально) папка с дополнениями
      addon1.py
      addon2.py
```

### Расположение

| Папка | Описание | Git |
|-------|----------|-----|
| `scripts/` | Встроенные скрипты | ✅ Отслеживаются |
| `scripts_custom/` | Пользовательские скрипты | ❌ gitignored |

Если скрипт существует в обеих папках — `scripts_custom/` имеет приоритет.

---

## meta.json

Обязательный файл в каждой папке скрипта. Формат:

```json
{
  "name": "My Script",
  "version": "1.0",
  "author": "Zaya",
  "description": "Описание скрипта",
  "command": ".myscript",
  "addons": [],
  "tabs": []
}
```

### Поля

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `name` | string | ✅ | Отображаемое имя скрипта |
| `version` | string | ✅ | Версия (semver) |
| `author` | string | ❌ | Автор |
| `description` | string | ❌ | Краткое описание |
| `command` | string | ❌ | Основная команда (для отображения) |
| `addons` | array | ✅ | Список дополнений (пустой = нет) |
| `tabs` | array | ✅ | Список веб-вкладок (пустой = нет) |

### addons

```json
{
  "addons": [
    {
      "file": "addons/ru.py",
      "name": "Русский",
      "command": ".myscript_ru",
      "enabled": true,
      "description": "Описание дополнения"
    }
  ]
}
```

| Поле | Тип | Описание |
|------|-----|----------|
| `file` | string | Путь к файлу аддона (относительно папки скрипта) |
| `name` | string | Отображаемое имя |
| `command` | string | Команда в Telegram |
| `enabled` | bool | Включён по умолчанию |
| `description` | string | Описание |

### tabs

```json
{
  "tabs": [
    {
      "id": "my_tab_id",
      "name": "Вкладка",
      "icon": "📊"
    }
  ]
}
```

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | string | Уникальный ID вкладки (для API) |
| `name` | string | Отображаемое имя в сайдбаре |
| `icon` | string | Emoji иконка |

---

## main.py

Основной файл скрипта. Должен содержать следующие функции:

### Обязательные

```python
def register(client):
    """
    Вызывается при загрузке скрипта.
    Здесь регистрируются обработчики Pyrogram.
    
    Args:
        client: Экземпляр Pyrogram Client (уже авторизован)
    """
    from pyrogram import filters
    from pyrogram.enums import ParseMode
    from pyrogram.types import Message
    
    @client.on_message(filters.command("cmd", prefixes=".") & filters.me)
    async def cmd_handler(client, message: Message):
        await message.edit_text("Привет!", parse_mode=ParseMode.HTML)


def on_load():
    """Вызывается после register(). Для инициализации."""
    print("[my_script] Loaded")


def on_unload():
    """Вызывается при выгрузке скрипта. Для очистки."""
    print("[my_script] Unloaded")
```

### Опциональные

```python
def get_tab_data(tab_id, **params):
    """
    Возвращает данные для веб-вкладки.
    Вызывается когда веб-панель запрашивает данные вкладки.
    
    Args:
        tab_id: ID вкладки из meta.json
        **params: GET параметры из запроса
    
    Returns:
        dict с данными (должен быть JSON-сериализуемым)
    """
    if tab_id == "my_tab_id":
        action = params.get("action", "default")
        return {"success": True, "data": [...]}
    return None
```

---

## Аддоны (дополнения)

Аддоны — это дополнительные модули, расширяющие функционал основного скрипта.
Они находятся в папке `addons/` внутри скрипта и имеют тот же формат что и `main.py`.

### Структура аддона

```python
# scripts/my_script/addons/feature.py

def register(client):
    """Регистрирует обработчики для данного дополнения."""
    from pyrogram import filters
    from pyrogram.enums import ParseMode
    from pyrogram.types import Message
    
    @client.on_message(filters.command("feature", prefixes=".") & filters.me)
    async def feature_handler(client, message: Message):
        await message.edit_text("Feature active!", parse_mode=ParseMode.HTML)


def on_load():
    print("[my_script/feature] Addon loaded")


def on_unload():
    print("[my_script/feature] Addon unloaded")
```

### Управление аддонами

- Состояние (включён/выключен) сохраняется в `scripts_custom/addon_states.json`
- При переключении аддона скрипт автоматически перезагружается
- Отключённые аддоны не загружаются (их `register()` не вызывается)

---

## Веб-вкладки

Скрипты могут добавлять свои вкладки в веб-панель. Это полезно для:
- Отображения данных, собранных скриптом
- Управления настройками скрипта
- Логов и статистики

### Как работает

1. В `meta.json` укажите вкладку в `tabs`
2. В `main.py` реализуйте функцию `get_tab_data(tab_id, **params)`
3. Веб-панель автоматически создаст навигацию и вызовет API

### API

```
GET /api/tabs                       — список всех доступных вкладок
GET /api/tabs/<tab_id>?param=value  — данные для вкладки
```

### Пример: логгер удалённых сообщений

```python
# meta.json
{
  "tabs": [{"id": "deleted_logger", "name": "Удалённые", "icon": "🗑"}]
}

# main.py
def get_tab_data(tab_id, **params):
    if tab_id == "deleted_logger":
        action = params.get("action", "list_chats")
        if action == "list_chats":
            return {"success": True, "chats": [...]}
        if action == "chat_messages":
            chat_id = params.get("chat_id")
            return {"success": True, "messages": [...]}
    return None
```

---

## Доступные API

### В скриптах (main.py)

| Объект | Описание |
|--------|----------|
| `client` | Pyrogram Client (передаётся в `register()`) |
| `from config import Config` | Конфигурация, логи, загрузка скриптов |

### Config

```python
from config import Config

Config.add_log("Сообщение", "INFO")     # Добавить лог
Config.get_logs()                       # Получить все логи
Config.BASE_DIR                         # Путь к папке юзербота
Config.SCRIPTS_DIR                      # Путь к scripts/
Config.CUSTOM_SCRIPTS_DIR               # Путь к scripts_custom/
```

### Pyrogram

```python
# В register(client):
from pyrogram import filters, Client
from pyrogram.enums import ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

# Важно: используйте ParseMode.HTML (enum), а не "html" (строку)
await message.edit_text("<b>text</b>", parse_mode=ParseMode.HTML)

# Для ответов с inline-кнопками:
await message.edit(
    "text",
    reply_markup=InlineKeyboardMarkup([...]),
    parse_mode=ParseMode.HTML
)
```

---

## Полный пример

### Создание скрипта "Counter"

```
scripts/
  counter/
    meta.json
    main.py
    data.json       (создаётся автоматически)
```

**meta.json:**
```json
{
  "name": "Counter",
  "version": "1.0",
  "author": "Zaya",
  "description": "Счётчик сообщений с веб-статистикой",
  "command": ".counter",
  "addons": [],
  "tabs": [
    {"id": "counter_stats", "name": "Статистика", "icon": "📊"}
  ]
}
```

**main.py:**
```python
"""
Counter — message counter with web stats tab
"""
import os
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")

_counts = {}


def _load():
    global _counts
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                _counts = json.load(f)
    except Exception:
        _counts = {}


def _save():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(_counts, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def register(client):
    from pyrogram import filters
    from pyrogram.enums import ParseMode
    from pyrogram.types import Message

    @client.on_message(filters.me & ~filters.command("counter", prefixes="."))
    async def count_handler(client, message: Message):
        chat_id = str(message.chat.id)
        _counts[chat_id] = _counts.get(chat_id, 0) + 1
        _save()

    @client.on_message(filters.command("counter", prefixes=".") & filters.me)
    async def counter_cmd(client, message: Message):
        chat_id = str(message.chat.id)
        count = _counts.get(chat_id, 0)
        total = sum(_counts.values())
        await message.edit_text(
            f"📊 <b>Счётчик</b>\n\n"
            f"Этот чат: <b>{count}</b>\n"
            f"Всего: <b>{total}</b>",
            parse_mode=ParseMode.HTML
        )


def get_tab_data(tab_id, **params):
    if tab_id == "counter_stats":
        sorted_chats = sorted(_counts.items(), key=lambda x: x[1], reverse=True)
        return {
            "success": True,
            "total": sum(_counts.values()),
            "chats": [{"id": cid, "count": cnt} for cid, cnt in sorted_chats]
        }
    return None


def on_load():
    _load()
    print("[Counter] Loaded")


def on_unload():
    _save()
    print("[Counter] Unloaded")
```

---

## Бесплатные скрипты (gitignored)

Пользовательские скрипты хранятся в `scripts_custom/` и не отслеживаются в git.
Вы можете создавать их:

1. **Через веб-панель** → кнопка "+ Новый скрипт"
2. **Через Telegram** → `.lm load <script_id>`
3. **Вручную** → создать папку с `meta.json` и `main.py` в `scripts_custom/`

### Состояния (persisted in scripts_custom/)

| Файл | Описание |
|------|----------|
| `auto_start.json` | Список скриптов для автозапуска |
| `addon_states.json` | Состояния включения/выключения аддонов |
| `bot_info.json` | Информация о боте для `.mm` |
| `bot_photo.jpg` | Фото для меню `.mm` |
| `notes.json` | Данные скрипта заметок |
