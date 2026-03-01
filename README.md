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





MAX → Telegram Bridge

Мост для пересылки сообщений из мессенджера MAX в Telegram-канал с указанием темы.

  Функции

- Пересылка текста, фотографий, видео и файлов
- Автоматическое определение темы
- Добавляет #дз только при обнаружении предмета
- Добавляет #прочее в противном случае
- Работает круглосуточно через systemd
- Автоматическое переподключение
ПО ВОПРОСАМ tg @DEL3Tru тгк со всей этой херней @DNSsystem
ПРИМЕЧАНИЕ
Это все писал школьник которому было просто не чего делать фулл код был написан через chat gpt,репозиторий создан для того что бы другие просто не тратили время на повторение данного кода
СПАСИБО ЗА ПРОЧТЕНИЕ И ИСПОЛЬЗОВАНИЯ КОДА ОТ DEL3Tru
