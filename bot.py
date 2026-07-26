import asyncio
import logging
import os
import re
import shutil
import sys
import time
from html import escape
from logging.handlers import RotatingFileHandler

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from telegram.error import TelegramError

from bot_config import BOT_TOKEN, CHANNEL_ID
from config import DOWNLOAD_DIR
from fetcher import (
    fetch_manga_page, parse_manga_info, fetch_chapter_page,
    parse_chapter_images, download_image,
)

RECENT_COUNT = 20

# --- 日志配置 ---
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")

# 业务日志（文件），输出到 logs/ 目录
_biz_logger = None


def _get_biz_logger():
    global _biz_logger
    if _biz_logger is not None:
        return _biz_logger

    os.makedirs(LOG_DIR, exist_ok=True)
    _biz_logger = logging.getLogger("manhua.biz")
    _biz_logger.setLevel(logging.INFO)
    _biz_logger.propagate = False

    handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "bot.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    ))
    _biz_logger.addHandler(handler)
    return _biz_logger


# 程序日志（stdout → journalctl 自动捕获）
_prog_logger = logging.getLogger("manhua")
_prog_logger.setLevel(logging.INFO)
_console = logging.StreamHandler(sys.stdout)
_console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
_prog_logger.addHandler(_console)


def _display_num(chapter_name):
    m = re.search(r"第\s*(\d+)\s*[话回]", chapter_name)
    return int(m.group(1)) if m else None


def _find_chapter_by_display(chapters, num):
    for ch in chapters:
        if _display_num(ch["chapter_name"]) == num:
            return ch
    return None


async def start(update, context):
    await update.message.reply_text(
        "漫画下载机器人\n\n"
        "命令：\n"
        "/recent <漫画ID>  — 查看最近章节\n"
        "例如：/recent woshidashenxian"
    )


async def _run_blocking(func, *args):
    """在线程池中运行阻塞的同步函数"""
    return await asyncio.to_thread(func, *args)


async def cmd_recent(update, context):
    args = context.args
    if not args:
        await update.message.reply_text("请提供漫画ID，例如：/recent woshidashenxian")
        return

    manga_id = args[0]
    user = update.effective_user
    _prog_logger.info("recent request: manga=%s user=%s", manga_id, user.username or user.id)

    msg = await update.message.reply_text("正在获取章节列表…")

    try:
        html = await _run_blocking(fetch_manga_page, manga_id)
        info = await _run_blocking(parse_manga_info, html, manga_id)
    except Exception as e:
        _prog_logger.error("fetch manga failed: %s", e)
        await msg.edit_text(f"获取漫画信息失败: {escape(str(e))}")
        return

    chapters = info.get("chapters", [])
    valid = [ch for ch in chapters if _display_num(ch["chapter_name"]) is not None]
    valid.sort(key=lambda ch: _display_num(ch["chapter_name"]), reverse=True)
    recent = valid[:RECENT_COUNT]
    recent.sort(key=lambda ch: _display_num(ch["chapter_name"]))

    if not recent:
        await msg.edit_text("未找到章节")
        return

    name = info.get("name", manga_id)
    buttons = []
    row = []
    for ch in recent:
        dn = _display_num(ch["chapter_name"])
        label = f"第{dn}话"
        row.append(InlineKeyboardButton(label, callback_data=f"dl|{manga_id}|{dn}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    await msg.edit_text(
        f"{name} — 最近章节",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


def _do_download(manga_id, chapter_num):
    """同步下载流程（在线程中运行，不阻塞事件循环）"""
    info = parse_manga_info(fetch_manga_page(manga_id), manga_id)

    target = _find_chapter_by_display(info["chapters"], chapter_num)
    if target is None:
        raise ValueError(f"未找到第 {chapter_num} 话")

    chapter_html = fetch_chapter_page(target["url"])
    image_urls = parse_chapter_images(chapter_html)
    if not image_urls:
        raise ValueError("未找到图片")

    manga_dir = os.path.join(DOWNLOAD_DIR, manga_id, str(chapter_num))
    os.makedirs(manga_dir, exist_ok=True)
    local_files = []
    failed = 0

    for i, img_url in enumerate(image_urls, 1):
        ext = img_url.rsplit(".", 1)[-1].split("?")[0] or "jpg"
        if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
            ext = "jpg"
        filepath = os.path.join(manga_dir, f"{i:03d}.{ext}")
        if download_image(img_url, filepath):
            local_files.append(filepath)
        else:
            failed += 1

    return {
        "manga_name": info.get("name", manga_id),
        "chapter_name": target["chapter_name"],
        "local_files": local_files,
        "failed": failed,
        "manga_dir": manga_dir,
    }


async def on_chapter_select(update, context):
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data.startswith("dl|"):
        return

    _, manga_id, chapter_str = data.split("|", 2)
    chapter_num = int(chapter_str)
    user = update.effective_user
    _prog_logger.info("download request: manga=%s chapter=%s user=%s", manga_id, chapter_num, user.username or user.id)

    await query.edit_message_text(f"正在下载第 {chapter_num} 话…")
    t0 = time.time()

    try:
        result = await _run_blocking(_do_download, manga_id, chapter_num)
    except ValueError as e:
        await query.edit_message_text(str(e))
        return
    except Exception as e:
        _prog_logger.error("download failed: %s", e)
        await query.edit_message_text(f"下载失败: {escape(str(e))}")
        return

    manga_name = result["manga_name"]
    chapter_name = result["chapter_name"]
    local_files = result["local_files"]
    failed = result["failed"]
    manga_dir = result["manga_dir"]

    if not local_files:
        await query.edit_message_text("所有图片下载失败")
        shutil.rmtree(manga_dir, ignore_errors=True)
        _get_biz_logger().warning("全部下载失败: %s #%s", manga_id, chapter_num)
        return

    total = len(local_files)
    dl_sec = time.time() - t0
    _prog_logger.info("downloaded %d/%d images (%.1fs), uploading...", total, total + failed, dl_sec)

    await query.edit_message_text(f"上传到 {CHANNEL_ID} ({total} 张)…")

    # 上传
    batch_size = 10
    for batch_idx in range(0, total, batch_size):
        batch = local_files[batch_idx : batch_idx + batch_size]
        media_group = []
        for j, fp in enumerate(batch):
            abs_path = os.path.abspath(fp).replace("\\", "/")
            if batch_idx == 0 and j == 0:
                caption = f"{manga_name}\n{chapter_name} ({batch_idx + 1}/{total})"
            else:
                caption = None
            media_group.append(
                InputMediaPhoto(media=open(abs_path, "rb"), caption=caption)
            )

        try:
            await context.bot.send_media_group(chat_id=CHANNEL_ID, media=media_group)
        except TelegramError as e:
            _prog_logger.error("upload failed: %s", e)
            await query.edit_message_text(f"上传失败: {escape(str(e))}")
            shutil.rmtree(manga_dir, ignore_errors=True)
            return

        if batch_idx + batch_size < total:
            await asyncio.sleep(1)

    # 清理
    shutil.rmtree(manga_dir, ignore_errors=True)
    total_sec = time.time() - t0

    biz = _get_biz_logger()
    biz.info("上传完成: %s #%s | 图片=%d 失败=%d 耗时=%.1fs | 用户=%s",
             manga_name, chapter_name, total, failed, total_sec,
             user.username or user.id)

    _prog_logger.info("upload done: %s #%s (%d imgs, %.1fs)", manga_id, chapter_num, total, total_sec)

    await query.edit_message_text(
        f"已上传到 {CHANNEL_ID}\n{manga_name} — {chapter_name}\n共 {total} 张 (耗时 {total_sec:.0f}s)"
    )


def main():
    _prog_logger.info("Bot starting...")
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("recent", cmd_recent))
    app.add_handler(CallbackQueryHandler(on_chapter_select))

    _prog_logger.info("Bot polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
