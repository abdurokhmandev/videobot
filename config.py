import os
import imageio_ffmpeg
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
TEMP_DIR = "temp_downloads"
MAX_FILE_SIZE_MB = 50  # Telegram fayl limitidan kichik bo'lishi kerak (50MB)
FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
