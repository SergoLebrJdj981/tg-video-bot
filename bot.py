import os
import asyncio
from aiogram import Bot, Dispatcher, executor, types
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import datetime

# Загружаем токены и ID из .env
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
GOOGLE_SHEETS_ID = os.getenv("GOOGLE_SHEETS_ID")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN не найден. Проверь файл .env")

# Белый список пользователей
ALLOWED_USERS = {1815433655}

def is_allowed(message: types.Message) -> bool:
    return (message.from_user is not None) and (message.from_user.id in ALLOWED_USERS)

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# --- Авторизация в Google API ---
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]
creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)

drive_service = build("drive", "v3", credentials=creds)
gc = gspread.authorize(creds)
sheet = gc.open_by_key(GOOGLE_SHEETS_ID).worksheet("videos")  # вкладка "videos" в таблице

def upload_to_drive(file_path, filename):
    """Загрузить файл в Google Drive и вернуть ссылку"""
    file_metadata = {
        "name": filename,
        "parents": [GOOGLE_DRIVE_FOLDER_ID]
    }
    media = MediaFileUpload(file_path, mimetype="video/mp4")
    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, webViewLink"
    ).execute()
    return file.get("webViewLink")

def add_row_to_sheet(video_id, version, link, title, hashtags, profile, social, status="готово"):
    """Добавить строку в Google Sheets"""
    today = datetime.datetime.now().strftime("%d.%m.%Y")
    sheet.append_row([video_id, version, today, link, title, "", hashtags, profile, social, status])

# --- Вспомогательная функция для ffmpeg ---
async def run_ffmpeg(cmd):
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        print("FFmpeg error:", stderr.decode())

# --- /start ---
@dp.message_handler(commands=["start"])
async def start_cmd(message: types.Message):
    if not is_allowed(message):
        await message.reply("⛔️ У вас нет доступа.")
        return
    await message.reply(
        "✅ Бот работает.\n"
        "Пришлите видео (до 20МБ). Я сделаю 5 версий, отправлю их сюда и запишу в Google Drive + Google Sheets."
    )

# --- Обработка видео ---
@dp.message_handler(content_types=[types.ContentType.VIDEO, types.ContentType.DOCUMENT])
async def handle_video(message: types.Message):
    if not is_allowed(message):
        return

    file = message.video or message.document
    if not file:
        await message.reply("⚠️ Пришлите видео в формате mp4/mov.")
        return

    file_name = f"video_{message.message_id}.mp4"
    input_path = f"input_{file_name}"
    await file.download(destination_file=input_path)

    await message.reply("📥 Видео получено. Обрабатываю...")

    outputs = []

    # Версия 1
    out1 = f"warm_25fps_{file_name}"
    cmd1 = [
        "ffmpeg", "-y", "-i", input_path,
        "-filter_complex",
        "[0:v]setpts=PTS/1.1,eq=contrast=1.05:brightness=0.02:saturation=1.2[v];[0:a]atempo=1.1[a]",
        "-map", "[v]", "-map", "[a]", "-r", "25",
        "-c:v", "libx264", "-preset", "fast", "-crf", "28",
        out1
    ]
    await run_ffmpeg(cmd1)
    outputs.append(("🔥 Warm LUT + 25fps + 1.1x", out1))

    # Версия 2
    out2 = f"cold_30fps_{file_name}"
    cmd2 = [
        "ffmpeg", "-y", "-i", input_path,
        "-filter_complex",
        "[0:v]setpts=PTS/1.2,eq=saturation=0.9:gamma_g=0.95:gamma_b=1.05[v];[0:a]atempo=1.2[a]",
        "-map", "[v]", "-map", "[a]", "-r", "30",
        "-c:v", "libx264", "-preset", "fast", "-crf", "28",
        out2
    ]
    await run_ffmpeg(cmd2)
    outputs.append(("❄️ Cold LUT + 30fps + 1.2x", out2))

    # Версия 3
    out3 = f"neutral_50fps_{file_name}"
    cmd3 = [
        "ffmpeg", "-y", "-i", input_path,
        "-filter_complex",
        "[0:v]setpts=PTS/1.3,eq=contrast=1.1:brightness=0.03:saturation=1.0[v];[0:a]atempo=1.3[a]",
        "-map", "[v]", "-map", "[a]", "-r", "50",
        "-c:v", "libx264", "-preset", "fast", "-crf", "28",
        out3
    ]
    await run_ffmpeg(cmd3)
    outputs.append(("⚖️ Neutral LUT + 50fps + 1.3x", out3))

    # Версия 4
    out4 = f"zoom_bar_{file_name}"
    cmd4 = [
        "ffmpeg", "-y", "-i", input_path,
        "-filter_complex",
        "[0:v]setpts=PTS/1.05,scale=iw*1.05:ih*1.05,crop=iw:ih,"
        "drawbox=x=0:y=ih-20:w=iw:h=20:color=red@0.8:t=fill[v];"
        "[0:a]atempo=1.05[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "28",
        out4
    ]
    await run_ffmpeg(cmd4)
    outputs.append(("🔎 Zoom + red bar + 1.05x", out4))

    # Версия 5
    out5 = f"rotate_sat_{file_name}"
    cmd5 = [
        "ffmpeg", "-y", "-i", input_path,
        "-filter_complex",
        "[0:v]setpts=PTS/1.0,eq=saturation=1.1,rotate=2*PI/180:fillcolor=black[v];"
        "[0:a]atempo=1.0[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "28",
        out5
    ]
    await run_ffmpeg(cmd5)
    outputs.append(("⏱ Rotate + saturation + 1.0x", out5))

    # Отправляем + загружаем в Drive + пишем в Sheets
    for idx, (caption, path) in enumerate(outputs, start=1):
        if os.path.exists(path) and os.path.getsize(path) > 0:
            # 1. Отправка в Telegram
            with open(path, "rb") as video:
                await message.reply_video(video, caption=caption)

            # 2. Загрузка в Google Drive
            drive_link = upload_to_drive(path, os.path.basename(path))

            # 3. Запись в Google Sheets (по одной строке на соцсеть)
            for social in ["TikTok", "YouTube Shorts", "VK Видео"]:
                add_row_to_sheet(
                    video_id=message.message_id,
                    version=f"V{idx}",
                    link=drive_link,
                    title=caption,
                    hashtags="#skincare #beauty",
                    profile=f"Профиль {idx}",
                    social=social,
                    status="готово"
                )
        else:
            await message.reply(f"⚠️ Ошибка: файл {path} пустой или не создан.")

    # Чистим временные файлы
    try:
        os.remove(input_path)
        for _, path in outputs:
            os.remove(path)
    except Exception:
        pass

if __name__ == "__main__":
    print("Bot is starting…")
    executor.start_polling(dp, skip_updates=True)
