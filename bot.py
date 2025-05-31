import os
import subprocess
import asyncio
import libtorrent as lt
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

TELEGRAM_TOKEN = 'YOUR_TELEGRAM_BOT_TOKEN'
MOUNT_POINT = '/mnt/gdrive'
DOWNLOAD_DIR = os.path.join(MOUNT_POINT, 'torrent_downloads')
RCLONE_REMOTE = 'gdrive'

# --- Mount Google Drive ---
async def mount_gdrive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    os.makedirs(MOUNT_POINT, exist_ok=True)
    if os.path.ismount(MOUNT_POINT):
        await query.edit_message_text("✅ Google Drive already mounted!")
        return
    try:
        subprocess.Popen(
            ["rclone", "mount", f"{RCLONE_REMOTE}:", MOUNT_POINT, "--daemon"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        await query.edit_message_text("⏳ Mounting Google Drive...")
        await asyncio.sleep(3)
        if os.path.ismount(MOUNT_POINT):
            await query.edit_message_text("✅ Google Drive mounted!")
        else:
            await query.edit_message_text("❌ Mount failed. Try again.")
    except Exception:
        await query.edit_message_text("❌ Mount failed.")

# --- /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("📥 Mount Google Drive", callback_data='mount_gdrive')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Send a .torrent file or magnet link.\n📥 Use the button below to mount Google Drive.",
        reply_markup=reply_markup
    )

# --- /status ---
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if os.path.ismount(MOUNT_POINT):
        await update.message.reply_text("✅ Google Drive is mounted!")
    else:
        await update.message.reply_text("❌ Google Drive is not mounted.")

# --- Download from .torrent file ---
async def download_torrent_file(torrent_path, download_dir, progress_callback):
    ses = lt.session()
    ses.listen_on(6881, 6891)
    info = lt.torrent_info(torrent_path)
    params = {'save_path': download_dir, 'storage_mode': lt.storage_mode_t(2), 'ti': info}
    h = ses.add_torrent(params)
    while not h.is_seed():
        s = h.status()
        await progress_callback(s.progress * 100)
        await asyncio.sleep(1)
    return download_dir

# --- Download from magnet link ---
async def download_torrent_magnet(magnet_link, download_dir, progress_callback):
    ses = lt.session()
    ses.listen_on(6881, 6891)
    params = {'save_path': download_dir, 'storage_mode': lt.storage_mode_t(2)}
    h = lt.add_magnet_uri(ses, magnet_link, params)
    while not h.has_metadata():
        await asyncio.sleep(1)
    while not h.is_seed():
        s = h.status()
        await progress_callback(s.progress * 100)
        await asyncio.sleep(1)
    return download_dir

# --- Handle .torrent file ---
async def handle_torrent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not os.path.ismount(MOUNT_POINT):
        await update.message.reply_text("❌ Google Drive not mounted. Use /start to mount.")
        return
    document = update.message.document
    if not document.file_name.endswith('.torrent'):
        await update.message.reply_text("❌ Please send a valid .torrent file.")
        return
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    torrent_path = os.path.join(DOWNLOAD_DIR, document.file_name)
    await document.get_file().download_to_drive(torrent_path)
    progress_msg = await update.message.reply_text("📥 Downloading...")
    async def progress_callback(progress):
        await progress_msg.edit_text(f"⏳ Downloading... {progress:.1f}%")
    try:
        await download_torrent_file(torrent_path, DOWNLOAD_DIR, progress_callback)
    except Exception:
        await progress_msg.edit_text("❌ Download failed.")
        return
    await progress_msg.edit_text("🚀 Uploading to Google Drive...")
    files = [f for f in os.listdir(DOWNLOAD_DIR) if not f.endswith('.torrent')]
    if files:
        file_list = "\n".join([f"✅ {f}" for f in files])
        await progress_msg.edit_text(f"✅ Done!\n{file_list}")
    else:
        await progress_msg.edit_text("❌ No files downloaded.")

# --- Handle magnet link ---
async def handle_magnet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not os.path.ismount(MOUNT_POINT):
        await update.message.reply_text("❌ Google Drive not mounted. Use /start to mount.")
        return
    text = update.message.text.strip()
    if not text.startswith("magnet:?"):
        return
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    progress_msg = await update.message.reply_text("📥 Downloading...")
    async def progress_callback(progress):
        await progress_msg.edit_text(f"⏳ Downloading... {progress:.1f}%")
    try:
        await download_torrent_magnet(text, DOWNLOAD_DIR, progress_callback)
    except Exception:
        await progress_msg.edit_text("❌ Download failed.")
        return
    await progress_msg.edit_text("🚀 Uploading to Google Drive...")
    files = [f for f in os.listdir(DOWNLOAD_DIR) if not f.endswith('.torrent')]
    if files:
        file_list = "\n".join([f"✅ {f}" for f in files])
        await progress_msg.edit_text(f"✅ Done!\n{file_list}")
    else:
        await progress_msg.edit_text("❌ No files downloaded.")

# --- Main ---
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CallbackQueryHandler(mount_gdrive, pattern='^mount_gdrive$'))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_torrent))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^magnet:\?'), handle_magnet))
    app.run_polling()

if __name__ == '__main__':
    main()
