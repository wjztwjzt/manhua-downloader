# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

从 gugu5.com 漫画网站抓取并下载漫画图片到本地，支持 CLI 命令和 Telegram Bot 两种方式。可将图片上传到 Telegram 频道。

## 技术栈

- Python 3 + `requests` + `python-telegram-bot`
- SQLite3（标准库）存储漫画、章节、图片记录
- 网页编码：GB2312（网站使用 GB2312，非 UTF-8）

## 项目结构

| 文件 | 职责 |
|------|------|
| `main.py` | CLI 入口，子命令：`download`、`list`、`download-all` |
| `bot.py` | Telegram Bot，命令 `/recent` + 章节选择回调解锁下载上传 |
| `fetcher.py` | HTTP 请求 + HTML 解析（正则提取章节列表、base64 解码图片 URL） |
| `db.py` | SQLite 建表与 CRUD（manga / chapters / images 三表） |
| `config.py` | 全局常量（BASE_URL、下载目录、数据库路径、超时时间） |
| `bot_config.py` | Bot Token 和频道 ID（已加入 .gitignore，不提交） |

## 命令

```bash
# 安装依赖
pip install requests python-telegram-bot

# CLI — 列出所有章节
python main.py list <manga_id>

# CLI — 下载指定章节
python main.py download <manga_id> <章节号>

# CLI — 下载全部章节
python main.py download-all <manga_id>

# 启动 Telegram Bot
python bot.py
```

## Telegram Bot

- Bot: `@mhgxa_bot`
- 频道: `@mhgxin`
- 命令：
  - `/start` — 欢迎信息
  - `/recent <manga_id>` — 查看最近 20 个章节，点击按钮下载并上传到频道
- 上传完成后自动删除本地文件

## 数据库表结构

- **manga** — 漫画基本信息（id, name, url, cover_url, description）
- **chapters** — 章节信息（id, manga_id, chapter_name, chapter_order, url, downloaded）
- **images** — 图片记录（chapter_id, image_url, page_num, local_path, downloaded）

## 注意事项

- 网站章节页中图片 URL 以 base64 编码存储在 JS 变量 `qTcms_S_m_murl_e` 中，分隔符 `$qingtiandy$`
- 章节编号匹配基于章节名中的「第X话」数字，非 `chapter_order` 字段（含番外偏移）
- 旧章节图片服务器可能已失效，新章节使用 CDN
- 章节列表从页面 `initIntroData(...)` 中正则提取，不完整解析 JSON（含无效转义）
- `bot_config.py` 含敏感凭证，已加入 .gitignore
