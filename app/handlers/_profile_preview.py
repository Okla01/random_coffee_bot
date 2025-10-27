"""
Helper function for sending profile preview with photos.
"""

from aiogram.types import InputMediaPhoto


async def _send_profile_preview_with_photos(bot, chat_id: int, user, state, reply_markup) -> None:
    """Send profile preview with user photos.

    Behavior:
    - If user has photos: first send them as media_group (album), then send text preview with buttons
    - If no photos: just send text preview with buttons
    """
    # build preview text
    lines = ["📇 Предпросмотр анкеты:"]
    if user.name:
        lines.append(f"• Имя: {user.name}")
    if user.age:
        lines.append(f"• Возраст: {user.age}")
    if user.bio:
        lines.append(f"• О себе: {user.bio}")
    interests = (user.interests_json or {}).get("interests", [])
    if interests:
        lines.append("• Интересы: " + ", ".join(interests))
    photos = (user.photos_json or {}).get("photos", [])
    if photos:
        lines.append(f"• Фото: {len(photos)} шт.")
    preview = "\n".join(lines)

    # get photo file_ids
    file_ids = [p.get("file_id") for p in photos if p.get("file_id")]

    # no photos -> simple text message
    if not file_ids:
        sent = await bot.send_message(chat_id, preview, reply_markup=reply_markup)
        await state.update_data(last_kb_mid=sent.message_id)
        return

    # has photos -> first send them as media_group (album), then send preview text with buttons
    media = []
    for fid in file_ids[:10]:
        media.append(InputMediaPhoto(media=fid))

    try:
        # send photos as album first
        await bot.send_media_group(chat_id=chat_id, media=media)
    except Exception:
        # ignore photo sending errors, still try to send preview text
        pass

    # then send text preview with buttons as a separate message
    sent = await bot.send_message(chat_id, preview, reply_markup=reply_markup)
    await state.update_data(last_kb_mid=sent.message_id)
    return