"""
Общие утилиты для всех скриптов sandusr.
Импортируй в скриптах: from scripts._utils import safe_edit
"""

import sys
import os

# Добавляем корень проекта в sys.path чтобы импорт работал
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)


async def safe_edit(message, text, **kwargs):
    """
    Безопасный edit_text с fallback на reply.

    В каналах и группах без прав редактирования edit_text кидает
    ChatWriteForbidden (403). Эта функция пытается edit_text,
    а если не получается — отправляет reply.

    Args:
        message: Pyrogram Message object
        text: текст сообщения
        **kwargs: дополнительные параметры для edit_text/reply
                  (parse_mode, disable_web_page_preview, и т.д.)
    """
    try:
        return await message.edit_text(text, **kwargs)
    except Exception:
        try:
            return await message.reply(text, quote=False, **kwargs)
        except Exception:
            pass
    return None
