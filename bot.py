import uuid
import asyncio
import os
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile, InputMediaPhoto, InputMediaVideo
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, MAX_FILE_SIZE_MB
from utils.downloader import Downloader, detect_platform, extract_urls, remove_file

router = Router()
downloader = Downloader()

# Kesh xotira (URL larni qisqa ID bilan saqlash uchun)
URL_CACHE = {}

# Bot usernameni saqlash uchun global o'zgaruvchi
BOT_USERNAME = ""

# ─────────────────────────────────────────────────────────────────────────────
# /START
# ─────────────────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def start_handler(message: Message):
    text = (
        "👋 <b>Salom! Men Universal Video Downloader botman.</b>\n\n"
        "📥 Menga quyidagi platformalardan istalgan havolani yuboring:\n\n"
        "🎬 <b>Qo'llab-quvvatlanadi:</b>\n"
        "  • YouTube (Video, Audio, Shorts)\n"
        "  • Instagram (Reels, Post, Carousel)\n"
        "  • TikTok (Watermarksiz)\n"
        "  • Facebook & Twitter (X)\n"
        "  • Pinterest & Spotify\n\n"
        "🔗 Shunchaki havolani paste qiling, men ma'lumotlarni tortib olaman!"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("help"))
async def help_handler(message: Message):
    text = (
        "ℹ️ <b>Yordam</b>\n\n"
        "<b>Qanday ishlatiladi?</b>\n"
        "YouTube yoki Instagram havolasini chat ga yuboring.\n\n"
        "<b>Misol:</b>\n"
        "<code>https://youtube.com/watch?v=...</code>\n"
        "<code>https://www.instagram.com/reel/...</code>\n\n"
        "<b>Eslatma:</b>\n"
        "• Private postlar yuklanmaydi\n"
        "• Maksimal fayl hajmi: 50MB\n"
        "• Agar link ishlamasa, yangi havolani sinab ko'ring"
    )
    await message.answer(text, parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────────────────
# LINK QABUL QILISH
# ─────────────────────────────────────────────────────────────────────────────

@router.message(F.text)
async def link_handler(message: Message):
    text = message.text or ""
    urls = extract_urls(text)

    if not urls:
        await message.answer(
            "❌ Havola topilmadi.\n\n"
            "YouTube yoki Instagram havolasini yuboring.",
            parse_mode="HTML"
        )
        return

    url = urls[0]
    platform = detect_platform(url)

    if platform == "unknown":
        await message.answer(
            "❌ Faqat <b>YouTube</b> va <b>Instagram</b> havolalari qabul qilinadi.",
            parse_mode="HTML"
        )
        return

    # Kuting xabari
    loading_msg = await message.reply("⏳ <b>Ma'lumotlar olinmoqda...</b>", parse_mode="HTML")

    # Ma'lumot olish
    info = await downloader.get_info(url)
    if not info:
        await loading_msg.edit_text("❌ Ma'lumot olinmadi. Havola noto'g'ri bo'lishi mumkin yoki platforma ruxsat bermadi.")
        return

    # Keshga saqlash
    url_id = uuid.uuid4().hex[:10]
    URL_CACHE[url_id] = {"url": url, "info": info}

    # Formatlarni ajratish
    formats = downloader.extract_formats(info)
    title = info.get('title', 'Video')
    
    # Boyitilgan Ma'lumotlar (Rich Metadata)
    views = info.get('view_count', 0)
    likes = info.get('like_count', 0)
    date = info.get('upload_date', '')
    
    def format_number(num):
        if not num: return "Noma'lum"
        if num >= 1_000_000: return f"{num/1_000_000:.1f}M"
        if num >= 1_000: return f"{num/1_000:.1f}K"
        return str(num)
        
    date_str = f"{date[:4]}-{date[4:6]}-{date[6:]}" if len(date) == 8 else "Noma'lum"
    
    # Xavfsiz tarzda duration ni olish va formatlash
    duration_val = info.get('duration')
    duration = info.get('duration_string')
    if not duration and isinstance(duration_val, (int, float)):
        m, s = divmod(int(duration_val), 60)
        h, m = divmod(m, 60)
        duration = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
    if not duration:
        duration = "Noma'lum"
        
    channel = info.get('uploader', 'Noma\'lum')
    thumbnail = info.get('thumbnail', '')
    
    # Rasm yashirincha qo'shish
    thumb_html = f"<a href='{thumbnail}'>&#8205;</a>" if thumbnail else ""

    text = (
        f"{thumb_html}🎬 <b>{title}</b>\n\n"
        f"👤 <b>Kanal/Avtor:</b> {channel}\n"
        f"👁 <b>Ko'rishlar:</b> {format_number(views)}  |  ❤️ <b>Layklar:</b> {format_number(likes)}\n"
        f"📅 <b>Sana:</b> {date_str}  |  ⏱ <b>Vaqt:</b> {duration}\n\n"
        f"👇 <i>Kerakli format yoki harakatni tanlang:</i>"
    )

    kb = build_quality_keyboard(formats, url_id, platform)
    
    await loading_msg.edit_text(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=False)


def build_quality_keyboard(formats: list, url_id: str, platform: str) -> InlineKeyboardMarkup:
    """Dinamik yuklab olish variantlari klaviaturasi"""
    buttons = []
    
    # 2 tadan tugmani yonma-yon qo'yish
    row = []
    for f in formats:
        # cb data: dl_id_formatid
        cb_data = f"dl_{url_id}_{f['id']}"
        row.append(InlineKeyboardButton(text=f["label"], callback_data=cb_data))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
        
    # Boshqa platformalar yoki formatsiz videolar uchun
    if not formats or (platform != "youtube" and len(formats) <= 1):
        buttons = [
            [
                InlineKeyboardButton(text="🎬 Video / Reels", callback_data=f"igv_{url_id}"),
                InlineKeyboardButton(text="🖼 Rasm / Carousel", callback_data=f"igp_{url_id}"),
            ],
            [
                InlineKeyboardButton(text="🎵 Audio (MP3)", callback_data=f"iga_{url_id}"),
            ]
        ]
        
    # Qo'shimcha funksiyalar tugmalari
    extra_buttons = [
        InlineKeyboardButton(text="🖼 Rasm (Thumbnail)", callback_data=f"thumb_{url_id}"),
        InlineKeyboardButton(text="📝 To'liq ma'lumot", callback_data=f"desc_{url_id}")
    ]
    buttons.append(extra_buttons)
        
    buttons.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ─────────────────────────────────────────────────────────────────────────────
# CALLBACK HANDLER — callback_data + reply_to_message dan URL olamiz
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "cancel")
async def cancel_handler(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer("Bekor qilindi ✅")


@router.callback_query(F.data.startswith(("thumb_", "desc_")))
async def extra_features_callback(callback: CallbackQuery):
    data = callback.data
    parts = data.split("_")
    action = parts[0]
    url_id = parts[1]

    cache_data = URL_CACHE.get(url_id)
    if not cache_data:
        await callback.answer("❌ Havola eskirgan.", show_alert=True)
        return
        
    info = cache_data.get("info", {})
    
    if action == "thumb":
        thumbnail = info.get("thumbnail")
        if thumbnail:
            await callback.message.answer_photo(thumbnail, caption="🖼 <b>Muqova rasmi (Thumbnail)</b>", parse_mode="HTML")
            await callback.answer()
        else:
            await callback.answer("Rasm topilmadi!", show_alert=True)
            
    elif action == "desc":
        desc = info.get("description", "Ma'lumot yo'q.")
        # Telegram limit 4096 belgi
        if len(desc) > 4000:
            desc = desc[:4000] + "..."
        await callback.message.answer(f"📝 <b>To'liq ma'lumot:</b>\n\n{desc}", parse_mode="HTML", disable_web_page_preview=True)
        await callback.answer()


@router.callback_query(F.data.startswith(("dl_", "igv_", "igp_", "iga_")))
async def download_callback(callback: CallbackQuery):
    await callback.answer()
    
    data = callback.data
    parts = data.split("_")
    action = parts[0]
    url_id = parts[1]
    format_id = parts[2] if len(parts) > 2 else None

    cache_data = URL_CACHE.get(url_id)
    if not cache_data:
        await callback.message.edit_text("❌ Havola eskirgan yoki xotiradan o'chgan. Iltimos, havolani qayta yuboring.")
        return

    url = cache_data.get("url")

    loading_msg = await callback.message.edit_text(
        "🚀 <b>Yuklash boshlanmoqda...</b>\n"
        "<i>Bir oz kuting...</i>",
        parse_mode="HTML"
    )

    await process_download(callback.message, url, action, format_id, loading_msg)



async def process_download(message: Message, url: str, action: str, format_id: str, loading_msg: Message):
    """Yuklab olish va yuborish"""
    result = None
    files_to_delete = []

    # Progress Callback funksiyasi
    async def progress_cb(percent, speed, eta):
        try:
            text = (
                f"📥 <b>Yuklanmoqda...</b>\n\n"
                f"📊 Foiz: <b>{percent}</b>\n"
                f"🚀 Tezlik: <b>{speed}</b>\n"
                f"⏳ Qolgan vaqt: <b>{eta}</b>"
            )
            await loading_msg.edit_text(text, parse_mode="HTML")
        except Exception:
            pass

    try:
        # ─── YouTube / Dynamic ───
        if action == "dl":
            if format_id == "audio":
                result = await downloader.download_audio(url, progress_callback=progress_cb)
            else:
                result = await downloader.download_video(url, format_id=format_id, progress_callback=progress_cb)
        # ─── Instagram Default ───
        elif action == "igv":
            result = await downloader.download_video(url, progress_callback=progress_cb)
        elif action == "igp":
            result = await downloader.download_instagram_photos(url, progress_callback=progress_cb)
        elif action == "iga":
            result = await downloader.download_audio(url, progress_callback=progress_cb)
        else:
            result = {"success": False, "error": "Noma'lum buyruq"}

        if not result or not result.get("success"):
            err = result.get("error", "Noma'lum xato") if result else "Noma'lum xato"
            await loading_msg.edit_text(f"❌ <b>Xato:</b> {err}", parse_mode="HTML")
            return

        files = result.get("files", [])
        if not files:
            await loading_msg.edit_text("❌ Fayl topilmadi.", parse_mode="HTML")
            return

        files_to_delete = [f["path"] for f in files]

        # ─── Yuborish ───
        await loading_msg.edit_text("📤 <b>Telegramga yuklanmoqda...</b>\n<i>Bu biroz vaqt olishi mumkin...</i>", parse_mode="HTML")

        # Asl xabarga javob (reply) qilish uchun message_id ni olamiz
        reply_id = message.reply_to_message.message_id if message.reply_to_message else None

        await send_files(message, files, result.get("title", ""), reply_to_msg_id=reply_id)

        await loading_msg.delete()

    except Exception as e:
        await loading_msg.edit_text(
            f"❌ <b>Kutilmagan xato:</b> {str(e)[:300]}",
            parse_mode="HTML"
        )
    finally:
        # Fayllarni tozalash
        for fpath in files_to_delete:
            await remove_file(fpath)


async def send_files(message: Message, files: list, title: str, reply_to_msg_id: int = None):
    """Fayllarni Telegramga yuboradi"""
    
    # Guruhga qo'shish tugmasi
    markup = None
    if BOT_USERNAME:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Guruhga qo'shish ➕", url=f"https://t.me/{BOT_USERNAME}?startgroup=true")]
        ])

    for i, file_info in enumerate(files):
        fpath = file_info["path"]
        ftype = file_info["type"]
        size_mb = file_info["size_mb"]
        ftitle = file_info.get("title", title)

        if not os.path.exists(fpath):
            continue

        if size_mb > MAX_FILE_SIZE_MB:
            await message.answer(
                f"⚠️ <b>Fayl hajmi {size_mb:.1f}MB!</b>\n\n"
                f"Telegram serverlari {MAX_FILE_SIZE_MB}MB gacha bo'lgan fayllarni yuborishga ruxsat beradi xolos.\n"
                f"Iltimos, pastroq sifatni tanlab ko'ring.",
                parse_mode="HTML"
            )
            continue

        caption = f"📥 <b>{ftitle[:200] if ftitle else 'Media'}</b>" if i == 0 else None
        input_file = FSInputFile(fpath)

        try:
            if ftype == "video":
                await message.answer_video(
                    input_file,
                    caption=caption,
                    parse_mode="HTML",
                    supports_streaming=True,
                    reply_markup=markup,
                    reply_to_message_id=reply_to_msg_id
                )
            elif ftype == "image":
                await message.answer_photo(
                    input_file,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=markup,
                    reply_to_message_id=reply_to_msg_id
                )
            elif ftype == "audio":
                await message.answer_audio(
                    input_file,
                    caption=caption,
                    title=ftitle[:64] if ftitle else "Audio",
                    parse_mode="HTML",
                    reply_markup=markup,
                    reply_to_message_id=reply_to_msg_id
                )
            else:
                await message.answer_document(
                    input_file,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=markup,
                    reply_to_message_id=reply_to_msg_id
                )
        except Exception as e:
            await message.answer(f"❌ Fayl yuborishda xato: {str(e)[:200]}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN .env faylida topilmadi!")
        return

    bot = Bot(token=BOT_TOKEN)
    
    # Bot username ni olish va global o'zgaruvchiga saqlash
    bot_info = await bot.get_me()
    global BOT_USERNAME
    BOT_USERNAME = bot_info.username

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    print(f"Bot ishga tushdi! (@{BOT_USERNAME})")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    asyncio.run(main())
