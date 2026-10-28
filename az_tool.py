import hashlib
import json
import os
import sys
import io
import base64
import uuid
import re
import random
import threading
import time
import tkinter as tk
import ctypes
from tkinter import messagebox
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from datetime import datetime, timezone

APP_NAME = "az tool"
LICENSE_SERVER = "https://az-tool-license.a-abdilaziz-a.workers.dev"
APP_DIR = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "az tool")
STATE_FILE = os.path.join(APP_DIR, "state.json")
# The requested monitor setup is 1920x1080. Region is bottom-centre, above inventory.
REGION = {"left": 460, "top": 690, "width": 1000, "height": 220}
POLL_SECONDS = 0.8
EVENT_COOLDOWN_SECONDS = 3.0

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
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, ValueError):
        return {}


def save_state(state):
    os.makedirs(APP_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump(state, file)


class AzToolApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("620x720")
        self.root.minsize(580, 680)
        self.root.configure(bg=BG)
        icon_path = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "assets", "az-tool-icon.ico")
        # PyInstaller bundles the same feather icon for the executable and the app window/taskbar.
        if not os.path.exists(icon_path):
            icon_path = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "az-tool-icon.ico")
        try:
            self.root.iconbitmap(icon_path)
        except (tk.TclError, OSError):
            pass
        self.state = load_state()
        self.license_key = tk.StringVar(value=self.state.get("license_key", ""))
        self.discord_id = tk.StringVar(value=self.state.get("discord_id", ""))
        self.status = tk.StringVar(value="Not activated")
        self.link_status = tk.StringVar(value="Discord account not linked")
        self.expiry = tk.StringVar(value="—")
        self.radar_status = tk.StringVar(value="OFF • Waiting for license and Discord verification")
        self.radar_enabled = False
        self._polling = False
        self._radar_thread = None
        self._last_event_key = None
        self._last_event_at = 0.0
        self._last_license_check = 0.0
        self._link_verified = False
        self._discord_skipped = bool(self.state.get('discord_skipped', False))
        self.afk_enabled = False
        self._afk_stop = threading.Event()
        self._afk_thread = None
        self._build()

    def label(self, parent, text, color=TEXT, size=10, bold=False):
        return tk.Label(parent, text=text, bg=parent["bg"], fg=color,
                        font=("Segoe UI", size, "bold" if bold else "normal"))

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

    def _build(self):
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=28, pady=(22, 8))
        self.label(header, "az Tool", size=25, bold=True).pack(anchor="w")
        self.label(header, "LICENSED DESKTOP CLIENT", MUTED, 9, True).pack(anchor="w", pady=(2, 0))

        license_card = self.card(self.root, "01  /  License", "Activate your key on this device.")
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

        self.discord_card = self.card(self.gated_frame, "02  /  Discord verification", "Enter your Discord user ID, then approve the bot's verification request.")
        discord_card = self.discord_card
        self.entry(discord_card, self.discord_id).pack(fill="x", ipady=10)
        actions = tk.Frame(discord_card, bg=PANEL)
        actions.pack(fill="x", pady=(10, 0))
        self.button(actions, "VERIFY & SAVE", self.request_link, color="#29314a").pack(side="left")
        self.button(actions, "SKIP FOR NOW", self.skip_discord, color="#303747").pack(side="right")
        tk.Label(discord_card, textvariable=self.link_status, bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9), wraplength=520, justify="left").pack(anchor="w", pady=(10, 0))

        self.afk_card = self.card(self.gated_frame, "03  /  AFK", "F5 toggles AFK mode")
        self.afk_button = self.button(self.afk_card, "START AFK  [F5]", self.toggle_afk, color=GREEN, fg="#07110d")
        self.afk_button.pack(fill="x")
        self.afk_status = tk.StringVar(value="AFK is OFF.")
        tk.Label(self.afk_card, textvariable=self.afk_status, bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(8, 0))

        self.radar_card = self.card(self.gated_frame, "04  /  Spawn Radar", "Fortnite • Go Up for Brainrot • 1920 × 1080")
        radar_card = self.radar_card
        self.radar_button = self.button(radar_card, "START RADAR", self.toggle_radar, color=GREEN, fg="#07110d")
        self.radar_button.pack(fill="x")
        tk.Label(radar_card, textvariable=self.radar_status, bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9), wraplength=520, justify="left").pack(anchor="w", pady=(10, 0))
        self.label(radar_card, "Detects Ascended Brainrot Spawned and Forbidden Brainrot Spawned.", MUTED, 9).pack(anchor="w", pady=(5, 0))

        self.boost_card = self.card(self.gated_frame, "05  /  Optional boosts", "Optional system adjustments")
        self.fps_var = tk.BooleanVar(value=False)
        self.ping_var = tk.BooleanVar(value=False)
        tk.Checkbutton(self.boost_card, text="FPS boost", variable=self.fps_var, command=self.toggle_fps_boost,
                       bg=PANEL, fg=TEXT, selectcolor=PANEL_2, activebackground=PANEL,
                       activeforeground=TEXT, font=("Segoe UI", 10)).pack(anchor="w", pady=3)
        tk.Checkbutton(self.boost_card, text="Ping boost", variable=self.ping_var, command=self.toggle_ping_boost,
                       bg=PANEL, fg=TEXT, selectcolor=PANEL_2, activebackground=PANEL,
                       activeforeground=TEXT, font=("Segoe UI", 10)).pack(anchor="w", pady=3)
        self.boost_status = tk.StringVar(value="Boosts are OFF.")
        tk.Label(self.boost_card, textvariable=self.boost_status, bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9), wraplength=520, justify="left").pack(anchor="w", pady=(6, 0))

        self.discord_card.pack_forget()
        self.afk_card.pack_forget()
        self.radar_card.pack_forget()
        self.boost_card.pack_forget()
        self.root.bind("<F5>", lambda event: self.toggle_afk())

        footer = tk.Frame(self.root, bg=BG)
        footer.pack(fill="x", padx=28, pady=(10, 18))
        self.label(footer, "License validation • Foreground Fortnite window required • No full-screen upload", MUTED, 8).pack(anchor="w")
        if self.license_key.get().strip():
            self.status.set("Saved key loaded — activate to validate")
        self.root.after(1000, self._refresh_link_state)

    def _show_gated_sections(self):
        if not self._link_verified and not self._discord_skipped:
            if not self.discord_card.winfo_manager():
                self.discord_card.pack(fill="x", padx=24, pady=8)
        else:
            self.discord_card.pack_forget()
        for card in (self.afk_card, self.radar_card, self.boost_card):
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
        self.radar_card.pack_forget()
        self.boost_card.pack_forget()

    def activate(self):
        key = self.license_key.get().strip()
        if not key:
            messagebox.showerror("License", "Enter your license key first.")
            return
        self.status.set("Checking license…")
        threading.Thread(target=self._activate_worker, args=(key,), daemon=True).start()

    def _activate_worker(self, key):
        try:
            result = post("/api/activate", {"code": key, "device_id": device_id()})
            if result.get("valid") is True or result.get("success") is True or result.get("activated") is True:
                self.state["license_key"] = key
                save_state(self.state)
                self.root.after(0, lambda: self.status.set("Activated • license accepted"))
                self.root.after(0, lambda: self.expiry.set(str(result.get("expires_at") or result.get("expires") or "Active")))
                self.root.after(0, self._show_gated_sections)
            else:
                self.root.after(0, lambda: self.status.set("Activation failed"))
                self.root.after(0, self._hide_gated_sections)
                self.root.after(0, lambda: messagebox.showerror("فشل التفعيل", arabic_error(result.get("error", "Activation was rejected."))))
        except Exception as exc:
            self.root.after(0, lambda: self.status.set("Server unavailable"))
            self.root.after(0, self._hide_gated_sections)
            self.root.after(0, lambda err=str(exc): messagebox.showerror("Connection", f"Could not contact the license server.\n\n{err}"))

    def skip_discord(self):
        self._discord_skipped = True
        self.state["discord_skipped"] = True
        save_state(self.state)
        self._show_gated_sections()

    def toggle_afk(self):
        if not self.license_key.get().strip():
            messagebox.showerror("AFK", "Activate your license first.")
            return
        if os.name != "nt":
            messagebox.showerror("AFK", "Automatic key input is supported on Windows only.")
            return

        self.afk_enabled = not self.afk_enabled
        if self.afk_enabled:
            self._afk_stop.clear()
            try:
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001 | 0x00000002)
            except Exception:
                pass
            self._afk_thread = threading.Thread(target=self._afk_input_loop, daemon=True)
            self._afk_thread.start()
            self.afk_button.config(text="STOP AFK  [F5]", bg=RED, fg="white")
            self.afk_status.set("AFK ON • Random W/A/S/D/P/Esc taps while Fortnite is focused.")
        else:
            self._afk_stop.set()
            try:
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            except Exception:
                pass
            self.afk_button.config(text="START AFK  [F5]", bg=GREEN, fg="#07110d")
            self.afk_status.set("AFK is OFF.")

    def _afk_input_loop(self):
        # Send short, randomized key taps only while the Fortnite window is foreground.
        key_codes = {"W": 0x57, "A": 0x41, "S": 0x53, "D": 0x44, "P": 0x50, "ESC": 0x1B}
        user32 = ctypes.windll.user32
        while not self._afk_stop.is_set():
            try:
                import win32gui
                hwnd = win32gui.GetForegroundWindow()
                title = win32gui.GetWindowText(hwnd).lower()
                if "fortnite" in title:
                    key = random.choice(("W", "A", "S", "D", "P", "ESC"))
                    vk = key_codes[key]
                    user32.keybd_event(vk, 0, 0, 0)
                    self._afk_stop.wait(random.uniform(0.12, 0.35))
                    user32.keybd_event(vk, 0, 0x0002, 0)
                    self._afk_stop.wait(random.uniform(2.0, 6.0))
                else:
                    self._afk_stop.wait(1.0)
            except Exception as exc:
                self.root.after(0, lambda err=str(exc): self.afk_status.set("AFK input error: " + err[:100]))
                self._afk_stop.wait(2.0)
    
    def toggle_fps_boost(self):
        if self.fps_var.get():
            try:
                import win32gui, win32process, win32api, win32con
                hwnd = win32gui.FindWindow(None, "Fortnite")
                if not hwnd:
                    hwnd = win32gui.GetForegroundWindow()
                    if "fortnite" not in win32gui.GetWindowText(hwnd).lower():
                        raise RuntimeError("Open Fortnite first.")
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                handle = win32api.OpenProcess(win32con.PROCESS_SET_INFORMATION, False, pid)
                try:
                    win32process.SetPriorityClass(handle, win32process.HIGH_PRIORITY_CLASS)
                finally:
                    win32api.CloseHandle(handle)
                self.boost_status.set("FPS boost ON • Fortnite priority set to High; performance may vary.")
            except Exception as exc:
                self.fps_var.set(False)
                self.boost_status.set("FPS boost couldn't be applied: " + str(exc)[:90])
        else:
            try:
                import win32gui, win32process, win32api, win32con
                hwnd = win32gui.FindWindow(None, "Fortnite") or win32gui.GetForegroundWindow()
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                handle = win32api.OpenProcess(win32con.PROCESS_SET_INFORMATION, False, pid)
                try:
                    win32process.SetPriorityClass(handle, win32process.NORMAL_PRIORITY_CLASS)
                finally:
                    win32api.CloseHandle(handle)
            except Exception:
                pass
            self.boost_status.set("FPS boost OFF • Normal priority requested.")

    def toggle_ping_boost(self):
        if self.ping_var.get():
            self.ping_var.set(False)
            self.boost_status.set("Ping boost not applied: no safe local setting can guarantee lower game-server latency.")
            messagebox.showinfo("Ping boost", "البنق يعتمد على مسار الشبكة وسيرفر اللعبة. ما راح أغيّر إعدادات شبكة حساسة بدون ضمان أو طريقة استرجاع آمنة.")
        else:
            self.boost_status.set("Ping boost OFF.")

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
        try:
            import mss, rapidocr_onnxruntime
            from PIL import Image
            import numpy
        except ImportError:
            messagebox.showerror("Missing components", "This build is missing bundled radar components. Please reinstall the complete az Tool application build.")
            return
        self.radar_enabled = True
        self.radar_button.config(text="STOP RADAR", bg=RED, fg="white")
        self.radar_status.set("ON • Waiting for Fortnite notification…")
        self._radar_thread = threading.Thread(target=self._radar_loop, daemon=True)
        self._radar_thread.start()

    def stop_radar(self):
        self.radar_enabled = False
        self.radar_button.config(text="START RADAR", bg=GREEN, fg="#07110d")
        self.radar_status.set("OFF • Radar stopped. No screen monitoring is active.")

    def _radar_loop(self):
        try:
            import mss
            from rapidocr_onnxruntime import RapidOCR
            from PIL import Image
            import numpy as np
            import win32gui
            ocr = RapidOCR()
        except ImportError:
            self.root.after(0, self.stop_radar)
            return
        while self.radar_enabled:
            try:
                hwnd = win32gui.GetForegroundWindow()
                title = win32gui.GetWindowText(hwnd).lower()
                if "fortnite" not in title:
                    self.root.after(0, lambda: self.radar_status.set("ON • Waiting for Fortnite to be the active window…"))
                    time.sleep(POLL_SECONDS)
                    continue
                with mss.mss() as sct:
                    shot = sct.grab(REGION)
                    image = Image.frombytes("RGB", shot.size, shot.rgb)
                detections, _elapsed = ocr(np.array(image))
                words = detections or []
                recognized = " ".join(str(item[1]) for item in words if len(item) > 1)
                normalized = re.sub(r"[^a-z0-9 ]", " ", recognized.lower())
                normalized = re.sub(r"\s+", " ", normalized).strip()
                phrase_found = (
                    ("brainrot" in normalized and "spawned" in normalized and ("ascended" in normalized or "forbidden" in normalized))
                )
                if phrase_found:
                    phrase_boxes = []
                    for item in words:
                        if len(item) < 2:
                            continue
                        word = str(item[1]).strip().lower()
                        if any(k in word for k in ("ascended", "forbidden", "brainrot", "spawned")):
                            pts = item[0]
                            xs = [float(p[0]) for p in pts]
                            ys = [float(p[1]) for p in pts]
                            phrase_boxes.append((min(xs), min(ys), max(xs), max(ys)))
                    if phrase_boxes:
                        x0 = max(0, int(min(b[0] for b in phrase_boxes) - 45))
                        y0 = max(0, int(min(b[1] for b in phrase_boxes) - 20))
                        x1 = min(image.width, int(max(b[2] for b in phrase_boxes) + 45))
                        y1 = min(image.height, int(max(b[3] for b in phrase_boxes) + 100))
                        crop = image.crop((x0, y0, x1, y1))
                    else:
                        crop = image
                    crop_detections, _ = ocr(np.array(crop))
                    crop_text = " ".join(str(item[1]) for item in (crop_detections or []) if len(item) > 1)
                    event_key = re.sub(r"\s+", " ", crop_text.lower()).strip()
                    now = time.time()
                    if event_key and (event_key != self._last_event_key or now - self._last_event_at > EVENT_COOLDOWN_SECONDS):
                        # Encode the crop in memory only; never write a screenshot file to disk.
                        buffer = io.BytesIO()
                        crop.save(buffer, format="PNG")
                        image_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
                        event_id = uuid.uuid4().hex
                        character_name = crop_text[:120] or "Ascended Brainrot"
                        result = post("/api/radar/event", {
                            "code": self.license_key.get().strip(),
                            "device_id": device_id(),
                            "event_id": event_id,
                            "character_name": character_name,
                            "image_base64": image_b64
                        }, timeout=15)
                        if result.get("ok"):
                            self._last_event_key, self._last_event_at = event_key, now
                            self.root.after(0, lambda: self.radar_status.set("ON • Spawn detected and sent to your linked Discord account."))
                        else:
                            err = result.get("error", "Server rejected the event")
                            self.root.after(0, lambda msg=err: self.radar_status.set(f"ON • Discord delivery failed: {msg[:90]}"))
                        buffer.close()
                        time.sleep(EVENT_COOLDOWN_SECONDS)
                else:
                    self.root.after(0, lambda: self.radar_status.set("ON • Watching Fortnite notification area…"))
            except Exception as exc:
                self.root.after(0, lambda e=str(exc): self.radar_status.set(f"ON • Radar warning: {e[:100]}"))
            time.sleep(POLL_SECONDS)

    def close(self):
        self._polling = False
        self.radar_enabled = False
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
