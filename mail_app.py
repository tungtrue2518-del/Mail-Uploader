import base64
import csv
import datetime
import html
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
import uuid

import webview
from webview import FileDialog

if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
    RESOURCE_DIR = sys._MEIPASS
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    RESOURCE_DIR = APP_DIR

CATEGORIES_FILE = os.path.join(APP_DIR, "categories.json")
SEND_LOG_FILE = os.path.join(APP_DIR, "send_log.json")
SCHEDULED_FILE = os.path.join(APP_DIR, "scheduled_sends.json")
CONFIG_FILE = os.path.join(APP_DIR, "config.json")

APP_VERSION = "3.0.0"
APP_BUILD_DATE = "2026-07-16"

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

THUNDERBIRD_CANDIDATES = [
    r"C:\Program Files\Mozilla Thunderbird\thunderbird.exe",
    r"C:\Program Files (x86)\Mozilla Thunderbird\thunderbird.exe",
]


def find_thunderbird() -> str:
    for path in THUNDERBIRD_CANDIDATES:
        if os.path.isfile(path):
            return path
    found = shutil.which("thunderbird")
    if found:
        return found
    raise FileNotFoundError("ไม่พบโปรแกรม Thunderbird ในเครื่องนี้")


DEFAULT_CONFIG = {
    "advice_root": r"C:\Users\IT-5\Desktop\Advice Order\ใบเสนอราคา Quotaion ( รวม)",
    "advice_to": "avi.commercial@advice.co.th",
    "advice_cc": "kaweewat.k@vel-suede.co.th, vsth_it@vel-suede.com",
    # Per-machine digital signature — deliberately editable in Settings, not
    # hardcoded per-person in source, since this app runs under whichever IT
    # staff member's Windows session is active (Tung/Arm/Bee/...). These
    # defaults are just this machine's (IT-5, Tung's) own real details.
    "sig_name": "Purinat Lexuthai",
    "sig_position": "IT SUPPORT STAFF",
    "sig_email": "isdpt5@vsth.lan",
    "sig_it_call": "123",
}


def load_config() -> dict:
    if not os.path.isfile(CONFIG_FILE):
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(DEFAULT_CONFIG)
        merged.update({k: v for k, v in data.items() if v})
        return merged
    except Exception:
        return dict(DEFAULT_CONFIG)


def save_config(data: dict) -> None:
    """Merges into the existing saved config instead of replacing it
    wholesale — otherwise saving the Advice settings would wipe out a
    separately-saved signature (and vice versa), since each caller only
    passes the subset of fields it owns."""
    existing = {}
    if os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = {}
        try:
            shutil.copyfile(CONFIG_FILE, CONFIG_FILE + ".bak")
        except Exception:
            pass
    existing.update(data)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


def advice_root() -> str:
    return load_config()["advice_root"]


def advice_to() -> str:
    return load_config()["advice_to"]


def advice_cc() -> str:
    return load_config()["advice_cc"]


def folder_step1() -> str:
    return os.path.join(advice_root(), "ใบเสนอราคาขั้น 1")


def folder_step3() -> str:
    return os.path.join(advice_root(), "ใบเสนอราคาขั้น 3")


def signature_config() -> dict:
    cfg = load_config()
    return {
        "sig_name": cfg.get("sig_name", ""),
        "sig_position": cfg.get("sig_position", ""),
        "sig_email": cfg.get("sig_email", ""),
        "sig_it_call": cfg.get("sig_it_call", ""),
    }


def build_signature_html(cfg: dict | None = None) -> str:
    """Renders the little name-card signature (bold name / blue role /
    "Email:" + bold link / boxed "IT Call" number) the user asked to match
    from their screenshot. Returns "" if no name is configured, so callers
    can treat an empty string as "no signature to add"."""
    cfg = cfg or signature_config()
    name = (cfg.get("sig_name") or "").strip()
    if not name:
        return ""
    position = (cfg.get("sig_position") or "").strip()
    email = (cfg.get("sig_email") or "").strip()
    it_call = (cfg.get("sig_it_call") or "").strip()

    rows = [f'<div style="font-weight:700;font-size:14px;color:#1c2b3a;">{html.escape(name)}</div>']
    if position:
        rows.append(
            f'<div style="font-weight:600;font-size:12px;color:#3a6f96;letter-spacing:0.03em;margin:2px 0 8px;">{html.escape(position)}</div>'
        )
    if email:
        rows.append(
            '<div style="font-size:12px;color:#5a6b7d;margin-bottom:4px;">Email: '
            f'<a href="mailto:{html.escape(email)}" style="color:#1a56db;font-weight:700;text-decoration:none;">{html.escape(email)}</a></div>'
        )
    if it_call:
        rows.append(
            '<div style="font-size:12px;color:#5a6b7d;">IT Call '
            f'<span style="display:inline-block;border:1px solid #c9d3e6;border-radius:4px;padding:1px 8px;font-weight:700;color:#1c2b3a;margin-left:4px;">{html.escape(it_call)}</span></div>'
        )

    return (
        "<table cellpadding=\"0\" cellspacing=\"0\" style=\"border-collapse:collapse;font-family:'Leelawadee UI','Segoe UI',Tahoma,Arial,sans-serif;margin-top:12px;\">"
        '<tr><td style="border-left:3px solid #3a6f96;padding:4px 0 4px 12px;">' + "".join(rows) + "</td></tr></table>"
    )

PO_NUMBER_RE = re.compile(r"(PR&QC\d+)", re.IGNORECASE)
QUOTE_NUMBER_RE = re.compile(r"(Q\d{6,})", re.IGNORECASE)

PR_PO_ARCHIVE_ROOT = r"\\vsth-fsrv\IT\fix\PR&PO"
MONTH_ABBR = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def archive_pr_po_file(file_path: str, po_no: str) -> dict:
    """After step 2 (อนุมัติ+จัดส่ง) opens a draft, COPY the PDF into the
    shared PR&PO archive, organized by Buddhist year / month abbreviation,
    renamed to just the PO number. Never raises — callers treat archiving as
    best-effort so a network hiccup doesn't undo an already-sent email.

    Was originally a MOVE, but that broke the still-open Thunderbird draft:
    this runs ~2s after the draft opens (see open_step2), not after the user
    actually clicks Send, so moving the file out from under the draft made
    the attachment un-previewable ("File not found") if the user checked it
    before sending — confirmed live when a real file had already been
    relocated to the archive while its compose window was still open.
    Copying leaves the original in the working folder for as long as the
    user needs it; nothing auto-cleans that folder anymore."""
    if not po_no:
        return {"ok": False, "message": "ไม่ได้คัดลอกไฟล์เข้า PR&PO เพราะไม่พบเลข PR&QC สำหรับตั้งชื่อไฟล์"}
    if not file_path or not os.path.isfile(file_path):
        return {"ok": False, "message": "ไม่ได้คัดลอกไฟล์เข้า PR&PO เพราะไม่พบไฟล์ต้นทาง"}

    today = datetime.date.today()
    buddhist_year = str(today.year + 543)
    month_folder = MONTH_ABBR[today.month]
    dest_dir = os.path.join(PR_PO_ARCHIVE_ROOT, buddhist_year, month_folder)
    ext = os.path.splitext(file_path)[1] or ".pdf"
    dest_path = os.path.join(dest_dir, f"{po_no}{ext}")

    try:
        os.makedirs(dest_dir, exist_ok=True)
        shutil.copy2(file_path, dest_path)
        return {"ok": True, "message": f"คัดลอกไฟล์เข้า PR&PO แล้ว: {buddhist_year}\\{month_folder}\\{po_no}{ext}"}
    except Exception as exc:
        return {"ok": False, "message": f"ส่งอีเมลสำเร็จ แต่คัดลอกไฟล์เข้า PR&PO ไม่สำเร็จ: {exc}"}

# ---------------------------------------------------------------------------
# FG Stock Uploader status tab: this is a SEPARATE standalone tool (its own
# folder, its own venv-independent pymysql dependency, its own Scheduled
# Task) that OverAll Uploader does not run or own — it just reads that tool's
# log/marker files and can trigger a manual run via its own launcher .bat.
# See "C:\Users\IT-5\Desktop\Auto FG Stock Importer\auto_fg_stock.py".
# ---------------------------------------------------------------------------
FG_STOCK_DIR = r"C:\Users\IT-5\Desktop\Auto FG Stock Importer"
FG_STOCK_LOG_FILE = os.path.join(FG_STOCK_DIR, "run_log.txt")
FG_STOCK_LAST_SUCCESS_FILE = os.path.join(FG_STOCK_DIR, "last_success.txt")
FG_STOCK_LAUNCHER = os.path.join(FG_STOCK_DIR, "run_export.bat")
FG_STOCK_CONFIG_FILE = os.path.join(FG_STOCK_DIR, "config.json")
FG_STOCK_TASK_NAME = "Auto FG Stock Importer"
FG_STOCK_STARTUP_SHORTCUT = os.path.join(
    os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs", "Startup",
    "Auto FG Stock Importer.lnk",
)
# Must stay identical to MONTH_FOLDER in auto_fg_stock.py — duplicated here
# rather than imported since the two tools are deliberately independent
# (see the block comment above).
FG_STOCK_MONTH_FOLDER = [
    "", "01-Jan", "02-Feb", "03-Mar", "04-April", "05-May", "06-Jun",
    "07-Jul", "08-Aug", "09-Sep", "10-Oct", "11-Nov", "12-Dec",
]


def fg_stock_today_folder() -> str | None:
    if not os.path.isfile(FG_STOCK_CONFIG_FILE):
        return None
    try:
        with open(FG_STOCK_CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        dest_root = cfg["dest_root"]
    except Exception:
        return None
    today = datetime.date.today()
    return os.path.join(dest_root, str(today.year), FG_STOCK_MONTH_FOLDER[today.month])


def fg_stock_task_info() -> dict:
    try:
        result = subprocess.run(
            ["schtasks", "/query", "/tn", FG_STOCK_TASK_NAME, "/fo", "LIST", "/v"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return {"registered": False}
        info = {}
        for line in result.stdout.splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                info[key.strip()] = value.strip()
        return {
            "registered": True,
            "next_run": info.get("Next Run Time", "-"),
            "last_run": info.get("Last Run Time", "-"),
            "last_result": info.get("Last Result", "-"),
        }
    except Exception:
        return {"registered": False}


SIGNATURE = (
    "ขอแสดงความนับถือ\n"
    "ภูริณัฐ เล็กอุทัย (Mr. Purinat Lexuthai)\n"
    "Information Technology Staff\n\n"
    "บริษัท เวล สเวด (ประเทศไทย) จำกัด\n"
    "Vel-Suede (Thailand) Co., Ltd.\n"
    "149/165-167, 149/181-182 หมู่ 13 เพชรเกษม 95\n"
    "ต.อ้อมน้อย อ.กระทุ่มแบน จ.สมุทรสาคร 74130\n"
    "โทร: 02-024-8830-4 (#123)\n"
    "แฟกซ์: 02-024-8835\n"
    "เว็บไซต์: www.vel-suede.co.jp"
)

THAI_WEEKDAYS = ["วันจันทร์", "วันอังคาร", "วันพุธ", "วันพฤหัสบดี", "วันศุกร์", "วันเสาร์", "วันอาทิตย์"]
THAI_MONTHS = [
    "", "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
]


def thai_date(d: datetime.date) -> str:
    weekday = THAI_WEEKDAYS[d.weekday()]
    return f"{weekday} ที่ {d.day} {THAI_MONTHS[d.month]} {d.year + 543}"


def next_business_day(d: datetime.date) -> datetime.date:
    n = d + datetime.timedelta(days=1)
    while n.weekday() >= 5:  # Sat=5, Sun=6
        n += datetime.timedelta(days=1)
    return n


def default_standby_subject() -> str:
    return f"แจ้งเรื่องการ Standby เจ้าหน้าที่ IT {thai_date(datetime.date.today())}"


def standby_cutoff_time(now: datetime.datetime | None = None) -> datetime.datetime:
    """The Standby cutoff is always a half-hour mark (17:00, 17:30, 18:00, ...),
    rounded up to the next half-hour from the current time — but never earlier
    than 17:00, since standby coverage starts at end of the normal workday.
    e.g. sent at 17:05 -> 17:30 cutoff; sent at 17:30 exactly -> stays 17:30;
    sent at 18:31 -> 19:00 cutoff; sent at 15:00 -> stays at the 17:00 floor."""
    now = now or datetime.datetime.now()
    floor = now.replace(hour=17, minute=0, second=0, microsecond=0)
    if now <= floor:
        return floor
    steps_of_30min = -(-int((now - floor).total_seconds() // 60) // 30)  # ceil division
    return floor + datetime.timedelta(minutes=30 * steps_of_30min)


def default_general_body() -> str:
    today = datetime.date.today()
    tomorrow = next_business_day(today)
    cutoff = standby_cutoff_time()
    cutoff_display = cutoff.strftime("%H:%M")
    return (
        "เรียน ทุกหน่วยงานที่เกี่ยวข้อง\n\n"
        f"เนื่องจากเจ้าหน้าที่ IT มีภารกิจส่วนตัว จึงไม่สามารถอยู่ Standby หลังช่วงเวลา {cutoff_display} น. "
        f"ของวันนี้ ({thai_date(today)}) ได้ ดังนั้น สำหรับพื้นที่การทำงานที่มีการเปิด OT จนถึงเวลา 21:00 น. "
        "หากพบปัญหาในการใช้งานอุปกรณ์คอมพิวเตอร์, Server หรือ Printer ท่านสามารถเขียนโน้ตแจ้งเรื่องไว้ที่โต๊ะแผนก IT ได้ทันทีครับ "
        f"เจ้าหน้าที่จะรีบเข้าดำเนินการแก้ไขให้ใน ({thai_date(tomorrow)})\n\n"
        "กรณีพบปัญหาเร่งด่วนที่มีผลกระทบต่อการทำงาน จนไม่สามารถปฏิบัติงานต่อได้ สามารถติดต่อเจ้าหน้าที่ได้ที่เบอร์โทรศัพท์ด้านล่างนี้ครับ:\n\n"
        "- IT Arm: 092-420-5014\n"
        "- IT Bee: 062-264-7041\n"
        "- IT Tung: 085-371-6799\n\n"
        "จึงเรียนมาเพื่อโปรดทราบและขออภัยในความไม่สะดวกครับ"
    )


def step1_body(quote_no: str) -> str:
    quote_display = quote_no.strip() or "___________"
    return (
        "เรียน ทีมงาน Advice Corporate\n\n"
        f"ผมขอความกรุณาจัดทำใบเสนอราคา หมายเลข [{quote_display}] ตามรายการที่แนบมาพร้อมอีเมลฉบับนี้\n\n"
        "รหัสลูกค้า: 80061748\n"
        "ชื่อบริษัท: เวล สเวด (ประเทศไทย) จำกัด\n\n"
        "หากต้องการข้อมูลเพิ่มเติม หรือต้องการสอบถามรายละเอียดใด ๆ เพิ่มเติม ทาง Advice สามารถติดต่อผมได้ตามข้อมูลด้านล่าง\n\n"
        "ขอขอบพระคุณล่วงหน้าสำหรับความกรุณาและการสนับสนุนครับ\n\n"
        "--\n" + SIGNATURE
    )


def step2_body(po_no: str) -> str:
    po_display = po_no.strip() or "___________"
    return (
        "เรียนแอดมินฝ่ายขาย Advice Corporate\n\n"
        f"ใบเสนอราคา [{po_display}] ได้รับการอนุมัติเรียบร้อยแล้วครับ\n"
        "เอกสารอนุมัติแนบมาพร้อมอีเมลฉบับนี้\n\n"
        "ขอความกรุณาจัดส่งสินค้าตามที่อยู่ด้านล่าง:\n\n"
        "บริษัท เวล สเวด (ประเทศไทย) จำกัด\n"
        "149/165-167, 149/181-182 หมู่ที่ 13 ซอยเพชรเกษม 95\n"
        "ถนนเพชรเกษม ตำบลอ้อมน้อย\n"
        "อำเภอกระทุ่มแบน จังหวัดสมุทรสาคร 74130\n\n"
        "เบอร์ติดต่อ:\n\n"
        "   02-024-8830-4 (ต่อ 123)\n\n"
        "   085-371-6799 คุณ ภูริณัฐ\n\n"
        "   092-420-5014 คุณ กฤษฎา\n\n"
        "   062-264-7041 คุณ อาสาฟ\n\n\n"
        "เวลารับสินค้า: วันจันทร์ - วันเสาร์ เวลา 08:00 - 17:00 น.\n\n"
        "ขอขอบพระคุณสำหรับการบริการครับ\n"
        "ขอแสดงความนับถือ"
    )


def latest_pdf(folder: str) -> str | None:
    try:
        candidates = [
            os.path.join(folder, name)
            for name in os.listdir(folder)
            if name.lower().endswith(".pdf")
        ]
    except FileNotFoundError:
        return None
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


def extract_pdf_text(path: str, max_pages: int = 2) -> str:
    """Best-effort text extraction from the first few pages of a PDF.
    Returns "" (not an exception) if PyMuPDF is missing or the file can't be read,
    so callers can always fall back to filename-only matching."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return ""
    try:
        parts = []
        with fitz.open(path) as doc:
            for i, page in enumerate(doc):
                if i >= max_pages:
                    break
                parts.append(page.get_text())
        return "\n".join(parts)
    except Exception:
        return ""


def find_number_in_file(path: str, pattern: "re.Pattern") -> str:
    """Search the filename first (cheap), then fall back to the PDF's own text
    content — the number IT staff care about often isn't in the filename at all,
    e.g. a generic "EXT HDD 3.5.pdf" that has the quote number printed inside it."""
    match = pattern.search(os.path.basename(path))
    if match:
        return match.group(1)
    match = pattern.search(extract_pdf_text(path))
    return match.group(1) if match else ""


def escape_field(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


_data_lock = threading.Lock()


def load_json_list(path: str) -> list:
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_json_list(path: str, data: list) -> None:
    if os.path.isfile(path):
        try:
            shutil.copyfile(path, path + ".bak")
        except Exception:
            pass
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_categories() -> list:
    return load_json_list(CATEGORIES_FILE)


def save_categories(categories: list) -> None:
    save_json_list(CATEGORIES_FILE, categories)


def split_addresses(value: str) -> list:
    if not value:
        return []
    return [p.strip() for p in re.split(r"[;,]", value) if p.strip()]


def validate_recipients(to_addr: str, cc_addr: str) -> str | None:
    bad = [a for a in split_addresses(to_addr) + split_addresses(cc_addr) if not EMAIL_RE.match(a)]
    if bad:
        return f"อีเมลไม่ถูกต้อง กรุณาตรวจสอบ: {', '.join(bad)}"
    return None


def append_send_log(entry: dict) -> dict:
    entry = dict(entry)
    entry["id"] = uuid.uuid4().hex[:10]
    entry["timestamp"] = datetime.datetime.now().isoformat(timespec="seconds")
    with _data_lock:
        logs = load_json_list(SEND_LOG_FILE)
        logs.insert(0, entry)
        logs = logs[:500]
        save_json_list(SEND_LOG_FILE, logs)
    return entry


def add_scheduled_send(entry: dict) -> dict:
    entry = dict(entry)
    entry["id"] = uuid.uuid4().hex[:10]
    entry["created_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    entry["status"] = "pending"
    with _data_lock:
        items = load_json_list(SCHEDULED_FILE)
        items.append(entry)
        save_json_list(SCHEDULED_FILE, items)
    return entry


def python_executable_for_shortcut() -> str:
    exe = sys.executable
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return pythonw if os.path.isfile(pythonw) else exe


def is_outlook_installed() -> bool:
    try:
        import winreg

        winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Outlook.Application\CLSID")
        return True
    except OSError:
        return False


def startup_shortcut_path() -> str:
    startup_dir = os.path.join(
        os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
    )
    return os.path.join(startup_dir, "OverAll Uploader.lnk")


BACKGROUND_TASK_NAME = "OverAll Uploader - ตรวจคิวส่งอัตโนมัติ"


def background_check_command() -> list:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--background-check"]
    pythonw = python_executable_for_shortcut()
    return [pythonw, os.path.join(APP_DIR, "mail_app.py"), "--background-check"]


def is_background_task_registered() -> bool:
    try:
        result = subprocess.run(
            ["schtasks", "/query", "/tn", BACKGROUND_TASK_NAME],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def run_background_check() -> None:
    """Headless entry point (no GUI window): wakes Outlook up if a scheduled
    send is due soon, so Outlook's own Outbox can flush it on time even if
    nobody has the app open. Intended to run from a Windows Scheduled Task."""
    items = load_json_list(SCHEDULED_FILE)
    now = datetime.datetime.now()
    needs_outlook = False
    for item in items:
        if item.get("status") not in ("pending", "due"):
            continue
        try:
            send_dt = datetime.datetime.fromisoformat(item["send_time"])
        except Exception:
            continue
        if send_dt <= now + datetime.timedelta(minutes=20):
            needs_outlook = True
            break
    if needs_outlook and is_outlook_installed():
        try:
            import win32com.client

            win32com.client.Dispatch("Outlook.Application")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Thunderbird "reply bridge": lets open_step2() open a REAL threaded reply to
# the original Advice quotation email instead of a brand-new compose window.
# Thunderbird's -compose CLI has no concept of replying to an existing
# message, so this uses a small Thunderbird extension (thunderbird_extension/)
# that talks to a native-messaging host (this process, run with
# --reply-bridge-host) over a simple JSON job-file queue:
#   1. open_step2() writes reply_jobs/<id>.json describing the job
#   2. the native host (a long-lived process Thunderbird itself launches when
#      the extension's background.js calls connectNative()) notices the file,
#      forwards it to the extension over native messaging, and waits
#   3. the extension searches Thunderbird's mail for the original message,
#      calls the real Compose API's beginReply(), sets body/cc, attaches the
#      file (sent as base64 to avoid needing file:// permissions), and
#      reports back
#   4. the host writes reply_jobs/<id>.result.json; open_step2() polls for it
#      with a timeout and falls back to the old -compose flow if it never
#      shows up (extension not installed, Thunderbird not running, etc.)
# ---------------------------------------------------------------------------

REPLY_BRIDGE_HOST_NAME = "com.velsuede.mail_uploader_reply_bridge"
REPLY_BRIDGE_EXTENSION_ID = "reply-bridge@vel-suede.local"
REPLY_JOBS_DIR = os.path.join(APP_DIR, "reply_jobs")


def reply_bridge_host_manifest_path() -> str:
    return os.path.join(APP_DIR, "reply_bridge_host_manifest.json")


def reply_bridge_launcher_path() -> str:
    return os.path.join(APP_DIR, "run_reply_bridge_host.bat")


def is_reply_bridge_registered() -> bool:
    try:
        import winreg

        winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            rf"SOFTWARE\Mozilla\Thunderbird\NativeMessagingHosts\{REPLY_BRIDGE_HOST_NAME}",
        )
        return True
    except OSError:
        return False


def register_reply_bridge() -> dict:
    """One-time setup: writes the native-messaging host manifest + launcher
    batch file, and registers the host under HKCU so Thunderbird can find it.
    Does NOT touch Thunderbird's extension-signature enforcement — that pref
    (xpinstall.signatures.required) is a browser security setting the user
    has to flip themselves in about:config; we never modify it for them."""
    try:
        pythonw = python_executable_for_shortcut()
        script = os.path.join(APP_DIR, "mail_app.py")
        launcher = reply_bridge_launcher_path()
        with open(launcher, "w", encoding="utf-8") as f:
            f.write("@echo off\r\n")
            if getattr(sys, "frozen", False):
                f.write(f'"{sys.executable}" --reply-bridge-host\r\n')
            else:
                f.write(f'"{pythonw}" "{script}" --reply-bridge-host\r\n')

        manifest = {
            "name": REPLY_BRIDGE_HOST_NAME,
            "description": "OverAll Uploader reply bridge",
            "path": launcher,
            "type": "stdio",
            "allowed_extensions": [REPLY_BRIDGE_EXTENSION_ID],
        }
        manifest_path = reply_bridge_host_manifest_path()
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        import winreg

        key = winreg.CreateKey(
            winreg.HKEY_CURRENT_USER,
            rf"SOFTWARE\Mozilla\Thunderbird\NativeMessagingHosts\{REPLY_BRIDGE_HOST_NAME}",
        )
        winreg.SetValue(key, "", winreg.REG_SZ, manifest_path)
        winreg.CloseKey(key)
        os.makedirs(REPLY_JOBS_DIR, exist_ok=True)
        return {"ok": True, "message": "ลงทะเบียน reply bridge แล้ว — ยังต้องติดตั้งส่วนขยายใน Thunderbird เองอีกขั้นตอนหนึ่ง (ดู SKILL.md)"}
    except Exception as exc:
        return {"ok": False, "message": f"ลงทะเบียนไม่สำเร็จ: {exc}"}


def unregister_reply_bridge() -> dict:
    try:
        import winreg

        try:
            winreg.DeleteKey(
                winreg.HKEY_CURRENT_USER,
                rf"SOFTWARE\Mozilla\Thunderbird\NativeMessagingHosts\{REPLY_BRIDGE_HOST_NAME}",
            )
        except FileNotFoundError:
            pass
        return {"ok": True, "message": "ปิดใช้งาน reply bridge แล้ว"}
    except Exception as exc:
        return {"ok": False, "message": f"ปิดใช้งานไม่สำเร็จ: {exc}"}


def _reply_bridge_send(message: dict) -> None:
    encoded = json.dumps(message).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(encoded)))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def _reply_bridge_read() -> dict | None:
    raw_length = sys.stdin.buffer.read(4)
    if not raw_length or len(raw_length) < 4:
        return None
    length = struct.unpack("<I", raw_length)[0]
    data = sys.stdin.buffer.read(length)
    return json.loads(data)


def run_reply_bridge_host() -> None:
    """The native-messaging host process itself. Thunderbird launches this
    (via run_reply_bridge_host.bat) the moment the extension's background.js
    calls connectNative(), and keeps it alive as long as that port stays
    open. Runs until Thunderbird closes the pipe (stdin read returns empty)."""
    os.makedirs(REPLY_JOBS_DIR, exist_ok=True)

    def watch_jobs():
        seen = set()
        while True:
            try:
                for name in os.listdir(REPLY_JOBS_DIR):
                    if not name.endswith(".json") or name.endswith(".result.json") or name in seen:
                        continue
                    path = os.path.join(REPLY_JOBS_DIR, name)
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            job = json.load(f)
                        _reply_bridge_send(job)
                        seen.add(name)
                        os.remove(path)
                    except Exception:
                        pass
            except FileNotFoundError:
                pass
            time.sleep(1)

    threading.Thread(target=watch_jobs, daemon=True).start()

    while True:
        msg = _reply_bridge_read()
        if msg is None:
            os._exit(0)
        job_id = msg.get("jobId")
        if not job_id:
            continue
        result_path = os.path.join(REPLY_JOBS_DIR, f"{job_id}.result.json")
        try:
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(msg, f, ensure_ascii=False)
        except Exception:
            pass


def try_bridge_action(
    search_text: str,
    cc_addr: str,
    body: str,
    attachment_paths: list | None = None,
    timeout_seconds: float = 15,
    action: str = "reply",
) -> dict | None:
    """Submit a reply/forward job and wait for the extension to handle it.
    Returns None (never raises) if the bridge isn't registered, Thunderbird
    isn't running the extension, or nothing answers in time — callers must
    treat None as "fall back to the normal compose flow". `action` is
    "reply" or "forward" (see background.js's processJob)."""
    if not is_reply_bridge_registered():
        return None
    try:
        os.makedirs(REPLY_JOBS_DIR, exist_ok=True)
        job_id = uuid.uuid4().hex[:12]
        job = {
            "jobId": job_id,
            "action": action,
            "searchText": search_text,
            "cc": cc_addr or "",
            "body": body,
        }
        attachments = []
        for path in attachment_paths or []:
            if path and os.path.isfile(path):
                with open(path, "rb") as f:
                    attachments.append(
                        {"name": os.path.basename(path), "base64": base64.b64encode(f.read()).decode("ascii")}
                    )
        if attachments:
            job["attachments"] = attachments

        job_path = os.path.join(REPLY_JOBS_DIR, f"{job_id}.json")
        with open(job_path, "w", encoding="utf-8") as f:
            json.dump(job, f, ensure_ascii=False)

        result_path = os.path.join(REPLY_JOBS_DIR, f"{job_id}.result.json")
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if os.path.isfile(result_path):
                try:
                    with open(result_path, "r", encoding="utf-8") as f:
                        result = json.load(f)
                finally:
                    try:
                        os.remove(result_path)
                    except Exception:
                        pass
                return result
            time.sleep(0.4)
        try:
            if os.path.isfile(job_path):
                os.remove(job_path)
        except Exception:
            pass
        return None
    except Exception:
        return None


def apply_body_keeping_signature(mail, body: str) -> None:
    """Set a new Outlook MailItem's body, adding a signature. Two sources,
    tried in order:
    1. This app's own configured signature (Settings → ลายเซ็นดิจิทัล) — the
       user explicitly wants THIS exact styled card, not just "whatever's in
       Outlook". Editable per-machine, never hardcoded to one person, since
       this app runs under whoever's Windows session is active.
    2. If no signature is configured here, fall back to preserving whatever
       Outlook itself would have auto-inserted for a new message (Outlook
       only populates that into HTMLBody once an Inspector exists for the
       item, so GetInspector is accessed to force that before reading it).
    """
    own_signature_html = build_signature_html()
    if own_signature_html:
        body_html = html.escape(body).replace("\n", "<br>\n")
        mail.HTMLBody = (
            "<html><body style=\"font-family:'Leelawadee UI','Segoe UI',Tahoma,Arial,sans-serif;font-size:13px;\">"
            + body_html + "<br><br>" + own_signature_html + "</body></html>"
        )
        return

    try:
        mail.GetInspector  # noqa: B018 — property access has the side effect of creating the Inspector
        existing_html = mail.HTMLBody or ""
        match = re.search(r"<body[^>]*>", existing_html, re.IGNORECASE)
        if match:
            body_html = html.escape(body).replace("\n", "<br>\n")
            insert_at = match.end()
            mail.HTMLBody = existing_html[:insert_at] + body_html + "<br><br>" + existing_html[insert_at:]
            return
    except Exception:
        pass
    # No signature detected (or anything above failed) — behave exactly as before.
    mail.Body = body


class Api:
    def get_defaults(self):
        step1_file = latest_pdf(folder_step1())
        step3_file = latest_pdf(folder_step3())
        return {
            "general_subject": "แจ้งเตือนการดูแลระบบ IT",
            "general_body": default_general_body(),
            "step1_file": os.path.basename(step1_file) if step1_file else "ไม่พบไฟล์ PDF",
            "step3_file": os.path.basename(step3_file) if step3_file else "ไม่พบไฟล์ PDF",
            "outlook_leave_subject": default_standby_subject(),
            "outlook_leave_body": default_general_body(),
        }

    def open_general(self, to_addr, cc_addr, subject, body, image_path=None):
        return self._compose_thunderbird(
            to_addr, cc_addr, subject, body, None, "แจ้งเตือนทั่วไป",
            extra_attachments=[image_path] if image_path else None,
        )

    def open_outlook_leave(self, to_addr, cc_addr, subject, body, deferred_time=None, image_path=None):
        return self._compose_outlook(
            to_addr, cc_addr, subject, body, deferred_time, "Outlook - แจ้งเลิกงาน",
            attachments=[image_path] if image_path else None,
        )

    def get_categories(self):
        return load_categories()

    def add_category(self, name, badge, description, client, to_addr, cc_addr):
        name = (name or "").strip()
        if not name:
            return {"error": "กรุณาตั้งชื่อหมวดหมู่"}
        badge = (badge or name[:2]).strip().upper()[:3]
        category = {
            "id": f"custom-{uuid.uuid4().hex[:8]}",
            "name": name,
            "badge": badge,
            "description": (description or "").strip(),
            "client": client if client in ("thunderbird", "outlook") else "thunderbird",
            "to": (to_addr or "").strip(),
            "cc": (cc_addr or "").strip(),
        }
        with _data_lock:
            categories = load_categories()
            categories.append(category)
            save_categories(categories)
        return {"category": category}

    def update_category(self, category_id, name, badge, description, client, to_addr, cc_addr):
        name = (name or "").strip()
        if not name:
            return {"error": "กรุณาตั้งชื่อหมวดหมู่"}
        with _data_lock:
            categories = load_categories()
            category = next((c for c in categories if c["id"] == category_id), None)
            if not category:
                return {"error": "ไม่พบหมวดหมู่นี้"}
            category["name"] = name
            category["badge"] = (badge or name[:2]).strip().upper()[:3]
            category["description"] = (description or "").strip()
            category["client"] = client if client in ("thunderbird", "outlook") else category["client"]
            category["to"] = (to_addr or "").strip()
            category["cc"] = (cc_addr or "").strip()
            save_categories(categories)
        return {"category": category}

    def delete_category(self, category_id):
        with _data_lock:
            categories = load_categories()
            categories = [c for c in categories if c["id"] != category_id]
            save_categories(categories)
        return {"ok": True}

    def open_custom(self, category_id, subject, body, to_addr=None, cc_addr=None, image_path=None):
        categories = load_categories()
        category = next((c for c in categories if c["id"] == category_id), None)
        if not category:
            return {"ok": False, "message": "ไม่พบหมวดหมู่นี้"}
        final_to = to_addr if to_addr else category["to"]
        final_cc = cc_addr if cc_addr else category["cc"]
        label = f"หมวดหมู่ - {category['name']}"
        if category["client"] == "outlook":
            return self._compose_outlook(
                final_to, final_cc, subject, body, None, label,
                attachments=[image_path] if image_path else None,
            )
        return self._compose_thunderbird(
            final_to, final_cc, subject, body, None, label,
            extra_attachments=[image_path] if image_path else None,
        )

    def pick_file(self):
        window = webview.windows[0]
        root = advice_root()
        result = window.create_file_dialog(
            FileDialog.OPEN,
            directory=root,
            allow_multiple=False,
            file_types=("PDF Files (*.pdf)", "All files (*.*)"),
        )
        if not result:
            return None
        chosen = result[0]
        # เลือกได้เฉพาะไฟล์ในโซนใบเสนอราคานี้เท่านั้น
        root_abs = os.path.abspath(root)
        if os.path.commonpath([root_abs, os.path.abspath(chosen)]) != root_abs:
            return {"error": "กรุณาเลือกไฟล์ภายในโฟลเดอร์ใบเสนอราคานี้เท่านั้น"}
        return {"path": chosen, "file_name": os.path.basename(chosen)}

    def pick_image_file(self):
        window = webview.windows[0]
        result = window.create_file_dialog(
            FileDialog.OPEN,
            allow_multiple=False,
            file_types=("Image Files (*.png;*.jpg;*.jpeg;*.gif;*.bmp;*.webp)", "All files (*.*)"),
        )
        if not result:
            return None
        chosen = result[0]
        return {"path": chosen, "file_name": os.path.basename(chosen)}

    def open_step1(self, quote_no, override_path=None, image_path=None):
        file_path = override_path or latest_pdf(folder_step1())
        if not file_path:
            return {"ok": False, "message": "ไม่พบไฟล์ PDF ในโฟลเดอร์ขั้น 1"}

        if not quote_no:
            quote_no = find_number_in_file(file_path, QUOTE_NUMBER_RE)

        result = self._compose_thunderbird(
            advice_to(), advice_cc(), "ขอจัดทำใบเสนอราคา", step1_body(quote_no), file_path, "Advice - ขอใบเสนอราคา",
            extra_attachments=[image_path] if image_path else None,
        )
        result["quote_no"] = quote_no
        result["file_name"] = os.path.basename(file_path)
        return result

    def open_step2(self, po_no, override_path=None, image_path=None):
        file_path = override_path or latest_pdf(folder_step3())
        if not file_path:
            return {"ok": False, "message": "ไม่พบไฟล์ PDF ในโฟลเดอร์ขั้น 3"}

        if not po_no:
            po_no = find_number_in_file(file_path, PO_NUMBER_RE)

        validation_error = validate_recipients("", advice_cc())
        if validation_error:
            return {"ok": False, "message": validation_error}

        subject = f"Re: ใบเสนอราคา [{po_no}] อนุมัติแล้ว - ขอความกรุณาจัดส่งสินค้า"
        body = step2_body(po_no)
        attachment_paths = [file_path] + ([image_path] if image_path else [])

        # Try a REAL threaded reply first (Thunderbird extension + native
        # messaging bridge — see thunderbird_extension/ and SKILL.md). The
        # original quotation email's body has the bare "QC..." number, not
        # our "PR&QC..." form, so strip the prefix before searching for it.
        bridge_result = None
        if po_no:
            search_text = po_no.replace("PR&", "").strip()
            if search_text:
                bridge_result = try_bridge_action(search_text, advice_cc(), body, attachment_paths)

        if bridge_result and bridge_result.get("ok"):
            result = {
                "ok": True,
                "message": f"เปิด Reply จริงบนอีเมลเดิมแล้ว (หัวข้อเดิม: {bridge_result.get('originalSubject', '-')}) กรุณาตรวจสอบก่อนกดส่ง",
            }
            append_send_log(
                {
                    "client": "thunderbird",
                    "category": "Advice - อนุมัติ+จัดส่ง (reply)",
                    "to": "",
                    "cc": advice_cc(),
                    "subject": subject,
                    "body": body,
                    "attachment": os.path.basename(file_path),
                    "status": "opened (reply)",
                }
            )
        else:
            result = self._compose_thunderbird(
                advice_to(), advice_cc(), subject, body, file_path, "Advice - อนุมัติ+จัดส่ง",
                extra_attachments=[image_path] if image_path else None,
            )
            if is_reply_bridge_registered():
                # bridge is set up but didn't find/answer in time — say so instead of pretending nothing was tried
                note = bridge_result.get("error") if bridge_result else "ไม่ตอบสนองภายในเวลาที่กำหนด"
                result["message"] = result.get("message", "") + f" (หมายเหตุ: ลอง reply จริงก่อนแล้วแต่ไม่สำเร็จ — {note} จึงเปิดฉบับร่างใหม่แทน)"

        result["po_no"] = po_no
        result["file_name"] = os.path.basename(file_path)

        if result.get("ok"):
            # Copying (not moving — see archive_pr_po_file's docstring), so
            # there's no race with Thunderbird still reading the original
            # for the attachment; no artificial delay needed here anymore.
            archive_result = archive_pr_po_file(file_path, po_no)
            result["archive_ok"] = archive_result["ok"]
            result["message"] = result["message"] + " " + archive_result["message"]

        return result

    def _compose_thunderbird(self, to_addr, cc_addr, subject, body, attachment, category_label="แจ้งเตือนทั่วไป", extra_attachments=None):
        validation_error = validate_recipients(to_addr, cc_addr)
        if validation_error:
            return {"ok": False, "message": validation_error}
        try:
            thunderbird = find_thunderbird()

            all_attachments = ([attachment] if attachment else []) + list(extra_attachments or [])

            fields = []
            if to_addr:
                fields.append(f"to='{escape_field(to_addr)}'")
            if cc_addr:
                fields.append(f"cc='{escape_field(cc_addr)}'")
            fields.append(f"subject='{escape_field(subject)}'")
            # Always plain text for Thunderbird's -compose. An HTML body
            # (tried to inject the digital-signature card here) reliably
            # broke in real testing: Thunderbird's compose editor either
            # dropped the content entirely or re-wrapped every line in its
            # own default-margin <p>, giving huge gaps between every single
            # line no matter how the HTML was structured. Plain text has
            # neither problem and renders \n / \n\n exactly as written.
            fields.append(f"body='{escape_field(body)}'")
            if all_attachments:
                # Thunderbird's -compose accepts a comma-separated list of file:// URIs
                # in a single attachment='...' value.
                uris = [
                    "file:///" + os.path.abspath(path).replace("\\", "/")
                    for path in all_attachments
                ]
                fields.append(f"attachment='{escape_field(','.join(uris))}'")
            compose_arg = ",".join(fields)

            subprocess.Popen([thunderbird, "-compose", compose_arg])
            append_send_log(
                {
                    "client": "thunderbird",
                    "category": category_label,
                    "to": to_addr or "",
                    "cc": cc_addr or "",
                    "subject": subject or "",
                    "body": body or "",
                    "attachment": ", ".join(os.path.basename(p) for p in all_attachments),
                    "status": "opened",
                }
            )
            return {"ok": True, "message": "เปิดฉบับร่างใน Thunderbird แล้ว กรุณาตรวจสอบก่อนกดส่ง"}
        except Exception as exc:
            return {"ok": False, "message": f"เกิดข้อผิดพลาด: {exc} — ตรวจสอบว่าติดตั้ง Thunderbird ไว้ที่เครื่องนี้แล้ว"}

    def _compose_outlook(self, to_addr, cc_addr, subject, body, deferred_time=None, category_label="Outlook", attachments=None):
        validation_error = validate_recipients(to_addr, cc_addr)
        if validation_error:
            return {"ok": False, "message": validation_error}
        try:
            import win32com.client

            outlook = win32com.client.Dispatch("Outlook.Application")
            mail = outlook.CreateItem(0)  # olMailItem
            if to_addr:
                mail.To = to_addr
            if cc_addr:
                mail.CC = cc_addr
            mail.Subject = subject
            apply_body_keeping_signature(mail, body)
            for path in attachments or []:
                if path and os.path.isfile(path):
                    mail.Attachments.Add(os.path.abspath(path))

            if deferred_time:
                try:
                    send_dt = datetime.datetime.fromisoformat(deferred_time)
                except ValueError:
                    return {"ok": False, "message": "รูปแบบเวลาไม่ถูกต้อง"}
                if send_dt <= datetime.datetime.now():
                    return {"ok": False, "message": "กรุณาเลือกเวลาส่งที่เป็นอนาคต"}
                mail.DeferredDeliveryTime = send_dt
                mail.Send()
                formatted = send_dt.strftime("%d/%m/%Y %H:%M")
                append_send_log(
                    {
                        "client": "outlook",
                        "category": category_label,
                        "to": to_addr or "",
                        "cc": cc_addr or "",
                        "subject": subject or "",
                        "body": body or "",
                        "attachment": ", ".join(os.path.basename(p) for p in (attachments or []) if p),
                        "status": f"ตั้งเวลาส่ง {formatted} น.",
                    }
                )
                add_scheduled_send(
                    {
                        "to": to_addr or "",
                        "cc": cc_addr or "",
                        "subject": subject or "",
                        "category": category_label,
                        "send_time": send_dt.isoformat(timespec="minutes"),
                    }
                )
                return {
                    "ok": True,
                    "message": (
                        f"ตั้งเวลาส่งอัตโนมัติแล้วที่ {formatted} น. — อีเมลอยู่ใน Outbox ของ Outlook "
                        "ยังเปิดแก้ไขหรือยกเลิกได้ก่อนถึงเวลา (ต้องเปิด Outlook ค้างไว้จนถึงเวลาส่ง)"
                    ),
                }

            mail.Display()
            append_send_log(
                {
                    "client": "outlook",
                    "category": category_label,
                    "to": to_addr or "",
                    "cc": cc_addr or "",
                    "subject": subject or "",
                    "body": body or "",
                    "attachment": ", ".join(os.path.basename(p) for p in (attachments or []) if p),
                    "status": "opened",
                }
            )
            return {"ok": True, "message": "เปิดฉบับร่างใน Outlook แล้ว กรุณาตรวจสอบก่อนกดส่ง"}
        except Exception as exc:
            return {"ok": False, "message": f"เกิดข้อผิดพลาด: {exc} — ตรวจสอบว่าเปิดโปรแกรม Outlook ไว้แล้ว"}

    def get_send_log(self, limit=100):
        return load_json_list(SEND_LOG_FILE)[:limit]

    def clear_history(self):
        with _data_lock:
            save_json_list(SEND_LOG_FILE, [])
        return {"ok": True}

    def export_history_csv(self):
        logs = load_json_list(SEND_LOG_FILE)
        if not logs:
            return {"ok": False, "message": "ไม่มีประวัติให้ส่งออก"}
        window = webview.windows[0]
        default_name = f"ประวัติการส่ง-{datetime.date.today().isoformat()}.csv"
        result = window.create_file_dialog(
            FileDialog.SAVE,
            directory=os.path.join(os.path.expanduser("~"), "Desktop"),
            save_filename=default_name,
            file_types=("CSV Files (*.csv)", "All files (*.*)"),
        )
        if not result:
            return {"ok": False, "message": "ยกเลิกการส่งออก"}
        path = result if isinstance(result, str) else result[0]
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["เวลา", "หมวดหมู่", "ช่องทาง", "ถึง", "สำเนา", "หัวข้อ", "สถานะ", "ไฟล์แนบ"])
        for entry in logs:
            writer.writerow(
                [
                    entry.get("timestamp", ""),
                    entry.get("category", ""),
                    entry.get("client", ""),
                    entry.get("to", ""),
                    entry.get("cc", ""),
                    entry.get("subject", ""),
                    entry.get("status", ""),
                    entry.get("attachment", ""),
                ]
            )
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            f.write(buf.getvalue())
        return {"ok": True, "message": f"ส่งออกประวัติแล้วที่ {path}"}

    def resend_log(self, log_id):
        logs = load_json_list(SEND_LOG_FILE)
        entry = next((l for l in logs if l["id"] == log_id), None)
        if not entry:
            return {"ok": False, "message": "ไม่พบประวัตินี้"}
        label = entry.get("category", "ส่งซ้ำจากประวัติ")
        if entry.get("client") == "outlook":
            return self._compose_outlook(entry.get("to", ""), entry.get("cc", ""), entry.get("subject", ""), entry.get("body", ""), None, label)
        return self._compose_thunderbird(entry.get("to", ""), entry.get("cc", ""), entry.get("subject", ""), entry.get("body", ""), None, label)

    def get_scheduled_sends(self):
        with _data_lock:
            items = load_json_list(SCHEDULED_FILE)
            now = datetime.datetime.now()
            changed = False
            for item in items:
                if item.get("status") == "pending":
                    try:
                        send_dt = datetime.datetime.fromisoformat(item["send_time"])
                    except Exception:
                        continue
                    if send_dt <= now:
                        item["status"] = "due"
                        changed = True
            if changed:
                save_json_list(SCHEDULED_FILE, items)
        items.sort(key=lambda x: x.get("send_time", ""))
        return items

    def dismiss_scheduled(self, sched_id):
        with _data_lock:
            items = load_json_list(SCHEDULED_FILE)
            items = [it for it in items if it["id"] != sched_id]
            save_json_list(SCHEDULED_FILE, items)
        return {"ok": True}

    def check_environment(self):
        warnings = []
        try:
            find_thunderbird()
        except FileNotFoundError:
            warnings.append("ไม่พบโปรแกรม Thunderbird ในเครื่องนี้ — หมวดหมู่ที่เปิดร่างด้วย Thunderbird จะใช้งานไม่ได้")
        if not is_outlook_installed():
            warnings.append("ไม่พบโปรแกรม Outlook ในเครื่องนี้ — หมวดหมู่ที่เปิดร่างด้วย Outlook จะใช้งานไม่ได้")
        if not os.path.isdir(advice_root()):
            warnings.append("ไม่พบโฟลเดอร์ใบเสนอราคา Advice ตามที่ตั้งค่าไว้ — ตรวจสอบตำแหน่งโฟลเดอร์ในหน้าตั้งค่า")
        return {"warnings": warnings}

    def get_fg_stock_status(self):
        log_tail = []
        if os.path.isfile(FG_STOCK_LOG_FILE):
            try:
                with open(FG_STOCK_LOG_FILE, "r", encoding="utf-8") as f:
                    log_tail = [line.strip() for line in f.readlines()[-15:]]
                log_tail.reverse()
            except Exception:
                pass

        last_success = ""
        if os.path.isfile(FG_STOCK_LAST_SUCCESS_FILE):
            try:
                with open(FG_STOCK_LAST_SUCCESS_FILE, "r", encoding="utf-8") as f:
                    last_success = f.read().strip()
            except Exception:
                pass

        return {
            "installed": os.path.isfile(FG_STOCK_LAUNCHER),
            "log_tail": log_tail,
            "last_success": last_success,
            "today_ok": last_success == datetime.date.today().isoformat(),
            "startup_shortcut": os.path.isfile(FG_STOCK_STARTUP_SHORTCUT),
            "task": fg_stock_task_info(),
        }

    def run_fg_stock_now(self):
        if not os.path.isfile(FG_STOCK_LAUNCHER):
            return {"ok": False, "message": "ไม่พบโปรแกรม Auto FG Stock Importer ในเครื่องนี้"}
        try:
            subprocess.run(
                ["cmd", "/c", FG_STOCK_LAUNCHER],
                capture_output=True, text=True, timeout=90,
            )
            return {"ok": True, "message": "รันคำสั่งดึงข้อมูล FG Stock เสร็จแล้ว ตรวจผลลัพธ์ด้านล่าง"}
        except subprocess.TimeoutExpired:
            return {"ok": False, "message": "รันนานเกินไป (เกิน 90 วินาที) — เครือข่ายหรือฐานข้อมูลอาจช้าหรือไม่ตอบสนอง"}
        except Exception as exc:
            return {"ok": False, "message": f"รันไม่สำเร็จ: {exc}"}

    def open_fg_stock_folder(self):
        folder = fg_stock_today_folder()
        if not folder:
            return {"ok": False, "message": "ไม่พบการตั้งค่าโฟลเดอร์ปลายทางของ Auto FG Stock Importer"}
        if not os.path.isdir(folder):
            return {"ok": False, "message": f"ยังไม่มีโฟลเดอร์ของเดือนนี้ (ยังไม่เคย export): {folder}"}
        try:
            os.startfile(folder)
            return {"ok": True, "message": "เปิดโฟลเดอร์แล้ว"}
        except Exception as exc:
            return {"ok": False, "message": f"เปิดโฟลเดอร์ไม่สำเร็จ: {exc}"}

    def get_advice_config(self):
        return load_config()

    def save_advice_config(self, to_addr, cc_addr, root_folder):
        root_folder = (root_folder or "").strip()
        if not root_folder:
            return {"error": "กรุณาระบุโฟลเดอร์ใบเสนอราคาหลัก"}
        validation_error = validate_recipients(to_addr, cc_addr)
        if validation_error:
            return {"error": validation_error}
        with _data_lock:
            save_config(
                {
                    "advice_to": (to_addr or "").strip(),
                    "advice_cc": (cc_addr or "").strip(),
                    "advice_root": root_folder,
                }
            )
        return {"ok": True, "config": load_config()}

    def get_signature_config(self):
        return signature_config()

    def save_signature_config(self, name, position, email, it_call):
        with _data_lock:
            save_config(
                {
                    "sig_name": (name or "").strip(),
                    "sig_position": (position or "").strip(),
                    "sig_email": (email or "").strip(),
                    "sig_it_call": (it_call or "").strip(),
                }
            )
        return {"ok": True, "config": signature_config()}

    def preview_signature_html(self):
        return {"html": build_signature_html()}

    def pick_advice_root_folder(self):
        window = webview.windows[0]
        result = window.create_file_dialog(FileDialog.FOLDER, directory=advice_root())
        if not result:
            return None
        return {"path": result[0] if isinstance(result, (list, tuple)) else result}

    def get_app_info(self):
        return {
            "version": APP_VERSION,
            "build_date": APP_BUILD_DATE,
            "author": "ภูริณัฐ เล็กอุทัย (IT Tung)",
            "company": "บริษัท เวล สเวด (ประเทศไทย) จำกัด",
        }

    def get_autostart(self):
        return {"enabled": os.path.isfile(startup_shortcut_path())}

    def set_autostart(self, enabled):
        path = startup_shortcut_path()
        if enabled:
            try:
                import win32com.client

                shell = win32com.client.Dispatch("WScript.Shell")
                shortcut = shell.CreateShortcut(path)
                if getattr(sys, "frozen", False):
                    shortcut.TargetPath = sys.executable
                    shortcut.IconLocation = sys.executable
                else:
                    shortcut.TargetPath = python_executable_for_shortcut()
                    shortcut.Arguments = f'"{os.path.join(APP_DIR, "mail_app.py")}"'
                    icon_path = os.path.join(RESOURCE_DIR, "ui", "app_icon.ico")
                    if os.path.isfile(icon_path):
                        shortcut.IconLocation = icon_path
                shortcut.WorkingDirectory = APP_DIR
                shortcut.Save()
                return {"ok": True, "message": "เปิดใช้งานเริ่มแอปอัตโนมัติเมื่อเปิดเครื่องแล้ว"}
            except Exception as exc:
                return {"ok": False, "message": f"ตั้งค่าไม่สำเร็จ: {exc}"}
        else:
            try:
                if os.path.isfile(path):
                    os.remove(path)
                return {"ok": True, "message": "ปิดการเริ่มแอปอัตโนมัติแล้ว"}
            except Exception as exc:
                return {"ok": False, "message": f"ปิดใช้งานไม่สำเร็จ: {exc}"}

    def get_reply_bridge(self):
        return {"enabled": is_reply_bridge_registered()}

    def set_reply_bridge(self, enabled):
        if enabled:
            return register_reply_bridge()
        return unregister_reply_bridge()

    def get_background_task(self):
        return {"enabled": is_background_task_registered()}

    def set_background_task(self, enabled):
        if enabled:
            cmd_parts = background_check_command()
            tr = " ".join(f'"{p}"' if " " in p else p for p in cmd_parts)
            try:
                result = subprocess.run(
                    [
                        "schtasks", "/create", "/tn", BACKGROUND_TASK_NAME,
                        "/tr", tr, "/sc", "minute", "/mo", "15", "/f",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if result.returncode != 0:
                    return {"ok": False, "message": f"สร้าง Scheduled Task ไม่สำเร็จ: {result.stderr.strip() or result.stdout.strip()}"}
                return {"ok": True, "message": "เปิดใช้งานระบบตรวจคิวเบื้องหลังแล้ว (ทำงานทุก 15 นาที แม้ปิดแอป)"}
            except Exception as exc:
                return {"ok": False, "message": f"สร้าง Scheduled Task ไม่สำเร็จ: {exc}"}
        else:
            try:
                result = subprocess.run(
                    ["schtasks", "/delete", "/tn", BACKGROUND_TASK_NAME, "/f"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if result.returncode != 0 and "ไม่พบ" not in result.stderr and "cannot find" not in result.stderr.lower():
                    return {"ok": False, "message": f"ปิดใช้งานไม่สำเร็จ: {result.stderr.strip()}"}
                return {"ok": True, "message": "ปิดระบบตรวจคิวเบื้องหลังแล้ว"}
            except Exception as exc:
                return {"ok": False, "message": f"ปิดใช้งานไม่สำเร็จ: {exc}"}

    def get_outlook_contacts(self):
        try:
            import win32com.client

            outlook = win32com.client.Dispatch("Outlook.Application")
            namespace = outlook.GetNamespace("MAPI")
            contacts_folder = namespace.GetDefaultFolder(10)  # olFolderContacts

            contacts = []
            seen = set()
            for item in contacts_folder.Items:
                try:
                    if item.Class != 40:  # olContact
                        continue
                    email = None
                    for addr_prop, type_prop in (
                        ("Email1Address", "Email1AddressType"),
                        ("Email2Address", "Email2AddressType"),
                        ("Email3Address", "Email3AddressType"),
                    ):
                        addr = getattr(item, addr_prop, None)
                        if not addr:
                            continue
                        if getattr(item, type_prop, None) == "EX":
                            try:
                                addr = item.PropertyAccessor.GetProperty(
                                    "http://schemas.microsoft.com/mapi/proptag/0x39FE001E"
                                )
                            except Exception:
                                addr = None
                        if addr and "@" in addr:
                            email = addr
                            break
                    if not email or email.lower() in seen:
                        continue
                    seen.add(email.lower())
                    name = item.FullName or item.CompanyName or email
                    contacts.append({"name": name, "email": email})
                except Exception:
                    continue

            contacts.sort(key=lambda c: c["name"].lower())
            return {"contacts": contacts}
        except Exception as exc:
            return {"error": f"ไม่สามารถอ่านสมุดที่อยู่ Outlook ได้: {exc}"}


def run_tray_and_watcher(window, icon_path):
    """System tray icon (minimize-to-tray) + a background thread that posts a
    native notification when a scheduled Outlook send is due soon, even while
    the window is hidden."""
    import pystray
    from PIL import Image

    quitting = {"flag": False}
    notified_ids = set()

    def show_window():
        window.show()
        window.restore()

    def quit_app(icon_obj, item=None):
        quitting["flag"] = True
        icon_obj.stop()
        window.destroy()

    def on_closing():
        if quitting["flag"]:
            return None
        window.hide()
        return False

    window.events.closing += on_closing

    try:
        image = Image.open(icon_path)
    except Exception:
        image = Image.new("RGBA", (32, 32), (22, 49, 79, 255))

    menu = pystray.Menu(
        pystray.MenuItem("เปิดแอป", lambda: show_window(), default=True),
        pystray.MenuItem("ออกจากโปรแกรม", quit_app),
    )
    tray_icon = pystray.Icon("mail_composer", image, "OverAll Uploader", menu)

    def watch_scheduled():
        while not quitting["flag"]:
            try:
                items = load_json_list(SCHEDULED_FILE)
                now = datetime.datetime.now()
                for item in items:
                    if item.get("status") != "pending" or item.get("id") in notified_ids:
                        continue
                    try:
                        send_dt = datetime.datetime.fromisoformat(item["send_time"])
                    except Exception:
                        continue
                    if 0 < (send_dt - now).total_seconds() <= 5 * 60:
                        notified_ids.add(item["id"])
                        try:
                            tray_icon.notify(
                                f"{item.get('subject') or '(ไม่มีหัวข้อ)'} — กำหนดส่ง {send_dt.strftime('%H:%M')} น.",
                                "ใกล้ถึงเวลาส่งอีเมลอัตโนมัติ",
                            )
                        except Exception:
                            pass
            except Exception:
                pass
            for _ in range(60):
                if quitting["flag"]:
                    break
                threading.Event().wait(1)

    threading.Thread(target=watch_scheduled, daemon=True).start()
    tray_icon.run_detached()
    return tray_icon


if __name__ == "__main__":
    if "--background-check" in sys.argv:
        run_background_check()
        sys.exit(0)

    if "--reply-bridge-host" in sys.argv:
        run_reply_bridge_host()
        sys.exit(0)

    ui_dir = os.path.join(RESOURCE_DIR, "ui")
    icon_path = os.path.join(ui_dir, "app_icon.ico")
    window = webview.create_window(
        "OverAll Uploader",
        url=os.path.join(ui_dir, "index.html"),
        js_api=Api(),
        width=1180,
        height=760,
        min_size=(960, 600),
        background_color="#e7ecf7",
    )

    def _setup_tray():
        if os.path.isfile(icon_path):
            try:
                run_tray_and_watcher(window, icon_path)
            except Exception:
                pass

    webview.start(_setup_tray, icon=icon_path if os.path.isfile(icon_path) else None)
