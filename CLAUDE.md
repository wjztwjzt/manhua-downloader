# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

从 gugu5.com 漫画网站抓取并下载漫画图片到本地，支持 CLI 命令和 Telegram Bot 两种方式。Bot 可将图片自动上传到 Telegram 频道 `@mhgxin`。

## 技术栈

- Python 3 + `requests` + `python-telegram-bot`
- SQLite3（标准库）存储漫画、章节、图片记录
- 网页编码：GB2312（网站使用 GB2312，非 UTF-8）
- systemd 服务保活，journalctl 程序日志，`logs/` 目录业务日志

## 项目结构

| 文件 | 职责 |
|------|------|
| `main.py` | CLI 入口，子命令：`download`、`list`、`download-all` |
| `bot.py` | Telegram Bot，`/recent` 命令 + 章节选择回调 → 下载上传 |
| `fetcher.py` | HTTP 请求 + HTML 解析（正则提取章节、base64 解码图片 URL） |
| `db.py` | SQLite 建表与 CRUD（manga / chapters / images 三表） |
| `config.py` | 全局常量（BASE_URL、下载目录、数据库路径、超时时间） |
| `bot_config.py` | Bot Token + 频道 ID（已加入 .gitignore） |
| `deploy.sh` | 一键部署到 sz1:/data/manhua |
| `manhua-bot.service` | systemd 服务定义 |

## 命令

```bash
# 安装依赖
pip install requests python-telegram-bot

# CLI — 列出章节 / 下载
python main.py list <manga_id>
python main.py download <manga_id> <章节号>
python main.py download-all <manga_id>

# 本地启动 Bot
python bot.py

# 部署到服务器
bash deploy.sh
```

## Telegram Bot

- Bot: `@mhgxa_bot`
- 频道: `@mhgxin`
- `/start` — 欢迎
- `/recent <manga_id>` — 最近 20 章节，点击按钮下载上传
- 上传完成后自动删除本地文件

## 部署 (sz1:/data/manhua)

- 服务器: `ssh sz1`
- systemd 服务: `systemctl status manhua-bot`
- 程序日志: `journalctl -u manhua-bot -f`
- 业务日志: `tail -f /data/manhua/logs/bot.log`
- Python venv: `/data/manhua/.venv/`

## 日志体系

- **程序日志** → stdout → journald → `journalctl -u manhua-bot`（启动/错误/关键操作）
- **业务日志** → `logs/bot.log`（下载上传记录、用户操作、耗时统计），RotatingFileHandler，10MB×5

## 数据库表结构

- **manga** — 漫画基本信息（id, name, url, cover_url, description）
- **chapters** — 章节信息（id, manga_id, chapter_name, chapter_order, url, downloaded）
- **images** — 图片记录（chapter_id, image_url, page_num, local_path, downloaded）

## 注意事项

- 章节页图片 URL 以 base64 编码存储在 `qTcms_S_m_murl_e`，分隔符 `$qingtiandy$`
- 章节编号匹配基于章节名中「第X话」数字，非 `chapter_order`（含番外偏移）
- 旧章节图片服务器可能已失效，新章节使用 CDN
- 章节列表从 `initIntroData(...)` 正则提取，不完整解析 JSON（含无效转义）
- `bot_config.py` 含敏感凭证，已加入 .gitignore
- 服务器 Ubuntu 24.04 使用 externally-managed Python，必须用 venv
