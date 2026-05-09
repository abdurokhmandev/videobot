import os
import re
import uuid
import asyncio
import time
import yt_dlp
from config import TEMP_DIR, MAX_FILE_SIZE_MB, FFMPEG_PATH


# ─────────────────────────────────────────────────────────────────────────────
# YORDAMCHI FUNKSIYALAR
# ─────────────────────────────────────────────────────────────────────────────

def detect_platform(url: str) -> str:
    """URL platformasini aniqlaydi"""
    url_lower = url.lower()
    if "instagram.com" in url_lower or "instagr.am" in url_lower:
        return "instagram"
    elif "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    elif "tiktok.com" in url_lower:
        return "tiktok"
    elif "facebook.com" in url_lower or "fb.watch" in url_lower:
        return "facebook"
    elif "twitter.com" in url_lower or "x.com" in url_lower:
        return "twitter"
    elif "pinterest.com" in url_lower or "pin.it" in url_lower:
        return "pinterest"
    elif "spotify.com" in url_lower:
        return "spotify"
    return "unknown"


def extract_urls(text: str) -> list:
    """Matndan URL larni ajratib oladi"""
    pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    return re.findall(pattern, text)


def ensure_temp_dir():
    """Vaqtinchalik papkani yaratadi"""
    os.makedirs(TEMP_DIR, exist_ok=True)


def get_file_size_mb(filepath: str) -> float:
    """Fayl hajmini MB da qaytaradi"""
    if os.path.exists(filepath):
        return os.path.getsize(filepath) / (1024 * 1024)
    return 0


async def remove_file(filepath: str):
    """Faylni xavfsiz o'chiradi"""
    try:
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
    except Exception:
        pass


def get_base_path() -> str:
    """Unique base path qaytaradi"""
    ensure_temp_dir()
    return os.path.join(TEMP_DIR, uuid.uuid4().hex)


def find_downloaded_files(prefix: str, exts=None) -> list:
    """Temp papkadan prefix bilan boshlanadigan fayllarni topadi"""
    result = []
    video_exts = {".mp4", ".webm", ".mkv", ".avi", ".mov"}
    image_exts = {".jpg", ".jpeg", ".png", ".webp"}
    audio_exts = {".mp3", ".m4a", ".opus", ".ogg"}

    for f in os.listdir(TEMP_DIR):
        fpath = os.path.join(TEMP_DIR, f)
        if not os.path.isfile(fpath):
            continue
        if not f.startswith(os.path.basename(prefix)):
            continue
        ext = os.path.splitext(f)[1].lower()
        if exts and ext not in exts:
            continue
        if ext in video_exts:
            ftype = "video"
        elif ext in image_exts:
            ftype = "image"
        elif ext in audio_exts:
            ftype = "audio"
        else:
            continue
        result.append({
            "path": fpath,
            "size_mb": get_file_size_mb(fpath),
            "type": ftype,
            "title": ""
        })
    return result


# ─────────────────────────────────────────────────────────────────────────────
# YT-DLP OPTIONS
# ─────────────────────────────────────────────────────────────────────────────

_COMMON_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "retries": 10,
    "fragment_retries": 10,
    "concurrent_fragment_downloads": 5, # Tezlashtirish
    "buffersize": 1024 * 1024 * 5, # 5MB buffer
    "skip_unavailable_fragments": True,
    "ffmpeg_location": FFMPEG_PATH,
    "http_headers": {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-us,en;q=0.5",
        "Sec-Fetch-Mode": "navigate",
    },
}

# Cookie faylini tekshirish (Bloklanmaslik uchun)
if os.path.exists("cookies.txt"):
    _COMMON_OPTS["cookiefile"] = "cookies.txt"

_INSTAGRAM_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.instagram.com/",
}


def _yt_video_opts(output_path: str, quality: str = "720", format_id: str = None) -> dict:
    opts = dict(_COMMON_OPTS)
    
    if format_id:
        format_str = f"{format_id}+bestaudio[ext=m4a]/{format_id}+bestaudio/{format_id}/best"
    else:
        height_map = {"360": 360, "480": 480, "720": 720, "1080": 1080}
        height = height_map.get(quality, 720)
        format_str = (
            f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]"
            f"/bestvideo[height<={height}]+bestaudio[ext=m4a]"
            f"/bestvideo[height<={height}]+bestaudio"
            f"/best[height<={height}][ext=mp4]"
            f"/best[height<={height}]"
            f"/mp4/best"
        )
        
    opts.update({
        "format": format_str,
        "outtmpl": output_path,
        "merge_output_format": "mp4",
    })
    return opts


def _yt_audio_opts(output_path: str) -> dict:
    opts = dict(_COMMON_OPTS)
    opts.update({
        "format": "bestaudio/best",
        "outtmpl": output_path,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    })
    return opts


def _ig_opts(output_path: str) -> dict:
    opts = dict(_COMMON_OPTS)
    # Instagram uchun YouTube extractor args kerak emas
    opts.pop("extractor_args", None)
    opts.update({
        "format": "best",
        "outtmpl": output_path,
        "http_headers": _INSTAGRAM_HEADERS,
    })
    return opts


# ─────────────────────────────────────────────────────────────────────────────
# DOWNLOADER SINFI
# ─────────────────────────────────────────────────────────────────────────────

class Downloader:

    @staticmethod
    def _run_ydl(url: str, opts: dict):
        """yt-dlp ni sinxron ishlatadi"""
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=True)

    @staticmethod
    def _run_ydl_nodown(url: str, opts: dict):
        """Faqat ma'lumot oladi, yuklamaydi"""
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    async def _run_async(self, func, *args):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func, *args)

    # ── Progress Hook ──────────────────────────────────────────────────────

    @staticmethod
    def _create_progress_hook(callback, loop):
        """yt-dlp progress hook ni asyncio ga moslashtiradi (Vizual progress bar)"""
        last_update_time = 0
        
        def generate_progress_bar(percent_val, length=10):
            filled = int(length * percent_val // 100)
            empty = length - filled
            return "█" * filled + "░" * empty
            
        def hook(d):
            nonlocal last_update_time
            if d['status'] == 'downloading':
                now = time.time()
                # Har 3 soniyada bir marta update qilish
                if now - last_update_time > 3.0:
                    last_update_time = now
                    
                    percent_str = d.get('_percent_str', '0.0%').strip()
                    # Aniq foizni float qilib olish
                    try:
                        clean_pct = percent_str.replace('%', '').replace('\x1b[0;94m', '').replace('\x1b[0m', '')
                        percent_float = float(clean_pct)
                    except Exception:
                        percent_float = 0.0
                        
                    speed_str = d.get('_speed_str', '0KiB/s').strip()
                    eta_str = d.get('_eta_str', 'Noma\'lum').strip()
                    
                    bar = generate_progress_bar(percent_float)
                    visual_percent = f"[{bar}] {percent_str}"
                    
                    if callback:
                        asyncio.run_coroutine_threadsafe(
                            callback(visual_percent, speed_str, eta_str), loop
                        )
                        
        return hook

    # ── YouTube Video ──────────────────────────────────────────────────────

    async def download_video(self, url: str, quality: str = "720", format_id: str = None, progress_callback=None) -> dict:
        """YouTube/Instagram video yuklab oladi"""
        base = get_base_path()
        platform = detect_platform(url)

        if platform == "instagram":
            opts = _ig_opts(base + ".%(ext)s")
        else:
            opts = _yt_video_opts(base + ".%(ext)s", quality, format_id)

        if progress_callback:
            loop = asyncio.get_event_loop()
            opts['progress_hooks'] = [self._create_progress_hook(progress_callback, loop)]

        try:
            info = await self._run_async(self._run_ydl, url, opts)
        except yt_dlp.utils.DownloadError as e:
            return {"success": False, "error": _friendly_error(str(e))}
        except Exception as e:
            return {"success": False, "error": f"Xato: {str(e)[:300]}"}

        if not info:
            return {"success": False, "error": "Ma'lumot olinmadi"}

        # Fayllarni topamiz
        entries = info.get("entries") or [info]
        files = []
        for entry in entries:
            if not entry:
                continue
            # requested_downloads dan to'g'ridan olish
            rds = entry.get("requested_downloads") or []
            fpath = rds[0].get("filepath", "") if rds else ""

            # Topilmasa papkadan qidiramiz
            if not fpath or not os.path.exists(fpath):
                found = find_downloaded_files(base, {".mp4", ".webm", ".mkv"})
                if found:
                    fpath = found[0]["path"]

            if fpath and os.path.exists(fpath):
                files.append({
                    "path": fpath,
                    "size_mb": get_file_size_mb(fpath),
                    "title": entry.get("title") or info.get("title", "video"),
                    "type": "video"
                })

        # Hali ham topilmasa papkadan qidiramiz
        if not files:
            files = find_downloaded_files(base, {".mp4", ".webm", ".mkv"})
            for f in files:
                f["title"] = info.get("title", "video")

        if not files:
            return {"success": False, "error": "Fayl yuklanmadi, qayta urinib ko'ring"}

        return {
            "success": True,
            "files": files,
            "title": info.get("title", "video"),
            "platform": platform
        }

    # ── Audio MP3 ──────────────────────────────────────────────────────────

    async def download_audio(self, url: str, progress_callback=None) -> dict:
        """MP3 audio yuklab oladi"""
        base = get_base_path()
        opts = _yt_audio_opts(base + ".%(ext)s")

        if progress_callback:
            loop = asyncio.get_event_loop()
            opts['progress_hooks'] = [self._create_progress_hook(progress_callback, loop)]

        try:
            info = await self._run_async(self._run_ydl, url, opts)
        except yt_dlp.utils.DownloadError as e:
            return {"success": False, "error": _friendly_error(str(e))}
        except Exception as e:
            return {"success": False, "error": f"Audio yuklanmadi: {str(e)[:300]}"}

        if not info:
            return {"success": False, "error": "Ma'lumot olinmadi"}

        # MP3 faylini topamiz
        mp3_path = base + ".mp3"
        if not os.path.exists(mp3_path):
            found = find_downloaded_files(base, {".mp3", ".m4a", ".opus", ".ogg"})
            if found:
                mp3_path = found[0]["path"]

        if not os.path.exists(mp3_path):
            return {"success": False, "error": "Audio fayl topilmadi"}

        return {
            "success": True,
            "files": [{
                "path": mp3_path,
                "size_mb": get_file_size_mb(mp3_path),
                "title": info.get("title", "audio"),
                "type": "audio"
            }],
            "title": info.get("title", "audio")
        }

    # ── Instagram Rasm/Carousel ────────────────────────────────────────────

    async def download_instagram_photos(self, url: str, progress_callback=None) -> dict:
        """Instagram post rasm/carousel yuklab oladi"""
        base = get_base_path()
        opts = _ig_opts(base + "_%(autonumber)s.%(ext)s")
        
        if progress_callback:
            loop = asyncio.get_event_loop()
            opts['progress_hooks'] = [self._create_progress_hook(progress_callback, loop)]

        try:
            info = await self._run_async(self._run_ydl, url, opts)
        except yt_dlp.utils.DownloadError as e:
            return {"success": False, "error": _friendly_error(str(e))}
        except Exception as e:
            return {"success": False, "error": f"Rasm yuklanmadi: {str(e)[:300]}"}

        if not info:
            return {"success": False, "error": "Ma'lumot olinmadi"}

        files = find_downloaded_files(base)
        for f in files:
            f["title"] = info.get("title") or "media"

        if not files:
            return {"success": False, "error": "Fayl topilmadi"}

        return {
            "success": True,
            "files": files,
            "title": info.get("title", "media")
        }

    # ── Info olish ────────────────────────────────────────────────────────

    async def get_info(self, url: str) -> dict:
        """Yuklab olmay faqat ma'lumot oladi"""
        platform = detect_platform(url)
        
        if platform == "instagram":
            opts = _ig_opts("")
        else:
            opts = dict(_COMMON_OPTS)
            
        opts.update({
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
        })
        
        try:
            info = await self._run_async(self._run_ydl_nodown, url, opts)
            return info or {}
        except Exception:
            return {}

    def extract_formats(self, info: dict) -> list:
        """Info ichidan mavjud sifatlarni va o'lchamlarni hisoblab qaytaradi"""
        if not info:
            return []
            
        formats_list = []
        
        # Audio uchun (Umumiy bitta audio variant qilib chiqaramiz)
        formats_list.append({
            "type": "audio",
            "id": "audio",
            "label": "🎵 Audio (MP3)",
            "size": "Noma'lum"
        })
        
        if "formats" not in info:
            # Instagram yoki formatsiz video bo'lsa
            return formats_list
            
        # YouTube sifatlari (faqat aniq balandligi borlarini olamiz)
        video_formats = {}
        for f in info.get("formats", []):
            height = f.get("height")
            # Sifat faqat video yoki best bo'lsa va height mavjud bo'lsa
            if height and isinstance(height, int) and height in [144, 240, 360, 480, 720, 1080, 1440, 2160]:
                fid = f.get("format_id")
                filesize = f.get("filesize") or f.get("filesize_approx")
                
                # Mavjud sifat uchun eng yaxshi formatni tanlash (mp4 afzalroq)
                if height not in video_formats or (f.get("ext") == "mp4" and video_formats[height].get("ext") != "mp4"):
                    mb = f"{filesize / (1024 * 1024):.1f} MB" if filesize else "Noma'lum"
                    video_formats[height] = {
                        "type": "video",
                        "id": fid,
                        "label": f"🎬 {height}p ({mb})",
                        "ext": f.get("ext"),
                        "height": height
                    }
                    
        # Sort by height descending
        sorted_heights = sorted(video_formats.keys(), reverse=True)
        for h in sorted_heights:
            formats_list.append(video_formats[h])
            
        return formats_list


# ─────────────────────────────────────────────────────────────────────────────
# XATO XABARLARINI FOYDALANUVCHI UCHUN TUSHUNARLI QILISH
# ─────────────────────────────────────────────────────────────────────────────

def _friendly_error(err: str) -> str:
    err_lower = err.lower()
    if "private" in err_lower:
        return "Bu post yopiq (private) ✋"
    if "age" in err_lower:
        return "Yosh cheklovi bor kontent 🔞"
    if "copyright" in err_lower or "removed" in err_lower:
        return "Bu kontent olib tashlangan yoki mualliflik huquqi bilan himoyalangan ⚠️"
    if "404" in err or "not found" in err_lower:
        return "Kontent topilmadi (o'chirilgan bo'lishi mumkin) 🔍"
    if "403" in err or "forbidden" in err_lower:
        return "Kirish taqiqlangan (403) — Boshqa havola bilan sinab ko'ring 🔄"
    if "login" in err_lower or "sign in" in err_lower:
        return "Bu kontent faqat login qilinganlar uchun ♟️"
    if "network" in err_lower or "connection" in err_lower:
        return "Internet muammosi, keyinroq urinib ko'ring 🌐"
    # Qisqacha xato
    short = err.replace("[youtube]", "").replace("[instagram]", "").strip()
    return f"Yuklab bo'lmadi: {short[:200]}"
