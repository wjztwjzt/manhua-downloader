#!/bin/bash
set -e

HOST="sz1"
TARGET="/data/manhua"
VENV="$TARGET/.venv"

echo "=== 部署到 $HOST:$TARGET ==="

# 1. 创建目录
ssh "$HOST" "mkdir -p $TARGET/logs $TARGET/downloads"

# 2. 上传代码
tar czf - \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='logs' \
    --exclude='downloads' \
    --exclude='.git' \
    --exclude='.gitignore' \
    --exclude='.claude' \
    --exclude='manhua.db' \
    . | ssh "$HOST" "cd $TARGET && tar xzf -"

# 3. 创建虚拟环境并安装依赖
ssh "$HOST" "python3 -m venv $VENV && $VENV/bin/pip install -r $TARGET/requirements.txt -q"

# 4. 安装 systemd 服务
ssh "$HOST" "cp $TARGET/manhua-bot.service /etc/systemd/system/ && systemctl daemon-reload"

# 5. 重启服务
ssh "$HOST" "systemctl enable manhua-bot && systemctl restart manhua-bot"

echo "=== 部署完成 ==="
echo ""
echo "查看状态: ssh $HOST systemctl status manhua-bot"
echo "查看程序日志: ssh $HOST journalctl -u manhua-bot -f"
echo "查看业务日志: ssh $HOST tail -f $TARGET/logs/bot.log"
