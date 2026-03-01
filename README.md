# MAX → Telegram Bridge

Bridge for forwarding messages from MAX messenger to Telegram channel with subject tagging.

## Features

- Forwards text, photos, videos and files
- Auto subject detection
- Adds #дз only if subject detected
- Adds #прочее otherwise
- Works 24/7 via systemd
- Auto reconnect

## Installation

```bash
git clone https://github.com/DEL3Tru/
---bridge-MaX-to-Telegram-
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
python3 max_to_tg_bridge.py
