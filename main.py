import argparse
import os
import sys
import time

import requests

import re

from config import DOWNLOAD_DIR
from db import (
    init_db,
    save_manga,
    save_chapter,
    get_chapters,
    mark_chapter_downloaded,
    save_image,
)
from fetcher import (
    fetch_manga_page,
    parse_manga_info,
    fetch_chapter_page,
    parse_chapter_images,
)


def _display_num(chapter_name):
    """从章节名称中提取显示编号（如 "第832话 xxx" → 832）"""
    m = re.search(r"第\s*(\d+)\s*话", chapter_name)
    return int(m.group(1)) if m else None


def _find_chapter(chapters, user_num):
    """按用户输入的编号查找章节：优先匹配章节名中的显示编号"""
    # 1. 精确匹配章节名中的数字
    for ch in chapters:
        dn = _display_num(ch["chapter_name"])
        if dn is not None and dn == user_num:
            return ch
    # 2. 模糊匹配章节名
    s = str(user_num)
    for ch in chapters:
        if s in ch["chapter_name"]:
            return ch
    return None


def download_image(url, filepath, retries=3):
    """下载单张图片到本地，支持重试"""
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                with open(filepath, "wb") as f:
                    f.write(resp.content)
                return True
        except Exception:
            if attempt < retries - 1:
                time.sleep(1)
    return False


def cmd_download(manga_id, chapter_num):
    """下载指定漫画的指定章节"""
    init_db()

    print(f"[1/4] 正在获取漫画信息: {manga_id}")
    html = fetch_manga_page(manga_id)
    info = parse_manga_info(html, manga_id)

    if not info.get("chapters"):
        print("错误: 未找到任何章节信息")
        sys.exit(1)

    print(f"  漫画: {info.get('name', '未知')}")
    print(f"  共 {len(info['chapters'])} 个章节")

    # 保存漫画信息
    save_manga(
        manga_id=manga_id,
        name=info.get("name", manga_id),
        url=f"http://m.gugu5.com/o/{manga_id}/",
        cover_url=info.get("cover_url"),
        description=info.get("description"),
    )

    # 查找指定章节
    target = _find_chapter(info["chapters"], chapter_num)

    if target is None:
        print(f"错误: 未找到第 {chapter_num} 话")
        sys.exit(1)

    print(f"\n[2/4] 目标章节: {target['chapter_name']}")

    # 保存章节到数据库
    save_chapter(target["id"], manga_id, target["chapter_name"], target["chapter_order"], target["url"])

    # 获取章节页面的图片列表
    print("[3/4] 正在获取图片列表...")
    chapter_html = fetch_chapter_page(target["url"])
    image_urls = parse_chapter_images(chapter_html)

    if not image_urls:
        print("错误: 未找到图片")
        sys.exit(1)

    print(f"  共 {len(image_urls)} 张图片")

    # 下载图片
    print("[4/4] 正在下载图片...")
    manga_dir = os.path.join(DOWNLOAD_DIR, manga_id, str(chapter_num))
    os.makedirs(manga_dir, exist_ok=True)

    for i, img_url in enumerate(image_urls, 1):
        ext = img_url.rsplit(".", 1)[-1].split("?")[0] or "jpg"
        if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
            ext = "jpg"
        filename = f"{i:03d}.{ext}"
        filepath = os.path.join(manga_dir, filename)

        print(f"  [{i}/{len(image_urls)}] {img_url[:60]}...", end=" ", flush=True)
        if download_image(img_url, filepath):
            save_image(target["id"], img_url, i, filepath)
            print("OK")
        else:
            save_image(target["id"], img_url, i)
            print("失败")

    mark_chapter_downloaded(target["id"])
    print(f"\n完成! 已保存到: {manga_dir}")


def cmd_list(manga_id):
    """列出漫画的所有章节"""
    init_db()

    # 先尝试从数据库读取
    chapters = get_chapters(manga_id)
    if not chapters:
        print(f"正在从网络获取 {manga_id} 的章节列表...")
        html = fetch_manga_page(manga_id)
        info = parse_manga_info(html, manga_id)
        if not info.get("chapters"):
            print("未找到章节信息")
            sys.exit(1)
        save_manga(
            manga_id=manga_id,
            name=info.get("name", manga_id),
            url=f"http://m.gugu5.com/o/{manga_id}/",
            cover_url=info.get("cover_url"),
            description=info.get("description"),
        )
        for ch in info["chapters"]:
            save_chapter(ch["id"], manga_id, ch["chapter_name"], ch["chapter_order"], ch["url"])
        chapters = get_chapters(manga_id)

    print(f"漫画: {manga_id}")
    print(f"共 {len(chapters)} 个章节:")
    for ch in chapters:
        status = " [已下载]" if ch["downloaded"] else ""
        print(f"  {ch['chapter_name']}{status}")


def cmd_download_all(manga_id):
    """下载漫画的所有章节"""
    init_db()

    print(f"[1/3] 正在获取漫画信息: {manga_id}")
    html = fetch_manga_page(manga_id)
    info = parse_manga_info(html, manga_id)

    if not info.get("chapters"):
        print("错误: 未找到任何章节信息")
        sys.exit(1)

    chapters = info["chapters"]
    print(f"  漫画: {info.get('name', '未知')}")
    print(f"  共 {len(chapters)} 个章节待下载")

    save_manga(
        manga_id=manga_id,
        name=info.get("name", manga_id),
        url=f"http://m.gugu5.com/o/{manga_id}/",
        cover_url=info.get("cover_url"),
        description=info.get("description"),
    )

    for idx, ch in enumerate(chapters):
        chapter_num = ch["chapter_order"]
        save_chapter(ch["id"], manga_id, ch["chapter_name"], chapter_num, ch["url"])

        print(f"\n[2/3] ({idx+1}/{len(chapters)}) 章节: {ch['chapter_name']}")

        chapter_html = fetch_chapter_page(ch["url"])
        image_urls = parse_chapter_images(chapter_html)

        if not image_urls:
            print("  跳过: 无图片")
            continue

        print(f"  {len(image_urls)} 张图片, 开始下载...")

        manga_dir = os.path.join(DOWNLOAD_DIR, manga_id, str(chapter_num))
        os.makedirs(manga_dir, exist_ok=True)

        for i, img_url in enumerate(image_urls, 1):
            ext = img_url.rsplit(".", 1)[-1].split("?")[0] or "jpg"
            if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
                ext = "jpg"
            filepath = os.path.join(manga_dir, f"{i:03d}.{ext}")

            if download_image(img_url, filepath):
                save_image(ch["id"], img_url, i, filepath)
            else:
                save_image(ch["id"], img_url, i)

        mark_chapter_downloaded(ch["id"])
        time.sleep(1)  # 请求间隔，避免被封

    print(f"\n全部完成! 保存路径: {os.path.join(DOWNLOAD_DIR, manga_id)}")


def main():
    parser = argparse.ArgumentParser(description="漫画下载器 - 从 gugu5.com 下载漫画")
    subparsers = parser.add_subparsers(dest="command", help="命令")

    # download 命令
    dl = subparsers.add_parser("download", help="下载指定章节")
    dl.add_argument("manga_id", help="漫画ID，如 woshidashenxian")
    dl.add_argument("chapter", type=int, help="章节号，如 832")

    # list 命令
    ls = subparsers.add_parser("list", help="列出所有章节")
    ls.add_argument("manga_id", help="漫画ID")

    # download-all 命令
    dla = subparsers.add_parser("download-all", help="下载所有章节")
    dla.add_argument("manga_id", help="漫画ID")

    args = parser.parse_args()

    if args.command == "download":
        cmd_download(args.manga_id, args.chapter)
    elif args.command == "list":
        cmd_list(args.manga_id)
    elif args.command == "download-all":
        cmd_download_all(args.manga_id)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
