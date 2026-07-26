import re
import base64
import requests
from config import BASE_URL, MANGA_LIST_PATH, REQUEST_TIMEOUT


def fetch_manga_page(manga_id):
    """获取漫画首页，返回 HTML 文本"""
    url = BASE_URL + MANGA_LIST_PATH.format(manga_id=manga_id)
    resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    resp.encoding = "gb2312"
    return resp.text


def _extract_chapters_from_js(html):
    """使用正则从 JS 中提取所有章节条目，避免完整 JSON 解析（数据可能有无效转义）"""
    chapters = []
    # 匹配每个章节对象: { "id": ..., "comic_id": ..., "chapter_name": "...", "chapter_order": ..., ... "h":"..." }
    for m in re.finditer(
        r'\{\s*"id":\s*(\d+).*?"comic_id":\s*(\d+).*?"chapter_name":\s*"((?:[^"\\]|\\.)*)".*?"chapter_order":\s*(-?\d+).*?"h":\s*"(http://m\.gugu5\.com[^"]+)"',
        html, re.DOTALL
    ):
        chapters.append({
            "id": int(m.group(1)),
            "comic_id": int(m.group(2)),
            "chapter_name": m.group(3).replace("\\/", "/"),
            "chapter_order": int(m.group(4)),
            "url": m.group(5).replace("http://m.gugu5.com", ""),
        })
    return chapters


def parse_manga_info(html, manga_id):
    """从漫画首页解析漫画基本信息和章节列表"""
    info = {}

    # 漫画名称
    m = re.search(r'id="comicName"[^>]*>([^<]+)<', html)
    if m:
        info["name"] = m.group(1).strip()

    # 封面图
    m = re.search(r'id="Cover"[^>]*>.*?<img\s+src="([^"]+)"', html, re.DOTALL)
    if m:
        info["cover_url"] = m.group(1)

    # 描述
    m = re.search(r'class="txtDesc[^"]*"[^>]*>([^<]+)', html)
    if m:
        info["description"] = m.group(1).strip()

    info["chapters"] = _extract_chapters_from_js(html)
    return info


def fetch_chapter_page(chapter_url):
    """获取章节页面，返回 HTML 文本"""
    url = BASE_URL + chapter_url
    resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    resp.encoding = "gb2312"
    return resp.text


def parse_chapter_images(html):
    """从章节页面解析图片 URL 列表"""
    m = re.search(r'var qTcms_S_m_murl_e="([^"]+)"', html)
    if not m:
        return []

    encoded = m.group(1)
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except Exception:
        return []

    return [u for u in decoded.split("$qingtiandy$") if u.strip()]
