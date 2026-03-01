import os
import re
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import aiohttp
from dotenv import load_dotenv

from pymax import SocketMaxClient, Message
from pymax.types import PhotoAttach, VideoAttach, FileAttach

# -------------------- ENV --------------------
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("bridge")

# -------------------- SUBJECTS --------------------
SUBJECT_KEYWORDS = {
    "химия": ["химия", "химии", "хим"],
    "алгебра": ["алгебра", "алг", "алгебры"],
    "геометрия": ["геометрия", "геом", "геометрии"],
    "вис": ["вис"],
    "русский": ["русский", "русского", "рус", "русс"],
    "информатика": ["информатика", "инфа", "информ"],
    "физика": ["физика", "физ"],
    "английский": ["английский", "английского", "англ"],
    "биология": ["биология", "био", "биологии"],
    "история": ["история", "ист", "истории"],
    "обществознание": ["обществознание", "общага", "обществ"],
    "литература": ["литература", "лит", "литры"],
}

MULTI_SPACES = re.compile(r"[ \t]+")
MULTI_NEWLINES = re.compile(r"\n{3,}")

MAX_PHONE = os.environ["MAX_PHONE"]
MAX_CHAT_ID = int(os.environ["MAX_CHAT_ID"])

TG_BOT_TOKEN = os.environ["TG_BOT_TOKEN"]
TG_TARGET = os.environ["TG_TARGET"]

WORK_DIR = os.environ.get("WORK_DIR", "/root/max/session_socket")
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "60"))

INCLUDE_HEADER = os.environ.get("INCLUDE_HEADER", "false").lower() == "true"
TZ = ZoneInfo(os.environ.get("TZ", "Europe/Moscow"))

RESTART_DELAY = int(os.environ.get("RESTART_DELAY", "10"))

# -------------------- TELEGRAM API --------------------
async def tg_call(method: str, data: dict, files: dict | None = None):
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/{method}"
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        if files:
            form = aiohttp.FormData()
            for k, v in data.items():
                if v is not None:
                    form.add_field(k, str(v))
            for field, (filename, content, ctype) in files.items():
                form.add_field(field, content, filename=filename, content_type=ctype)
            async with session.post(url, data=form) as r:
                js = await r.json(content_type=None)
        else:
            async with session.post(url, json=data) as r:
                js = await r.json(content_type=None)

    if not js.get("ok"):
        log.error(f"Telegram API error on {method}: {js}")
        raise RuntimeError(js)

    return js["result"]


async def tg_send_message(text: str):
    return await tg_call("sendMessage", {"chat_id": TG_TARGET, "text": text})


async def tg_send_photo(photo_bytes: bytes, caption: str | None):
    return await tg_call(
        "sendPhoto",
        {"chat_id": TG_TARGET, "caption": caption},
        files={"photo": ("photo.jpg", photo_bytes, "image/jpeg")},
    )


async def tg_send_video(video_bytes: bytes, caption: str | None):
    # Telegram сам определит тип по контенту, но filename/mp4 помогает
    return await tg_call(
        "sendVideo",
        {"chat_id": TG_TARGET, "caption": caption},
        files={"video": ("video.mp4", video_bytes, "video/mp4")},
    )


async def tg_send_document(doc_bytes: bytes, filename: str, caption: str | None):
    return await tg_call(
        "sendDocument",
        {"chat_id": TG_TARGET, "caption": caption},
        files={"document": (filename or "file", doc_bytes, "application/octet-stream")},
    )

# -------------------- HELPERS --------------------
async def download(url: str) -> bytes:
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as r:
            r.raise_for_status()
            return await r.read()


def normalize_text(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    text = MULTI_SPACES.sub(" ", text)
    text = MULTI_NEWLINES.sub("\n\n", text)
    return text.strip()


def detect_subjects(text: str) -> list[str]:
    t = (text or "").lower()
    found = []
    for subject, keywords in SUBJECT_KEYWORDS.items():
        for kw in keywords:
            if kw and kw in t:
                found.append(subject)
                break
    return list(dict.fromkeys(found))


def format_datetime(msg: Message) -> str:
    dt = None
    for attr in ("created_at", "time", "date", "timestamp"):
        v = getattr(msg, attr, None)
        if isinstance(v, datetime):
            dt = v
            break
    if dt is None:
        dt = datetime.now(TZ)
    else:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        else:
            dt = dt.astimezone(TZ)
    return dt.strftime("%d.%m.%Y %H:%M")


async def get_sender_name(client: SocketMaxClient, user_id: int) -> str:
    try:
        user = await client.get_user(user_id=user_id)
        if user and getattr(user, "names", None):
            return user.names[0].name
    except Exception as e:
        log.warning(f"Cannot fetch sender name for {user_id}: {e}")
    return f"User {user_id}"


def build_message(original_text: str, subjects: list[str], header: str | None):
    """
    Правило тегов:
      - если найден предмет -> #дз + #предметы
      - если предмет НЕ найден -> только #прочее (без #дз)
    """
    body = normalize_text(original_text)

    if not subjects:
        tag_line = "#прочее"
    else:
        tags = ["#дз"] + [f"#{s}" for s in subjects]
        tag_line = " ".join(tags)

    if header:
        if body:
            return f"{header}\n\n{body}\n\n{tag_line}"
        return f"{header}\n\n{tag_line}"

    if body:
        return f"{body}\n\n{tag_line}"
    return tag_line


def pick_video_url(attach: VideoAttach, info_obj) -> str | None:
    """
    В разных версиях PyMax ссылка может лежать по-разному.
    Пробуем максимум вариантов.
    """
    # 1) из info (предпочтительно)
    if info_obj is not None:
        for key in ("url", "video_url", "file_url", "download_url"):
            u = getattr(info_obj, key, None)
            if isinstance(u, str) and u.startswith("http"):
                return u

    # 2) прямо из attach
    for key in ("url", "base_url", "video_url", "file_url", "download_url"):
        u = getattr(attach, key, None)
        if isinstance(u, str) and u.startswith("http"):
            return u

    return None


# -------------------- CLIENT --------------------
def make_client() -> SocketMaxClient:
    c = SocketMaxClient(MAX_PHONE, work_dir=WORK_DIR, reconnect=True)

    @c.on_message()
    async def on_message(message: Message):
        try:
            log.info(
                f"INCOMING: chat_id={getattr(message,'chat_id',None)} "
                f"sender={getattr(message,'sender',None)} "
                f"text={getattr(message,'text',None)!r} "
                f"attaches={bool(getattr(message,'attaches',None))}"
            )

            if getattr(message, "chat_id", None) != MAX_CHAT_ID:
                return

            text = (getattr(message, "text", "") or "").strip()
            subjects = detect_subjects(text)

            header = None
            if INCLUDE_HEADER:
                sender = await get_sender_name(c, message.sender)
                dt = format_datetime(message)
                header = f"{sender} • {dt}"

            final_text = build_message(text, subjects, header)

            # Telegram лимиты (чтобы не падать)
            if len(final_text) > 3500:
                final_text = final_text[:3500].rstrip() + "\n\n#прочее"

            caption_used = False
            attaches = getattr(message, "attaches", None) or []

            for a in attaches:
                try:
                    if isinstance(a, PhotoAttach):
                        content = await download(a.base_url)
                        await tg_send_photo(content, final_text if not caption_used else None)
                        caption_used = True

                    elif isinstance(a, VideoAttach):
                        info = None
                        try:
                            # у некоторых сообщений message.id может быть None, страхуемся
                            if getattr(message, "id", None) is not None:
                                info = await c.get_video_by_id(message.chat_id, message.id, a.video_id)
                        except Exception as e:
                            log.warning(f"get_video_by_id failed: {e}")

                        url = pick_video_url(a, info)
                        if not url:
                            # чтобы не было "пустоты"
                            warn_text = final_text + "\n\n(⚠️ не удалось получить ссылку на видео)"
                            await tg_send_message(warn_text)
                            caption_used = True
                        else:
                            content = await download(url)
                            # Если sendVideo не пройдёт (размер/формат), отправим как документ
                            try:
                                await tg_send_video(content, final_text if not caption_used else None)
                            except Exception as e:
                                log.warning(f"sendVideo failed, fallback to document: {e}")
                                await tg_send_document(content, "video.mp4", final_text if not caption_used else None)
                            caption_used = True

                    elif isinstance(a, FileAttach):
                        info = await c.get_file_by_id(message.chat_id, message.id, a.file_id)
                        if info and getattr(info, "url", None):
                            filename = getattr(info, "name", "file")
                            content = await download(info.url)
                            await tg_send_document(content, filename, final_text if not caption_used else None)
                            caption_used = True

                except Exception as e:
                    log.exception(f"Attachment processing failed: {e}")

            if not caption_used:
                await tg_send_message(final_text)

            log.info(f"FORWARDED OK: max_id={getattr(message,'id',None)}")

        except Exception as e:
            log.exception(f"Handler error (won't crash client): {e}")

    return c


# -------------------- SUPERVISOR --------------------
async def main():
    log.info("Starting MAX -> Telegram bridge (SOCKET)…")
    log.info(f"WORK_DIR={WORK_DIR}")
    log.info(f"MAX_CHAT_ID filter = {MAX_CHAT_ID}")

    while True:
        client = make_client()
        try:
            await client.start()
            log.warning(f"client.start() finished unexpectedly. Restart in {RESTART_DELAY}s...")
            await asyncio.sleep(RESTART_DELAY)
        except KeyboardInterrupt:
            log.info("Stopping by Ctrl+C…")
            break
        except Exception as e:
            log.exception(f"Client crashed, restart in {RESTART_DELAY}s: {e}")
            await asyncio.sleep(RESTART_DELAY)
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                try:
                    await close()
                except Exception:
                    pass


if __name__ == "__main__":
    asyncio.run(main())
