#!/usr/bin/env bash
# Обновление бота на сервере: свежий код, зависимости, перезапуск.
set -euo pipefail

cd "$(dirname "$0")"

SERVICE="kazikbot"
TMUX_SESSION="kazikbot"

echo "==> Забираю свежий код"
git pull --ff-only origin main

echo "==> Ставлю зависимости"
if [ -d venv ]; then
    ./venv/bin/pip install -q -r requirements.txt
    PYTHON="$PWD/venv/bin/python3"
else
    pip install -q -r requirements.txt
    PYTHON="$(command -v python3)"
fi

echo "==> Перезапускаю бота"
if systemctl list-unit-files "$SERVICE.service" >/dev/null 2>&1 \
   && systemctl cat "$SERVICE" >/dev/null 2>&1; then
    # Вариант 1: бот живёт под systemd
    sudo systemctl restart "$SERVICE"
    sudo systemctl --no-pager status "$SERVICE" | head -5
elif command -v tmux >/dev/null 2>&1; then
    # Вариант 2: бот живёт в tmux-сессии
    tmux kill-session -t "$TMUX_SESSION" 2>/dev/null || true
    tmux new-session -d -s "$TMUX_SESSION" "$PYTHON main.py"
    echo "Бот запущен в tmux-сессии '$TMUX_SESSION'."
    echo "Посмотреть логи: tmux attach -t $TMUX_SESSION (выйти: Ctrl+B, затем D)"
else
    echo "Не нашёл ни systemd-юнита '$SERVICE', ни tmux." >&2
    echo "Запусти бота вручную: $PYTHON main.py" >&2
    exit 1
fi

echo "==> Готово"
