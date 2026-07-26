import asyncio
import os
import re
import shutil
from html import escape

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from telegram.error import TelegramError

from bot_config import BOT_TOKEN, CHANNEL_ID
from config import DOWNLOAD_DIR
from fetcher import fetch_manga_page, parse_manga_info, fetch_chapter_page, parse_chapter_images

RECENT_COUNT = 20


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


async def cmd_recent(update, context):
    args = context.args
    if not args:
        await update.message.reply_text("请提供漫画ID，例如：/recent woshidashenxian")
        return

    manga_id = args[0]
    msg = await update.message.reply_text("正在获取章节列表…")

    try:
        html = fetch_manga_page(manga_id)
        info = parse_manga_info(html, manga_id)
    except Exception as e:
        await msg.edit_text(f"获取漫画信息失败: {escape(str(e))}")
        return

    chapters = info.get("chapters", [])
    # 过滤有有效显示编号的章节，取最近 RECENT_COUNT 个
    valid = [ch for ch in chapters if _display_num(ch["chapter_name"]) is not None]
    valid.sort(key=lambda ch: _display_num(ch["chapter_name"]), reverse=True)
    recent = valid[:RECENT_COUNT]
    # 按编号升序排列便于阅读
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

    # 上一页/下一页占位（后续可实现分页）
    await msg.edit_text(
        f"📖 {name} — 最近章节",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def on_chapter_select(update, context):
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data.startswith("dl|"):
        return

    _, manga_id, chapter_str = data.split("|", 2)
    chapter_num = int(chapter_str)

    # 判断是下载还是仅显示详情
    text = query.message.text or ""
    await query.edit_message_text(f"⏳ 正在下载第 {chapter_num} 话…")

    try:
        html = fetch_manga_page(manga_id)
        info = parse_manga_info(html, manga_id)
    except Exception as e:
        await query.edit_message_text(f"获取漫画信息失败: {escape(str(e))}")
        return

    target = _find_chapter_by_display(info["chapters"], chapter_num)
    if target is None:
        await query.edit_message_text(f"未找到第 {chapter_num} 话")
        return

    chapter_name = target["chapter_name"]
    manga_name = info.get("name", manga_id)

    # 获取图片 URL
    try:
        chapter_html = fetch_chapter_page(target["url"])
        image_urls = parse_chapter_images(chapter_html)
    except Exception as e:
        await query.edit_message_text(f"获取图片列表失败: {escape(str(e))}")
        return

    if not image_urls:
        await query.edit_message_text("未找到图片")
        return

    # 下载图片
    manga_dir = os.path.join(DOWNLOAD_DIR, manga_id, str(chapter_num))
    os.makedirs(manga_dir, exist_ok=True)
    local_files = []

    for i, img_url in enumerate(image_urls, 1):
        ext = img_url.rsplit(".", 1)[-1].split("?")[0] or "jpg"
        if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
            ext = "jpg"
        filepath = os.path.join(manga_dir, f"{i:03d}.{ext}")

        try:
            r = requests.get(img_url, timeout=30)
            if r.status_code == 200:
                with open(filepath, "wb") as f:
                    f.write(r.content)
                local_files.append(filepath)
        except Exception:
            pass

    if not local_files:
        await query.edit_message_text("所有图片下载失败")
        shutil.rmtree(manga_dir, ignore_errors=True)
        return

    total = len(local_files)
    await query.edit_message_text(f"📤 正在上传到 {CHANNEL_ID} ({total} 张)…")

    # 按每组最多10张分批发送 media group
    batch_size = 10
    for batch_idx in range(0, total, batch_size):
        batch = local_files[batch_idx : batch_idx + batch_size]
        media_group = []
        for j, fp in enumerate(batch):
            abs_path = os.path.abspath(fp)
            # os.path.abspath 在 Windows 上生成反斜杠路径，需要转为正斜杠用于 file:// URI
            abs_path = abs_path.replace("\\", "/")
            if batch_idx == 0 and j == 0:
                caption = f"📖 {manga_name}\n{chapter_name} ({batch_idx + 1}/{total})"
            else:
                caption = None
            media_group.append(
                InputMediaPhoto(
                    media=open(abs_path, "rb"),
                    caption=caption,
                )
            )

        try:
            await context.bot.send_media_group(
                chat_id=CHANNEL_ID,
                media=media_group,
            )
        except TelegramError as e:
            await query.edit_message_text(f"上传失败: {escape(str(e))}")
            shutil.rmtree(manga_dir, ignore_errors=True)
            return

        if batch_idx + batch_size < total:
            await asyncio.sleep(1)

    # 删除本地文件
    shutil.rmtree(manga_dir, ignore_errors=True)

    await query.edit_message_text(
        f"✅ 已上传到 {CHANNEL_ID}\n{manga_name} — {chapter_name}\n共 {total} 张图片"
    )


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("recent", cmd_recent))
    app.add_handler(CallbackQueryHandler(on_chapter_select))

    print("Bot started. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
