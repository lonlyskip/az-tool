import hashlib
import json
import os
import sys
import io
import base64
import uuid
import re
import subprocess
import threading
import time
import tkinter as tk
import ctypes
import ctypes.wintypes
from tkinter import messagebox
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from datetime import datetime, timezone
from PIL import Image, ImageEnhance, ImageTk, ImageChops, ImageStat

APP_NAME = "az tool"
LICENSE_SERVER = "https://az-tool-license.a-abdilaziz-a.workers.dev"
APP_DIR = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "az tool")
STATE_FILE = os.path.join(APP_DIR, "state.json")
# Radar scans only a compact lower-center notification region while Fortnite is foreground.
POLL_SECONDS = 0.50

EVENT_COOLDOWN_SECONDS = 1.5


MONEY_UNITS = ("QI", "SX", "SP", "OC", "NO")
UNIT_TO_QI = {unit: 1000 ** index for index, unit in enumerate(MONEY_UNITS)}


def calculate_afk_earnings(income_per_second, elapsed_seconds):
    """Estimate earnings using the editable per-second income only."""
    income_per_second = float(income_per_second)
    if income_per_second <= 0:
        raise ValueError("الدخل بالثانية لازم يكون أكبر من صفر.")
    return income_per_second * max(0.0, float(elapsed_seconds))


def income_to_qi(amount, unit):
    unit = str(unit or "").strip().upper()
    if unit not in UNIT_TO_QI:
        raise ValueError("اختر وحدة دخل صحيحة: QI أو SX أو SP أو OC أو NO.")
    amount = float(amount)
    if amount < 0:
        raise ValueError("المبلغ لا يمكن أن يكون سالباً.")
    return amount * UNIT_TO_QI[unit]


def format_money(amount_qi):
    amount = max(0.0, float(amount_qi or 0))
    unit_index = 0
    while amount >= 1000 and unit_index < len(MONEY_UNITS) - 1:
        amount /= 1000
        unit_index += 1
    return f"{amount:,.2f} {MONEY_UNITS[unit_index]}"


def format_expected_money(amount_qi):
    """Format forecast output in the largest available unit without changing tracked money."""
    amount = max(0.0, float(amount_qi or 0))
    unit_index = 0
    while amount >= 1000 and unit_index < len(MONEY_UNITS) - 1:
        amount /= 1000
        unit_index += 1
    number = f"{amount:,.2f}".rstrip("0").rstrip(".")
    return f"{number}{MONEY_UNITS[unit_index].lower()}"


AFK_LOADING_TERMS = (
    "loading", "connecting", "matchmaking", "joining server",
    "traveling to", "travelling to", "checking for updates",
    "logging in", "waiting for", "preparing"
)
AFK_LOBBY_TERMS = (
    "battle royale", "zero build", "item shop", "locker",
    "quests", "v bucks", "vbucks", "party up", "ready up",
    "discover", "play", "lobby", "friends", "invite", "battle pass"
)


def classify_afk_screen(text):
    """Classify OCR text conservatively; unknown screens never count as a connection."""
    normalized = re.sub(r"[^a-z0-9 ]", " ", str(text or "").lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return "unknown"
    if any(term in normalized for term in AFK_LOADING_TERMS):
        return "loading"
    if any(
        (term in normalized) if term != "play" else bool(re.search(r"\bplay\b", normalized))
        for term in AFK_LOBBY_TERMS
    ):
        return "lobby"
    return "gameplay"


def runtime_base_dir():
    """Return the directory containing bundled onefile data for Nuitka or a source run."""
    compiled = globals().get("__compiled__")
    if compiled is not None:
        containing_dir = getattr(compiled, "containing_dir", None)
        if containing_dir:
            return os.path.abspath(containing_dir)
    return os.path.dirname(os.path.abspath(__file__))


def notification_region(monitor):
    """Small lower-center OCR region, clamped to the primary display bounds."""
    left_edge = int(monitor["left"])
    top_edge = int(monitor["top"])
    width = max(1, int(monitor["width"]))
    height = max(1, int(monitor["height"]))
    region_width = max(1, int(width * 0.48))
    region_height = max(1, int(height * 0.16))
    left = left_edge + (width - region_width) // 2
    top = top_edge + int(height * 0.78)
    top = min(top, top_edge + height - region_height)
    return {"left": left, "top": top, "width": region_width, "height": region_height}

BG = "#0b0d12"
PANEL = "#131722"
PANEL_2 = "#1a2030"
TEXT = "#edf2ff"
MUTED = "#8d98b3"
ACCENT = "#8b7cff"
GREEN = "#50e3a4"
RED = "#ff657a"


def device_id():
    raw = "|".join((os.getenv("COMPUTERNAME", ""), os.getenv("PROCESSOR_IDENTIFIER", ""), os.getenv("USERNAME", "")))
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def post(path, payload, timeout=10):
    req = Request(
        LICENSE_SERVER.rstrip("/") + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "az-tool-license-client/1.0"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            try:
                return json.loads(raw)
            except ValueError:
                raise RuntimeError(f"License server returned invalid JSON (HTTP {response.status}).")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
            detail = data.get("error") or data.get("message")
            if not detail:
                detail = f"HTTP {exc.code}: {raw[:500]}"
        except ValueError:
            detail = f"HTTP {exc.code}: {raw[:500]}"
        raise RuntimeError(f"License server rejected the request: {detail}") from None
    except URLError as exc:
        raise RuntimeError(f"Cannot reach license server: {exc.reason}") from None


def arabic_error(message):
    """Translate common license-server errors into clear Arabic messages."""
    raw = str(message or "").strip()
    value = raw.lower()

    if any(term in value for term in ("expired", "expiry", "انته", "منتهي")):
        return "كود التفعيل منتهي الصلاحية. جدّد الاشتراك أو تواصل مع المسؤول."
    if any(term in value for term in ("revoked", "revoke", "ملغي", "ملغى", "موقوف")):
        return "كود التفعيل ملغي أو موقوف. تواصل مع المسؤول."
    if any(term in value for term in ("bound to another device", "another device", "device mismatch", "جهاز آخر")):
        return "كود التفعيل مرتبط بجهاز آخر ولا يمكن استخدامه على هذا الجهاز."
    if any(term in value for term in ("invalid", "not found", "unknown license", "غير صالح", "غير صحيح")):
        return "كود التفعيل غير صالح أو غير موجود. تأكد من كتابته بشكل صحيح."
    if any(term in value for term in ("configuration", "internal server", "server error", "http 500")):
        return "حدث خطأ في إعدادات السيرفر. حاول لاحقًا أو تواصل مع المسؤول."
    if any(term in value for term in ("cannot reach", "timed out", "connection", "urlopen", "network")):
        return "تعذر الاتصال بسيرفر التفعيل. تحقق من الإنترنت وحاول مرة أخرى."
    if raw:
        return "تعذر تفعيل الكود: " + raw
    return "تعذر تفعيل الكود لسبب غير معروف. حاول مرة أخرى."


def load_state():
    """Load only a valid state object; tolerate missing or damaged local state."""
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            state = json.load(file)
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def save_state(state):
    """Atomically persist state so interruption cannot leave a truncated JSON file."""
    os.makedirs(APP_DIR, exist_ok=True)
    temporary_path = STATE_FILE + ".tmp"
    try:
        with open(temporary_path, "w", encoding="utf-8") as file:
            json.dump(state, file, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, STATE_FILE)
    finally:
        try:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)
        except OSError:
            pass


def parse_expiry(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


class AzToolApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("680x1050")
        self.root.minsize(620, 900)
        self.root.configure(bg=BG)
        self._background_original = None
        self._background_photo = None
        self._background_label = None
        self._background_resize_job = None
        self._setup_background()
        # Force the native Windows caption/title bar into dark mode.
        self.root.update_idletasks()
        if os.name == "nt":
            try:
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
                dark = ctypes.c_int(1)
                for attribute in (20, 19):
                    if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(dark), ctypes.sizeof(dark)) == 0:
                        break
            except Exception:
                pass
        base_dir = runtime_base_dir()
        icon_candidates = (
            os.path.join(base_dir, "az-tool-icon.ico"),
            os.path.join(base_dir, "assets", "az-tool-icon.ico"),
        )
        icon_path = next((path for path in icon_candidates if os.path.exists(path)), icon_candidates[0])
        try:
            self.root.iconbitmap(icon_path)
        except (tk.TclError, OSError):
            pass
        self.state = load_state()
        self.license_key = tk.StringVar(value=str(self.state.get("license_key", "")).strip())
        self.discord_id = tk.StringVar(value=self.state.get("discord_id", ""))
        self.status = tk.StringVar(value="Not activated")
        self.link_status = tk.StringVar(value="Discord account not linked")
        self.expiry = tk.StringVar(value="—")
        self.radar_status = tk.StringVar(value="OFF • Waiting for license and Discord verification")
        self.radar_enabled = False
        self._radar_stop = threading.Event()
        self._polling = False
        self._radar_thread = None
        self._last_event_key = None
        self._last_event_at = 0.0
        self._last_ocr_status_at = 0.0
        self._last_license_check = 0.0
        self._license_check_in_progress = False
        self._activation_in_progress = False
        self._subscription_expired = False
        self._link_verified = False
        self._discord_skipped = False
        self.state.pop('discord_skipped', None)
        self.afk_enabled = False
        self._afk_stop = threading.Event()
        # Keep the collection counter across AFK stop/start and app restarts.
        try:
            self._afk_elapsed = max(0.0, float(self.state.get("afk_elapsed_seconds", 0.0)))
        except (TypeError, ValueError):
            self._afk_elapsed = 0.0
        self._afk_last_tick = None
        self._afk_earnings_thread = None
        self.base_income = tk.StringVar(value=str(self.state.get("afk_base_income", "1")))
        saved_income_unit = str(self.state.get("afk_income_unit", "QI")).strip().upper()
        if saved_income_unit not in MONEY_UNITS:
            saved_income_unit = "QI"
        self.income_unit = tk.StringVar(value=saved_income_unit)
        # Forecast calculator has its own inputs and never touches tracked earnings.
        self.forecast_income = tk.StringVar(value="900")
        self.forecast_unit = tk.StringVar(value="SX")
        self.forecast_days = tk.StringVar(value="0")
        self.forecast_hours = tk.StringVar(value="0")
        self.forecast_minutes = tk.StringVar(value="0")
        self.forecast_result = tk.StringVar(value="أدخل الدخل والمدة ثم اضغط احسب.")
        try:
            self._afk_last_sync_elapsed = max(
                0.0, float(self.state.get("afk_last_sync_elapsed", self._afk_elapsed))
            )
        except (TypeError, ValueError):
            self._afk_last_sync_elapsed = self._afk_elapsed
        self._afk_pending_sync = None
        # Remove obsolete settings from older versions.
        self.state.pop("afk_rebirth", None)
        self.state.pop("afk_colors", None)
        self.afk_earnings_status = tk.StringVar(value="المدة: 00:00:00 | الدخل: 0.00 QI")
        self._afk_thread = None
        self._afk_monitor_thread = None
        self._hotkey_thread = None
        self._hotkey_thread_id = None
        self._hotkey_ready = threading.Event()
        self._closing = False
        self._build()
        # A saved key is never trusted locally: validate it with the license server on every launch.
        self.state.pop("discord_skipped", None)
        save_state(self.state)
        saved_key = self.license_key.get().strip()
        if saved_key:
            self.license_card.pack_forget()
            self.status.set("Restoring saved session…")
            self.root.after(150, self.check_subscription)
        else:
            self.license_card.pack(fill="x", padx=24, pady=8)
            self.status.set("Enter your license key to activate")
        if os.name == "nt":
            self._hotkey_thread = threading.Thread(target=self._global_f5_listener, daemon=True)
            self._hotkey_thread.start()

    def _setup_background(self):
        """Load the bundled Nexora artwork as a dark, full-window background."""
        base_dir = runtime_base_dir()
        image_path = os.path.join(base_dir, "IMG_4552.jpg")
        try:
            self._background_original = Image.open(image_path).convert("RGB")
            self._background_label = tk.Label(self.root, bd=0, highlightthickness=0, bg=BG)
            self._background_label.place(x=0, y=0, relwidth=1, relheight=1)
            self._background_label.lower()
            self.root.bind("<Configure>", self._on_background_resize, add="+")
            self.root.after(80, self._render_background)
        except (OSError, tk.TclError):
            # Keep the normal dark interface if the optional artwork cannot be loaded.
            self._background_original = None

    def _on_background_resize(self, event):
        if event.widget is not self.root or self._background_original is None:
            return
        if self._background_resize_job is not None:
            self.root.after_cancel(self._background_resize_job)
        self._background_resize_job = self.root.after(100, self._render_background)

    def _render_background(self):
        self._background_resize_job = None
        if self._background_original is None or self._background_label is None:
            return
        width = max(1, self.root.winfo_width())
        height = max(1, self.root.winfo_height())
        source = self._background_original
        scale = max(width / source.width, height / source.height)
        resized = source.resize(
            (max(width, int(source.width * scale)), max(height, int(source.height * scale))),
            Image.Resampling.LANCZOS,
        )
        left = (resized.width - width) // 2
        top = (resized.height - height) // 2
        resized = resized.crop((left, top, left + width, top + height))
        # Darken the artwork so the existing labels, cards, and controls stay readable.
        resized = ImageEnhance.Brightness(resized).enhance(0.42)
        self._background_photo = ImageTk.PhotoImage(resized)
        self._background_label.configure(image=self._background_photo)
        self._background_label.lower()

    def label(self, parent, text, color=TEXT, size=10, bold=False):
        widget = tk.Label(
            parent, text=text, bg=parent["bg"], fg=color,
            font=("Segoe UI", size, "bold" if bold else "normal"),
            wraplength=520, justify="left", anchor="w"
        )
        # Keep long descriptions readable when the window is resized.
        def update_wrap(event=None):
            try:
                available = max(220, parent.winfo_width() - 42)
                widget.configure(wraplength=min(680, available))
            except tk.TclError:
                pass

        parent.bind("<Configure>", update_wrap, add="+")
        widget.bind("<Configure>", update_wrap, add="+")
        return widget

    def card(self, parent, title, subtitle=None):
        frame = tk.Frame(parent, bg=PANEL, padx=18, pady=16,
                         highlightthickness=1, highlightbackground="#242b3b")
        frame.pack(fill="x", padx=24, pady=8)
        self.label(frame, title, size=11, bold=True).pack(anchor="w")
        if subtitle:
            self.label(frame, subtitle, MUTED, 9).pack(anchor="w", pady=(4, 10))
        return frame

    def entry(self, parent, variable, show=None):
        widget = tk.Entry(parent, textvariable=variable, show=show, bg=PANEL_2, fg=TEXT,
                          insertbackground=TEXT, relief="flat", font=("Segoe UI", 10),
                          highlightthickness=1, highlightbackground="#30394d",
                          highlightcolor=ACCENT)

        # Clipboard actions are implemented directly because Tk's virtual Paste event
        # can silently do nothing in some packaged Windows builds.
        menu = tk.Menu(widget, tearoff=0, bg=PANEL_2, fg=TEXT,
                       activebackground=ACCENT, activeforeground="white")

        def paste_clipboard(event=None):
            try:
                value = self.root.clipboard_get()
            except tk.TclError:
                self.status.set("الحافظة فارغة أو تعذر الوصول إليها")
                return "break"
            try:
                if widget.selection_present():
                    widget.delete("sel.first", "sel.last")
                widget.insert("insert", value)
            except tk.TclError:
                pass
            return "break"

        def copy_selection(event=None, cut=False):
            try:
                value = widget.get("sel.first", "sel.last")
            except tk.TclError:
                return "break"
            self.root.clipboard_clear()
            self.root.clipboard_append(value)
            if cut:
                widget.delete("sel.first", "sel.last")
            return "break"

        def select_all(event=None):
            widget.select_range(0, "end")
            widget.icursor("end")
            return "break"

        menu.add_command(label="Cut", command=lambda: copy_selection(cut=True))
        menu.add_command(label="Copy", command=copy_selection)
        menu.add_command(label="Paste", command=paste_clipboard)
        menu.add_command(label="Select all", command=select_all)

        def show_menu(event):
            try:
                widget.focus_set()
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        widget.bind("<Button-3>", show_menu)
        widget.bind("<Control-v>", paste_clipboard)
        widget.bind("<Control-KeyPress-v>", paste_clipboard)
        widget.bind("<Control-V>", paste_clipboard)
        widget.bind("<Control-KeyPress-V>", paste_clipboard)
        widget.bind("<Shift-Insert>", paste_clipboard)
        widget.bind("<Control-c>", copy_selection)
        widget.bind("<Control-x>", lambda event: copy_selection(cut=True))
        widget.bind("<Control-a>", select_all)
        return widget

    def button(self, parent, text, command, color=ACCENT, fg="white"):
        return tk.Button(parent, text=text, command=command, bg=color, fg=fg,
                         activebackground=color, activeforeground=fg, relief="flat",
                         cursor="hand2", font=("Segoe UI", 9, "bold"), padx=14, pady=9)

    def open_discord_server(self):
        import webbrowser
        webbrowser.open("https://discord.gg/4W3CCJyfN", new=2)

    def _build(self):
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=28, pady=(22, 8))
        self.label(header, "az Tool", size=25, bold=True).pack(anchor="w")
        self.label(header, "LICENSED DESKTOP CLIENT", MUTED, 9, True).pack(anchor="w", pady=(2, 0))
        self.button(header, "سيرفر الدسكورد", lambda: self.open_discord_server(), color="#29314a").pack(anchor="e", pady=(0, 4))

        license_card = self.card(self.root, "License", "Activate your key on this device.")
        self.license_card = license_card
        row = tk.Frame(license_card, bg=PANEL)
        row.pack(fill="x")
        self.entry(row, self.license_key, show="•").pack(side="left", fill="x", expand=True, ipady=10)
        self.button(row, "ACTIVATE", self.activate).pack(side="left", padx=(10, 0))
        tk.Label(license_card, textvariable=self.status, bg=PANEL, fg=GREEN, font=("Segoe UI", 9)).pack(anchor="w", pady=(10, 0))
        expiry_row = tk.Frame(license_card, bg=PANEL)
        expiry_row.pack(fill="x", pady=(5, 0))
        self.label(expiry_row, "Subscription", MUTED, 9).pack(side="left")
        tk.Label(expiry_row, textvariable=self.expiry, bg=PANEL, fg=TEXT, font=("Segoe UI", 9, "bold")).pack(side="right")

        self.gated_frame = tk.Frame(self.root, bg=BG)
        self.gated_frame.pack(fill="x")

        self.discord_card = self.card(self.gated_frame, "Discord verification", "Enter your Discord user ID, then approve the bot's verification request.")
        discord_card = self.discord_card
        self.entry(discord_card, self.discord_id).pack(fill="x", ipady=10)
        actions = tk.Frame(discord_card, bg=PANEL)
        actions.pack(fill="x", pady=(10, 0))
        self.button(actions, "VERIFY & SAVE", self.request_link, color="#29314a").pack(side="left")
        self.button(actions, "SKIP FOR NOW", self.skip_discord, color="#303747").pack(side="right")
        tk.Label(discord_card, textvariable=self.link_status, bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9), wraplength=520, justify="left").pack(anchor="w", pady=(10, 0))

        self.afk_card = self.card(self.gated_frame, "AFK", "F5 toggles AFK mode")
        self.afk_button = self.button(self.afk_card, "START AFK  [F5]", self.toggle_afk, color=GREEN, fg="#07110d")
        self.afk_button.pack(fill="x")
        self.afk_status = tk.StringVar(value="AFK is OFF.")
        tk.Label(self.afk_card, textvariable=self.afk_status, bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(8, 0))
        settings = tk.Frame(self.afk_card, bg=PANEL)
        settings.pack(fill="x", pady=(12, 0))
        self.label(settings, "الدخل بالثانية", MUTED, 9).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.entry(settings, self.base_income).grid(row=0, column=1, sticky="ew", pady=4, ipady=6)
        self.income_unit_menu = tk.OptionMenu(settings, self.income_unit, *MONEY_UNITS)
        self.income_unit_menu.configure(bg=PANEL_2, fg=TEXT, activebackground=ACCENT,
                                         activeforeground="white", relief="flat",
                                         highlightthickness=0, width=5)
        self.income_unit_menu["menu"].configure(bg=PANEL_2, fg=TEXT,
                                                activebackground=ACCENT,
                                                activeforeground="white")
        self.income_unit_menu.grid(row=0, column=2, sticky="ew", padx=(8, 0), pady=4)
        settings.columnconfigure(1, weight=1)
        self.button(settings, "حفظ الدخل والوحدة", self.save_afk_settings, color="#29314a").grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 4))
        tk.Label(self.afk_card, textvariable=self.afk_earnings_status, bg=PANEL, fg=GREEN, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(5, 0))
        self.button(self.afk_card, "إعادة تعيين التجميع الحالي",
                    self.reset_afk_earnings, color="#29314a").pack(fill="x", pady=(10, 0))

        self.forecast_card = self.card(
            self.gated_frame, "حاسبة الدخل المتوقع",
            "حاسبة مستقلة — لا تغيّر رصيد التجميع أو إحصائياتك."
        )
        forecast_income_row = tk.Frame(self.forecast_card, bg=PANEL)
        forecast_income_row.pack(fill="x", pady=(4, 8))
        self.label(forecast_income_row, "الدخل بالثانية", MUTED, 9).pack(side="left", padx=(0, 8))
        self.entry(forecast_income_row, self.forecast_income).pack(side="left", fill="x", expand=True, ipady=6)
        self.forecast_unit_menu = tk.OptionMenu(forecast_income_row, self.forecast_unit, *MONEY_UNITS)
        self.forecast_unit_menu.configure(
            bg=PANEL_2, fg=TEXT, activebackground=ACCENT,
            activeforeground="white", relief="flat",
            highlightthickness=0, width=5
        )
        self.forecast_unit_menu["menu"].configure(
            bg=PANEL_2, fg=TEXT, activebackground=ACCENT,
            activeforeground="white"
        )
        self.forecast_unit_menu.pack(side="left", padx=(8, 0))
        self.label(self.forecast_card, "المدة — تقدر تجمع أيام وساعات ودقائق مع بعض", MUTED, 9).pack(anchor="w", pady=(4, 6))
        forecast_time_row = tk.Frame(self.forecast_card, bg=PANEL)
        forecast_time_row.pack(fill="x")
        for column, (caption, variable) in enumerate((
            ("أيام", self.forecast_days),
            ("ساعات", self.forecast_hours),
            ("دقائق", self.forecast_minutes),
        )):
            cell = tk.Frame(forecast_time_row, bg=PANEL)
            cell.pack(side="left", fill="x", expand=True, padx=(0 if column == 0 else 6, 0))
            self.label(cell, caption, MUTED, 9).pack(anchor="w")
            self.entry(cell, variable).pack(fill="x", ipady=6)
        self.button(
            self.forecast_card, "احسب الدخل المتوقع",
            self.calculate_expected_income, color=ACCENT
        ).pack(fill="x", pady=(10, 8))
        tk.Label(
            self.forecast_card, textvariable=self.forecast_result,
            bg=PANEL, fg=GREEN, font=("Segoe UI", 11, "bold"),
            wraplength=520, justify="left"
        ).pack(anchor="w")

        self.radar_card = self.card(self.gated_frame, "Spawn Radar", "Fortnite • Go Up for Brainrot • Notification-area detection")
        radar_card = self.radar_card
        self.radar_button = self.button(radar_card, "START RADAR", self.toggle_radar, color=GREEN, fg="#07110d")
        self.radar_button.pack(fill="x")
        tk.Label(radar_card, textvariable=self.radar_status, bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9), wraplength=520, justify="left").pack(anchor="w", pady=(10, 0))
        self.label(radar_card, "Shows live OCR text from the notification area. Server acceptance and Discord delivery are reported separately.", MUTED, 9).pack(anchor="w", pady=(5, 0))
        self.label(radar_card, "Privacy: while Radar is ON and Fortnite is the active window, the app checks a small lower-center screen area for Spawn/Spawned text. It uploads an image crop around detected text to the AZ Tool server over HTTPS only after a match. If OCR cannot provide text coordinates, the full small scan area is sent instead. No screen image is intentionally saved to disk. Stop Radar to stop screen checks.", MUTED, 9).pack(anchor="w", pady=(7, 0))


        self.discord_card.pack_forget()
        self.afk_card.pack_forget()
        self.radar_card.pack_forget()
        # F5 is registered globally below so it works while Fortnite is focused.

        footer = tk.Frame(self.root, bg=BG)
        footer.pack(fill="x", padx=28, pady=(10, 18))
        self.label(footer, "Radar privacy details are shown in the Spawn Radar section. Screen images are uploaded only after a Spawn match.", MUTED, 8).pack(anchor="w")
        if self.license_key.get().strip():
            self.status.set("Saved key loaded — activate to validate")
        self.root.after(1000, self._refresh_link_state)
        self.root.after(1000, self._schedule_subscription_check)

    def _show_gated_sections(self):
        if not self._link_verified and not self._discord_skipped:
            if not self.discord_card.winfo_manager():
                self.discord_card.pack(fill="x", padx=24, pady=8)
        else:
            self.discord_card.pack_forget()
        for card in (self.afk_card, self.forecast_card, self.radar_card):
            if not card.winfo_manager():
                card.pack(fill="x", padx=24, pady=8)
        if self._link_verified:
            self.radar_button.config(state="normal", bg=GREEN)
        else:
            self.radar_button.config(state="disabled", bg="#303747")
            self.radar_status.set("Discord verification is needed for alert delivery.")

    def _hide_gated_sections(self):
        self.stop_radar()
        self._link_verified = False
        self._discord_skipped = False
        self.discord_card.pack_forget()
        self.afk_card.pack_forget()
        self.forecast_card.pack_forget()
        self.radar_card.pack_forget()

    def activate(self):
        key = self.license_key.get().strip()
        if not key:
            messagebox.showerror("License", "Enter your license key first.")
            return
        self._activation_in_progress = True
        self._subscription_expired = False
        self.status.set("Checking license…")
        threading.Thread(target=self._activate_worker, args=(key,), daemon=True).start()

    def _activate_worker(self, key):
        try:
            result = post("/api/activate", {"code": key, "device_id": device_id()})
            if result.get("valid") is True or result.get("success") is True or result.get("activated") is True:
                expiry_value = result.get("expires_at") or result.get("expires")
                parsed_expiry = parse_expiry(expiry_value)
                if not parsed_expiry or parsed_expiry <= datetime.now(timezone.utc):
                    raise RuntimeError("License server did not return a future expiry time.")
                self._subscription_expired = False
                self.state["license_key"] = key
                self.state["expires_at"] = parsed_expiry.isoformat()
                save_state(self.state)
                self.root.after(0, lambda: self.status.set("Activated • license accepted"))
                self.root.after(0, self.license_card.pack_forget)
                self.root.after(0, lambda: self.expiry.set(parsed_expiry.strftime("%Y-%m-%d %H:%M UTC")))
                self.root.after(0, self._show_gated_sections)
                self.root.after(0, self._resume_saved_discord_link)
                self.root.after(0, lambda: setattr(self, "_activation_in_progress", False))
            else:
                self.state.pop("license_key", None)
                self.state.pop("expires_at", None)
                save_state(self.state)
                self.root.after(0, lambda: self.license_key.set(""))
                self.root.after(0, lambda: self.status.set("Activation failed"))
                self.root.after(0, self.license_card.pack)
                self.root.after(0, self._hide_gated_sections)
                self.root.after(0, lambda: messagebox.showerror("فشل التفعيل", arabic_error(result.get("error", "Activation was rejected."))))
                self.root.after(0, lambda: setattr(self, "_activation_in_progress", False))
        except Exception as exc:
            self.root.after(0, lambda: self.status.set("Server unavailable"))
            self.root.after(0, self._hide_gated_sections)
            self.root.after(0, lambda err=str(exc): messagebox.showerror("Connection", f"Could not contact the license server.\n\n{err}"))
            self.root.after(0, lambda: setattr(self, "_activation_in_progress", False))

    def _schedule_subscription_check(self):
        """Revalidate active subscriptions periodically without overlapping requests."""
        if self._closing or self._subscription_expired:
            return
        if not self._activation_in_progress:
            key = self.license_key.get().strip()
            if key and not self._license_check_in_progress:
                self._license_check_in_progress = True
                threading.Thread(target=self._automatic_subscription_check, args=(key,), daemon=True).start()
        if not self._closing and not self._subscription_expired:
            self.root.after(60_000, self._schedule_subscription_check)

    def _automatic_subscription_check(self, key):
        try:
            local_expiry = parse_expiry(self.state.get("expires_at"))
            if local_expiry and local_expiry <= datetime.now(timezone.utc):
                self.root.after(0, self._handle_expired_subscription)
                return
            result = post("/api/validate", {"code": key, "device_id": device_id()}, timeout=8)
            # Treat explicit server status as authoritative; some API responses may
            # include success=true while separately reporting revoked/expired.
            status = str(result.get("status", result.get("license_status", ""))).strip().lower()
            explicitly_invalid = (
                result.get("valid") is False
                or result.get("active") is False
                or result.get("revoked") is True
                or result.get("expired") is True
                or status in {"invalid", "inactive", "revoked", "expired", "cancelled", "canceled", "suspended", "disabled", "rejected"}
            )
            valid = not explicitly_invalid and (
                result.get("valid") is True
                if "valid" in result
                else result.get("success") is True or result.get("active") is True
            )
            expiry_value = result.get("expires_at") or result.get("expires") or self.state.get("expires_at")
            parsed_expiry = parse_expiry(expiry_value)
            if not valid or not parsed_expiry or parsed_expiry <= datetime.now(timezone.utc):
                self.root.after(0, self._handle_expired_subscription)
                return
            self.state["license_key"] = key
            self.state["expires_at"] = parsed_expiry.isoformat()
            save_state(self.state)
            self.root.after(0, lambda expiry=parsed_expiry: self.expiry.set(expiry.strftime("%Y-%m-%d %H:%M UTC")))
        except RuntimeError as exc:
            # HTTP rejection from the license API means the license was rejected;
            # transient connectivity failures should not revoke a valid subscription.
            if "License server rejected the request:" in str(exc):
                self.root.after(0, self._handle_expired_subscription)
        except Exception:
            # A network error alone does not prove the subscription expired.
            pass
        finally:
            self._license_check_in_progress = False

    def _handle_expired_subscription(self):
        if self._subscription_expired or self._closing or self._activation_in_progress:
            return
        self._subscription_expired = True
        self._polling = False
        self._afk_stop.set()
        self.afk_enabled = False
        self.radar_enabled = False
        self._link_verified = False
        self.state.pop("license_key", None)
        self.state.pop("expires_at", None)
        self.state.pop("discord_skipped", None)
        save_state(self.state)
        self.license_key.set("")
        self.status.set("Subscription expired")
        self.expiry.set("Expired")
        try:
            if os.name == "nt":
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        except Exception:
            pass
        messagebox.showerror("انتهى الاشتراك", "انتهى اشتراكك. اضغط موافق للعودة إلى شاشة إدخال كود التفعيل.")
        self.close()

    def check_subscription(self):
        key = self.license_key.get().strip() or str(self.state.get("license_key", "")).strip()
        if not key:
            self.license_card.pack(fill="x", padx=24, pady=8)
            self.status.set("Enter a license key, then activate.")
            return
        self.status.set("Checking subscription…")
        threading.Thread(target=self._check_subscription_worker, args=(key,), daemon=True).start()

    def _check_subscription_worker(self, key):
        try:
            result = post("/api/validate", {"code": key, "device_id": device_id()})
            status = str(result.get("status", result.get("license_status", ""))).strip().lower()
            explicitly_invalid = (
                result.get("valid") is False
                or result.get("active") is False
                or result.get("revoked") is True
                or result.get("expired") is True
                or status in {"invalid", "inactive", "revoked", "expired", "cancelled", "canceled", "suspended", "disabled", "rejected"}
            )
            valid = not explicitly_invalid and (
                result.get("valid") is True
                if "valid" in result
                else result.get("success") is True or result.get("active") is True
            )
            expiry_value = result.get("expires_at") or result.get("expires") or self.state.get("expires_at")
            parsed_expiry = parse_expiry(expiry_value)
            valid = valid and parsed_expiry is not None and parsed_expiry > datetime.now(timezone.utc)
            if valid:
                self.state["license_key"] = key
                self.state["expires_at"] = parsed_expiry.isoformat()
                save_state(self.state)
                self.root.after(0, lambda: self.status.set("Subscription verified"))
                self.root.after(0, lambda: self.expiry.set(parsed_expiry.strftime("%Y-%m-%d %H:%M UTC")))
                self.root.after(0, self.license_card.pack_forget)
                self.root.after(0, self._show_gated_sections)
                self.root.after(0, self._resume_saved_discord_link)
            else:
                self.state.pop("license_key", None)
                self.state.pop("expires_at", None)
                save_state(self.state)
                self.root.after(0, lambda: self.license_key.set(""))
                self.root.after(0, lambda: self.status.set("Subscription expired or revoked"))
                self.root.after(0, self._hide_gated_sections)
                self.root.after(0, lambda: self.license_card.pack(fill="x", padx=24, pady=8))
                self.root.after(0, lambda: messagebox.showerror("الاشتراك", "الاشتراك منتهي أو ملغي. أدخل كودًا صالحًا للتفعيل."))
        except Exception:
            self.root.after(0, lambda: self.status.set("Could not verify subscription"))
            self.root.after(0, lambda: self.license_card.pack(fill="x", padx=24, pady=8))
            self.root.after(0, lambda: messagebox.showerror("الاشتراك", "تعذر التحقق الآن. لم يتم اعتبار الاشتراك صالحًا بناءً على هذا الفحص."))
    def _resume_saved_discord_link(self):
        """Restore Discord verification only after the saved license passes server validation."""
        discord_id = str(self.state.get("discord_id", "")).strip()
        if not discord_id or self._link_verified or self._subscription_expired:
            return
        request_id = self.state.get("link_request_id")
        if request_id:
            self._polling = True
            self.link_status.set("Restoring Discord verification…")
            threading.Thread(target=self._poll_link_status, daemon=True).start()
        else:
            # The server confirms whether this Discord account is already linked.
            self.discord_id.set(discord_id)
            self.request_link()

    def skip_discord(self):
        self._discord_skipped = True
        self.state["discord_skipped"] = True
        save_state(self.state)
        self._show_gated_sections()

    def _global_f5_listener(self):
        # Register F5 system-wide so it works even when Fortnite has focus.
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            self._hotkey_thread_id = kernel32.GetCurrentThreadId()
            MOD_NOREPEAT = 0x4000
            if not user32.RegisterHotKey(None, 0xA501, MOD_NOREPEAT, 0x74):
                self.root.after(0, lambda: self.afk_status.set("Global F5 unavailable; another app may already use it."))
                return
            self._hotkey_ready.set()
            msg = ctypes.wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312 and msg.wParam == 0xA501:  # WM_HOTKEY
                    self.root.after(0, self.toggle_afk)
                if self._closing:
                    break
            user32.UnregisterHotKey(None, 0xA501)
        except Exception as exc:
            self.root.after(0, lambda err=str(exc): self.afk_status.set("Global F5 error: " + err[:90]))

    def calculate_expected_income(self):
        """Calculate a separate forecast; do not persist or sync it to the money ledger."""
        try:
            income = float(self.forecast_income.get().strip().replace(",", ""))
            unit = self.forecast_unit.get().strip().upper()
            if income <= 0:
                raise ValueError("أدخل دخلًا أكبر من صفر.")
            if unit not in UNIT_TO_QI:
                raise ValueError("اختر وحدة دخل صحيحة.")
            days = float(self.forecast_days.get().strip() or 0)
            hours = float(self.forecast_hours.get().strip() or 0)
            minutes = float(self.forecast_minutes.get().strip() or 0)
            if min(days, hours, minutes) < 0:
                raise ValueError("المدة لا يمكن أن تكون سالبة.")
            total_seconds = days * 86400 + hours * 3600 + minutes * 60
            if total_seconds <= 0:
                raise ValueError("أدخل مدة أكبر من صفر.")
            total_qi = income_to_qi(income, unit) * total_seconds
            self.forecast_result.set(
                f"الدخل المتوقع: {format_expected_money(total_qi)}"
            )
        except (ValueError, TypeError, OverflowError) as exc:
            self.forecast_result.set(str(exc) or "تأكد من صحة الدخل والمدة.")

    def save_afk_settings(self):
        if self.afk_enabled:
            messagebox.showwarning("إعدادات AFK", "أوقف AFK قبل تعديل قيمة الدخل أو وحدته.")
            return False
        try:
            income = float(self.base_income.get().strip())
            calculate_afk_earnings(income, 0)
            unit = self.income_unit.get().strip().upper()
            if unit not in MONEY_UNITS:
                raise ValueError("اختر وحدة صحيحة للدخل.")
            income_to_qi(income, unit)
        except (TypeError, ValueError) as exc:
            messagebox.showerror("إعدادات AFK", str(exc) or "أدخل دخلًا صحيحًا أكبر من صفر.")
            return False
        self.state["afk_base_income"] = str(income)
        self.state["afk_income_unit"] = unit
        self.state.pop("afk_rebirth", None)
        self.state.pop("afk_colors", None)
        save_state(self.state)
        self.afk_status.set(f"تم حفظ الدخل: {income:,.4g} {unit} في الثانية")
        return True

    def _sync_afk_earnings(self, through_elapsed):
        """Send an idempotent earnings interval to the Worker in canonical QI."""
        through_elapsed = max(0.0, float(through_elapsed))
        pending = self._afk_pending_sync
        if pending is None:
            delta_seconds = through_elapsed - self._afk_last_sync_elapsed
            if delta_seconds <= 0.001:
                return True
            income = float(self.base_income.get())
            unit = self.income_unit.get().strip().upper()
            amount_qi = income_to_qi(income * delta_seconds, unit)
            payload = {
                "code": self.license_key.get().strip(),
                "device_id": device_id(),
                "event_id": uuid.uuid4().hex,
                "amount": amount_qi,
                "elapsed_seconds": round(delta_seconds, 3)
            }
            pending = {"payload": payload, "end_elapsed": through_elapsed}
            self._afk_pending_sync = pending
        try:
            result = post("/api/money/add", pending["payload"], timeout=12)
            if isinstance(result, dict) and (
                result.get("ok") is False or result.get("success") is False
            ):
                raise RuntimeError(result.get("error", "Worker rejected the earnings event."))
            self._afk_last_sync_elapsed = float(pending["end_elapsed"])
            self.state["afk_elapsed_seconds"] = self._afk_elapsed
            self.state["afk_last_sync_elapsed"] = self._afk_last_sync_elapsed
            save_state(self.state)
            self._afk_pending_sync = None
            if through_elapsed - self._afk_last_sync_elapsed > 0.001:
                return self._sync_afk_earnings(through_elapsed)
            return True
        except Exception as exc:
            if not self._closing:
                message = str(exc)[:100]
                self.root.after(0, lambda msg=message: self.afk_status.set(
                    f"تعذر مزامنة الأرباح مع السيرفر: {msg}"
                ))
            return False

    def _afk_earnings_loop(self):
        import win32gui
        try:
            while not self._afk_stop.is_set() and not self._closing:
                try:
                    hwnd = win32gui.GetForegroundWindow()
                    title = win32gui.GetWindowText(hwnd).lower()
                    now = time.monotonic()
                    if "fortnite" in title:
                        if self._afk_last_tick is not None:
                            self._afk_elapsed += max(0.0, now - self._afk_last_tick)
                        self._afk_last_tick = now
                    else:
                        self._afk_last_tick = None
                    total = calculate_afk_earnings(float(self.base_income.get()), self._afk_elapsed)
                    total_qi = income_to_qi(total, self.income_unit.get())
                    seconds = int(self._afk_elapsed)
                    clock = f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"
                    formatted_total = format_money(total_qi)
                    self.root.after(0, lambda c=clock, t=formatted_total: self.afk_earnings_status.set(
                        f"المدة داخل Fortnite: {c} | الدخل التقديري: {t}"
                    ))
                    if self._afk_elapsed - self._afk_last_sync_elapsed >= 10.0:
                        self._sync_afk_earnings(self._afk_elapsed)
                    # Persist the visible counter even when AFK is paused later.
                    self.state["afk_elapsed_seconds"] = self._afk_elapsed
                    self.state["afk_last_sync_elapsed"] = self._afk_last_sync_elapsed
                    save_state(self.state)
                except Exception as exc:
                    if not self._closing:
                        message = str(exc)[:80]
                        self.root.after(0, lambda e=message: self.afk_earnings_status.set(
                            f"تعذر تحديث الدخل: {e}"
                        ))
                self._afk_stop.wait(1.0)
        finally:
            if self._afk_elapsed > self._afk_last_sync_elapsed:
                self._sync_afk_earnings(self._afk_elapsed)

    def reset_afk_earnings(self):
        if self.afk_enabled:
            messagebox.showwarning("إعادة تعيين التجميع", "أوقف AFK أولاً حتى يتم حفظ آخر مبلغ قبل التصفير.")
            return
        if not self.license_key.get().strip():
            messagebox.showerror("إعادة تعيين التجميع", "فعّل الترخيص أولاً.")
            return
        if not messagebox.askyesno(
            "إعادة تعيين التجميع",
            "سيتم تصفير أرباحك الحالية فقط. إجمالي أرباحك منذ البداية سيبقى محفوظاً. هل تريد المتابعة؟"
        ):
            return
        self.afk_status.set("جاري حفظ آخر مبلغ ثم إعادة التعيين...")
        threading.Thread(target=self._reset_afk_earnings_worker, daemon=True).start()

    def _reset_afk_earnings_worker(self):
        try:
            earnings_thread = self._afk_earnings_thread
            if earnings_thread and earnings_thread.is_alive():
                earnings_thread.join(timeout=20)
                if earnings_thread.is_alive():
                    raise RuntimeError("تأخر إيقاف مزامنة الأرباح. حاول مرة أخرى.")
            if self._afk_pending_sync is not None or self._afk_elapsed > self._afk_last_sync_elapsed:
                if not self._sync_afk_earnings(self._afk_elapsed):
                    raise RuntimeError("تعذرت مزامنة آخر مبلغ؛ لم يتم تصفير التجميع.")
            result = post(
                "/api/money/reset",
                {"code": self.license_key.get().strip(), "device_id": device_id()},
                timeout=12
            )
            if isinstance(result, dict) and (
                result.get("ok") is False or result.get("success") is False
            ):
                raise RuntimeError(result.get("error", "Worker rejected the reset request."))
            self._afk_elapsed = 0.0
            self._afk_last_tick = None
            self._afk_last_sync_elapsed = 0.0
            self._afk_pending_sync = None
            self.state["afk_elapsed_seconds"] = 0.0
            self.state["afk_last_sync_elapsed"] = 0.0
            save_state(self.state)
            if not self._closing:
                self.root.after(0, lambda: self.afk_earnings_status.set(
                    "المدة داخل Fortnite: 00:00:00 | الدخل التقديري: 0.00 QI"
                ))
                self.root.after(0, lambda: self.afk_status.set(
                    "تم تصفير التجميع الحالي. الإجمالي منذ البداية لم يتغير."
                ))
        except Exception as exc:
            if not self._closing:
                message = str(exc)[:140]
                self.root.after(0, lambda msg=message: self.afk_status.set(
                    f"فشل إعادة التعيين: {msg}"
                ))

    def toggle_afk(self):
        if not self.license_key.get().strip():
            messagebox.showerror("AFK", "Activate your license first.")
            return
        if os.name != "nt":
            messagebox.showerror("AFK", "Automatic key input is supported on Windows only.")
            return
        if not self.afk_enabled:
            if self._afk_earnings_thread and self._afk_earnings_thread.is_alive():
                messagebox.showwarning("AFK", "انتظر حتى تنتهي مزامنة الجلسة السابقة.")
                return
            if self._afk_pending_sync is not None:
                messagebox.showwarning("AFK", "توجد أرباح لم تتم مزامنتها. تحقق من الاتصال ثم أعد المحاولة.")
                return
            if not self.save_afk_settings():
                return
            self.afk_enabled = True
            # Resuming AFK must not reset the collection counter.
            self._afk_last_tick = None
            self._afk_stop.clear()
            self._afk_earnings_thread = threading.Thread(target=self._afk_earnings_loop, daemon=True)
            self._afk_earnings_thread.start()
            try:
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001 | 0x00000002)
            except Exception:
                pass
            self._afk_thread = threading.Thread(target=self._afk_input_loop, daemon=True)
            self._afk_thread.start()
            self._afk_monitor_thread = threading.Thread(target=self._afk_monitor_loop, daemon=True)
            self._afk_monitor_thread.start()
            self.afk_button.config(text="STOP AFK  [F5]", bg=RED, fg="white")
            self.afk_status.set("AFK is ON.")
        else:
            self.afk_enabled = False
            self._afk_stop.set()
            try:
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            except Exception:
                pass
            self.afk_button.config(text="START AFK  [F5]", bg=GREEN, fg="#07110d")
            self.afk_status.set("AFK is OFF. Saving the final earnings interval...")


    def _fortnite_process_running(self):
        """Return True/False when tasklist can be checked, otherwise None."""
        try:
            completed = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            if completed.returncode != 0:
                return None
            output = (completed.stdout or "").lower()
            return "fortniteclient-win64-shipping" in output
        except Exception:
            return None

    def _send_afk_notification(self, event_type):
        """Queue one AFK state transition for the linked Discord account."""
        if not self._link_verified:
            self.root.after(0, lambda: self.afk_status.set(
                "AFK monitor: اربط حساب Discord لتلقي إشعارات الطرد والعودة."
            ))
            return False

        try:
            result = post("/api/afk/event", {
                "code": self.license_key.get().strip(),
                "device_id": device_id(),
                "event_id": uuid.uuid4().hex,
                "event_type": event_type
            }, timeout=12)
            if not isinstance(result, dict) or not result.get("ok"):
                raise RuntimeError(
                    result.get("error", "Worker did not accept the AFK notification.")
                    if isinstance(result, dict) else "Invalid Worker response."
                )
            labels = {
                "kick_detected": "تم اكتشاف خروج من المباراة. جارٍ متابعة حالة اللعبة...",
                "finding_server": "Finding Server | جارٍ العثور على الخادم...",
                "connected": "تم الاتصال بنجاح!",
                "reconnect_failed": "تعذر إعادة الاتصال."
            }
            message = labels.get(event_type, "تم إرسال إشعار AFK.")
            self.root.after(0, lambda msg=message: self.afk_status.set(msg))
            return True
        except Exception as exc:
            message = str(exc)[:110]
            self.root.after(0, lambda msg=message: self.afk_status.set(
                f"تعذر إرسال إشعار AFK إلى Discord: {msg}"
            ))
            return False

    def _afk_monitor_loop(self):
        """
        Monitor Fortnite only while AFK is enabled.
        It never presses Play, joins matchmaking, or attempts to reconnect.
        A loading -> lobby transition is treated as a possible kick.
        A return is confirmed only by non-lobby gameplay OCR plus repeated screen motion.
        """
        try:
            import mss
            import numpy as np
            from rapidocr_onnxruntime import RapidOCR
            import win32gui
            ocr = RapidOCR()
            sct = mss.mss()
        except Exception as exc:
            if not self._closing and not self._afk_stop.is_set():
                message = f"{type(exc).__name__}: {exc}"[:120]
                self.root.after(0, lambda msg=message: self.afk_status.set(
                    f"تعذر تشغيل مراقبة AFK: {msg}"
                ))
            return

        loading_seen_at = None
        kick_reported = False
        lobby_since = None
        motion_streak = 0
        previous_small = None
        had_game_process = False

        try:
            while not self._afk_stop.is_set() and not self._closing:
                try:
                    running = self._fortnite_process_running()

                    if running is False:
                        if had_game_process:
                            self._send_afk_notification("reconnect_failed")
                            had_game_process = False
                            loading_seen_at = None
                            kick_reported = False
                            lobby_since = None
                            motion_streak = 0
                            previous_small = None
                        self._afk_stop.wait(2.0)
                        continue

                    if running is None:
                        self._afk_stop.wait(2.0)
                        continue

                    had_game_process = True
                    hwnd = win32gui.GetForegroundWindow()
                    title = win32gui.GetWindowText(hwnd).lower()
                    if "fortnite" not in title:
                        self._afk_stop.wait(1.5)
                        continue

                    monitor = sct.monitors[1]
                    shot = sct.grab(monitor)
                    frame = Image.frombytes("RGB", shot.size, shot.rgb)

                    ocr_width = min(1280, frame.width)
                    ocr_height = max(1, int(frame.height * (ocr_width / frame.width)))
                    ocr_frame = frame.resize((ocr_width, ocr_height))
                    detections, _elapsed = ocr(np.array(ocr_frame))
                    recognized = " ".join(
                        str(item[1]) for item in (detections or [])
                        if len(item) > 1 and str(item[1]).strip()
                    )
                    screen_state = classify_afk_screen(recognized)
                    now = time.monotonic()

                    if screen_state == "loading":
                        loading_seen_at = now
                        if not kick_reported:
                            lobby_since = None
                            motion_streak = 0

                    elif (
                        screen_state == "lobby"
                        and loading_seen_at is not None
                        and now - loading_seen_at <= 300
                    ):
                        if not kick_reported:
                            kick_reported = True
                            lobby_since = now
                            self._send_afk_notification("kick_detected")
                            self._send_afk_notification("finding_server")

                    elif kick_reported and screen_state == "lobby":
                        if lobby_since is None:
                            lobby_since = now
                        elif now - lobby_since >= 600:
                            self._send_afk_notification("reconnect_failed")
                            kick_reported = False
                            loading_seen_at = None
                            lobby_since = None
                            motion_streak = 0
                            previous_small = None

                    elif kick_reported and screen_state == "gameplay":
                        small = frame.resize((160, 90)).convert("L")
                        if previous_small is not None:
                            difference = ImageChops.difference(small, previous_small)
                            motion_score = ImageStat.Stat(difference).mean[0]
                            if motion_score >= 5.0:
                                motion_streak += 1
                            else:
                                motion_streak = 0
                        previous_small = small

                        if motion_streak >= 2:
                            self._send_afk_notification("connected")
                            kick_reported = False
                            loading_seen_at = None
                            lobby_since = None
                            motion_streak = 0
                            previous_small = None

                    elif kick_reported:
                        motion_streak = 0

                    if loading_seen_at is not None and now - loading_seen_at > 300 and not kick_reported:
                        loading_seen_at = None

                except Exception as exc:
                    if not self._closing and not self._afk_stop.is_set():
                        message = str(exc)[:100]
                        self.root.after(0, lambda msg=message: self.afk_status.set(
                            f"AFK monitor warning: {msg}"
                        ))

                self._afk_stop.wait(2.5)
        finally:
            try:
                sct.close()
            except Exception:
                pass

    def _afk_input_loop(self):
        # Move in a fixed W -> A -> S -> D sequence; hold W for 0.35 seconds and keep the other movement timings unchanged.
        # P keeps its one-second cadence and ESC is tapped every ten seconds.
        # Always release a held movement key, including when AFK is stopped or an error occurs.
        key_codes = {"W": 0x57, "A": 0x41, "S": 0x53, "D": 0x44, "P": 0x50, "ESC": 0x1B}
        movement_sequence = ("W", "A", "S", "D")
        movement_index = 0
        movement_hold_seconds = {"W": 0.35, "A": 0.5, "S": 0.5, "D": 0.5}
        user32 = ctypes.windll.user32
        next_p = time.monotonic()
        next_esc = time.monotonic() + 10.0
        last_focus_notice = 0.0

        def tap_key(vk, duration=0.06):
            user32.keybd_event(vk, 0, 0, 0)
            try:
                self._afk_stop.wait(duration)
            finally:
                user32.keybd_event(vk, 0, 0x0002, 0)

        while not self._afk_stop.is_set():
            held_vk = None
            try:
                import win32gui
                hwnd = win32gui.GetForegroundWindow()
                title = win32gui.GetWindowText(hwnd).lower()
                if "fortnite" not in title:
                    now = time.monotonic()
                    if now - last_focus_notice > 2:
                        self.root.after(0, lambda: self.afk_status.set("AFK ON • Waiting for Fortnite to be the active window."))
                        last_focus_notice = now
                    self._afk_stop.wait(0.25)
                    next_p = time.monotonic()
                    continue

                self.root.after(0, lambda: self.afk_status.set("AFK is ON."))
                key = movement_sequence[movement_index]
                movement_index = (movement_index + 1) % len(movement_sequence)
                held_vk = key_codes[key]
                user32.keybd_event(held_vk, 0, 0, 0)
                try:
                    self._afk_stop.wait(movement_hold_seconds[key])
                finally:
                    user32.keybd_event(held_vk, 0, 0x0002, 0)
                    held_vk = None

                if self._afk_stop.is_set():
                    break

                # Auxiliary P/ESC taps happen between movement presses so they
                # cannot extend the movement-key hold duration.
                now = time.monotonic()
                if now >= next_p:
                    tap_key(key_codes["P"], 0.06)
                    next_p = time.monotonic() + 1.0
                if time.monotonic() >= next_esc:
                    tap_key(key_codes["ESC"], 0.06)
                    next_esc = time.monotonic() + 10.0
            except Exception as exc:
                if held_vk is not None:
                    try:
                        user32.keybd_event(held_vk, 0, 0x0002, 0)
                    except Exception:
                        pass
                self.root.after(0, lambda err=str(exc): self.afk_status.set("AFK input error: " + err[:100]))
                self._afk_stop.wait(1.0)

    def request_link(self):
        key, discord_id = self.license_key.get().strip(), self.discord_id.get().strip()
        if not key:
            messagebox.showerror("License", "Activate your license first.")
            return
        if not discord_id.isdigit() or not (17 <= len(discord_id) <= 20):
            messagebox.showerror("Discord ID", "Enter the numeric Discord user ID (17–20 digits).")
            return
        self.link_status.set("Sending verification request…")
        threading.Thread(target=self._link_worker, args=(key, discord_id), daemon=True).start()

    def _link_worker(self, key, discord_id):
        try:
            result = post("/api/link/request", {"code": key, "device_id": device_id(), "discord_user_id": discord_id})
            if result.get("linked"):
                self.state["discord_id"] = discord_id
                self._link_verified = True
                save_state(self.state)
                self.root.after(0, lambda: self.link_status.set("Discord already linked and verified."))
                self.root.after(0, self._show_gated_sections)
            elif result.get("request_id"):
                self.state["discord_id"] = discord_id
                self.state["link_request_id"] = result.get("request_id")
                save_state(self.state)
                self.root.after(0, lambda: self.link_status.set("Request sent. Waiting for bot approval…"))
                self._polling = True
                threading.Thread(target=self._poll_link_status, daemon=True).start()
            else:
                self.root.after(0, lambda: self.link_status.set("Request was not accepted by the server."))
                self.root.after(0, lambda: messagebox.showerror("Discord verification", result.get("error", "Request failed.")))
        except Exception as exc:
            self.root.after(0, lambda: self.link_status.set("Could not reach the verification service."))
            self.root.after(0, lambda err=str(exc): messagebox.showerror("Connection", f"Verification request failed.\n\n{err}"))

    def _poll_link_status(self):
        request_id, discord_id = self.state.get("link_request_id"), self.state.get("discord_id")
        if not request_id:
            return
        while self._polling:
            try:
                result = post("/api/link/request-status", {"code": self.state.get("license_key", ""), "device_id": device_id(), "request_id": request_id})
                status = str(result.get("status", "")).lower()
                if status in ("confirmed", "approved", "linked", "accepted") and result.get("linked"):
                    self._link_verified = True
                    self.root.after(0, lambda: self.link_status.set("Discord verified."))
                    self.root.after(0, self._show_gated_sections)
                    return
                if status in ("rejected", "expired", "denied"):
                    self._link_verified = False
                    self.root.after(0, lambda: self.link_status.set("Request rejected or expired. Submit a new request."))
                    return
            except Exception:
                pass
            time.sleep(4)

    def _refresh_link_state(self):
        # Enforce expiry locally; the automatic checker also validates with the server.
        cached_expiry = parse_expiry(self.state.get("expires_at"))
        current_key = self.license_key.get().strip()
        saved_key = str(self.state.get("license_key", "")).strip()
        if (not self._activation_in_progress and saved_key and current_key == saved_key
                and (not cached_expiry or cached_expiry <= datetime.now(timezone.utc))):
            self.root.after(0, self._handle_expired_subscription)
        # Radar cannot be started merely because an ID was typed; server approval is required.
        if self.radar_enabled and (not self.license_key.get().strip() or not self._link_verified):
            self.root.after(0, self.stop_radar)
        self.root.after(3000, self._refresh_link_state)

    def toggle_radar(self):
        if self.radar_enabled:
            self.stop_radar()
            return
        if not self.license_key.get().strip():
            messagebox.showerror("Radar locked", "Activate a valid license first.")
            return
        if not self._link_verified:
            messagebox.showerror("Radar locked", "Verify and approve your Discord link first.")
            return
        # Keep heavy OCR/ONNX imports off the Tkinter UI thread. Importing
        # RapidOCR synchronously can freeze the window and make it appear white.
        self._radar_stop.clear()
        self.radar_enabled = True
        self.radar_button.config(text="STOP RADAR", bg=RED, fg="white")
        self.radar_status.set("ON • Initializing OCR engine…")
        self._radar_thread = threading.Thread(target=self._radar_loop, daemon=True)
        self._radar_thread.start()

    def _radar_startup_failed(self, message):
        self.radar_enabled = False
        self.radar_button.config(text="START RADAR", bg=GREEN, fg="#07110d")
        self.radar_status.set(f"OFF • Radar startup error: {message[:140]}")

    def stop_radar(self):
        self.radar_enabled = False
        self._radar_stop.set()
        if not self._closing:
            self.radar_button.config(text="START RADAR", bg=GREEN, fg="#07110d")
            self.radar_status.set("OFF • Radar stopping. No new screen checks or uploads will start.")

    def _radar_loop(self):
        """Watch only the lower-center Spawn/Spawned notification on the primary display."""
        try:
            import mss
            from rapidocr_onnxruntime import RapidOCR
            from PIL import Image
            import numpy as np
            import win32gui
            import win32process
            ocr = RapidOCR()
        except Exception as exc:
            if not self._closing and not self._radar_stop.is_set():
                message = f"{type(exc).__name__}: {exc}"
                self.root.after(0, lambda msg=message: self._radar_startup_failed(msg))
            return

        try:
            sct = mss.mss()
        except Exception as exc:
            if not self._closing and not self._radar_stop.is_set():
                message = f"{type(exc).__name__}: {exc}"
                self.root.after(0, lambda msg=message: self._radar_startup_failed(msg))
            return

        try:
            while self.radar_enabled and not self._radar_stop.is_set() and not self._closing:
                try:
                    hwnd = win32gui.GetForegroundWindow()
                    title = win32gui.GetWindowText(hwnd).lower()
                    process_name = ""
                    try:
                        _thread_id, process_id = win32process.GetWindowThreadProcessId(hwnd)
                        process_handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, process_id)
                        if process_handle:
                            try:
                                image_path = ctypes.create_unicode_buffer(1024)
                                path_size = ctypes.wintypes.DWORD(len(image_path))
                                if ctypes.windll.kernel32.QueryFullProcessImageNameW(
                                    process_handle, 0, image_path, ctypes.byref(path_size)
                                ):
                                    process_name = os.path.basename(image_path.value).lower()
                            finally:
                                ctypes.windll.kernel32.CloseHandle(process_handle)
                    except Exception:
                        process_name = ""

                    is_fortnite = "fortnite" in title or "fortniteclient" in process_name
                    if not is_fortnite:
                        active_window = title[:45] or process_name or "unknown window"
                        if not self._closing and not self._radar_stop.is_set():
                            self.root.after(
                                0,
                                lambda name=active_window: self.radar_status.set(
                                    f"ON • Waiting for Fortnite. Active window: {name}"
                                )
                            )
                        self._radar_stop.wait(POLL_SECONDS)
                        continue

                    region = notification_region(sct.monitors[1])
                    shot = sct.grab(region)
                    roi = Image.frombytes("RGB", shot.size, shot.rgb)
                    detections, _elapsed = ocr(np.array(roi))
                    words = detections or []
                    recognized = " ".join(str(item[1]) for item in words if len(item) > 1)
                    normalized = re.sub(r"[^a-z0-9 ]", " ", recognized.lower())
                    normalized = re.sub(r"\s+", " ", normalized).strip()

                    now_status = time.time()
                    if now_status - self._last_ocr_status_at >= 2.0:
                        self._last_ocr_status_at = now_status
                        debug_text = re.sub(r"\s+", " ", recognized).strip()
                        if not debug_text:
                            debug_text = "no text recognized in notification area"
                        debug_text = debug_text[:75]
                        if not self._closing and not self._radar_stop.is_set():
                            self.root.after(0, lambda msg=debug_text: self.radar_status.set(f"ON • OCR reading: {msg}"))

                    if self._radar_stop.is_set() or self._closing:
                        break

                    if re.search(r"\bspawn(?:ed)?\b", normalized):
                        text_boxes = []
                        for item in words:
                            if len(item) < 2 or not str(item[1]).strip():
                                continue
                            pts = item[0]
                            xs = [float(p[0]) for p in pts]
                            ys = [float(p[1]) for p in pts]
                            text_boxes.append((min(xs), min(ys), max(xs), max(ys)))

                        if text_boxes:
                            x0 = max(0, int(min(b[0] for b in text_boxes) - 55))
                            y0 = max(0, int(min(b[1] for b in text_boxes) - 35))
                            x1 = min(roi.width, int(max(b[2] for b in text_boxes) + 55))
                            y1 = min(roi.height, int(max(b[3] for b in text_boxes) + 75))
                            crop = roi.crop((x0, y0, x1, y1))
                        else:
                            crop = roi

                        crop_text = recognized or "Spawned"
                        event_key = re.sub(r"\s+", " ", crop_text.lower()).strip()
                        now = time.time()
                        if event_key != self._last_event_key or now - self._last_event_at > EVENT_COOLDOWN_SECONDS:
                            if self._radar_stop.is_set() or self._closing:
                                break
                            buffer = io.BytesIO()
                            try:
                                crop.save(buffer, format="PNG")
                                image_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
                                if self._radar_stop.is_set() or self._closing:
                                    break
                                event_id = uuid.uuid4().hex
                                character_name = "Spawned: " + crop_text[:110] if crop_text.strip() else "Spawned"
                                result = post("/api/radar/event", {
                                    "code": self.license_key.get().strip(),
                                    "device_id": device_id(),
                                    "event_id": event_id,
                                    "character_name": character_name,
                                    "image_base64": image_b64
                                }, timeout=15)
                            finally:
                                buffer.close()

                            if not self._closing and not self._radar_stop.is_set():
                                if result.get("ok"):
                                    self._last_event_key, self._last_event_at = event_key, now
                                    self.root.after(0, lambda: self.radar_status.set(
                                        "ON • Server accepted event; Discord bot delivery is a separate step."
                                    ))
                                else:
                                    err = result.get("error", "Server rejected the event")
                                    self.root.after(0, lambda msg=err: self.radar_status.set(
                                        f"ON • Discord delivery failed: {msg[:90]}"
                                    ))
                except Exception as exc:
                    if not self._closing and not self._radar_stop.is_set():
                        self.root.after(0, lambda e=str(exc): self.radar_status.set(f"ON • Radar warning: {e[:100]}"))
                self._radar_stop.wait(POLL_SECONDS)
        finally:
            self.radar_enabled = False
            try:
                sct.close()
            except Exception:
                pass

    def close(self):
        if self._closing:
            return
        self._closing = True
        self._polling = False
        self._radar_stop.set()
        self.radar_enabled = False
        self._afk_stop.set()
        self.afk_enabled = False
        try:
            if os.name == "nt" and self._hotkey_thread_id:
                ctypes.windll.user32.PostThreadMessageW(self._hotkey_thread_id, 0x0012, 0, 0)  # WM_QUIT
        except Exception:
            pass
        try:
            if os.name == "nt":
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        except Exception:
            pass
        self.root.destroy()


def main():
    root = tk.Tk()
    app = AzToolApp(root)
    root.protocol("WM_DELETE_WINDOW", app.close)
    root.mainloop()


if __name__ == "__main__":
    main()