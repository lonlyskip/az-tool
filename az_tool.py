import hashlib
import json
import os
import threading
import time
import tkinter as tk
from tkinter import messagebox
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

APP_NAME = "az Tool"
LICENSE_SERVER = "https://az-tool-license.a-abdilaziz-a.workers.dev"
APP_DIR = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "az Tool")
STATE_FILE = os.path.join(APP_DIR, "state.json")

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
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


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
        self.root.geometry("620x690")
        self.root.minsize(580, 650)
        self.root.configure(bg=BG)
        self.state = load_state()
        self.license_key = tk.StringVar(value=self.state.get("license_key", ""))
        self.discord_id = tk.StringVar(value=self.state.get("discord_id", ""))
        self.status = tk.StringVar(value="Not activated")
        self.link_status = tk.StringVar(value="Discord account not linked")
        self.expiry = tk.StringVar(value="—")
        self._polling = False
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
        return tk.Entry(parent, textvariable=variable, show=show, bg=PANEL_2, fg=TEXT,
                        insertbackground=TEXT, relief="flat", font=("Segoe UI", 10),
                        highlightthickness=1, highlightbackground="#30394d",
                        highlightcolor=ACCENT)

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
        self.label(license_card, "Status: " + "", MUTED, 9).pack_forget()
        tk.Label(license_card, textvariable=self.status, bg=PANEL, fg=GREEN,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(10, 0))
        expiry_row = tk.Frame(license_card, bg=PANEL)
        expiry_row.pack(fill="x", pady=(5, 0))
        self.label(expiry_row, "Subscription", MUTED, 9).pack(side="left")
        tk.Label(expiry_row, textvariable=self.expiry, bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 9, "bold")).pack(side="right")

        discord_card = self.card(self.root, "02  /  Discord verification",
                                 "Enter your Discord user ID, then approve the bot's DM request.")
        self.entry(discord_card, self.discord_id).pack(fill="x", ipady=10)
        self.button(discord_card, "VERIFY & SAVE", self.request_link, color="#29314a").pack(anchor="e", pady=(10, 0))
        tk.Label(discord_card, textvariable=self.link_status, bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9), wraplength=520, justify="left").pack(anchor="w", pady=(10, 0))

        radar_card = self.card(self.root, "03  /  Radar", "Radar stays locked until license and Discord verification are confirmed.")
        self.radar_button = self.button(radar_card, "RADAR NOT READY", self.radar_unavailable, color="#242a39", fg=MUTED)
        self.radar_button.pack(fill="x")
        self.label(radar_card, "Screen detection and screenshot delivery are not enabled in this build yet.",
                   MUTED, 9).pack(anchor="w", pady=(10, 0))

        footer = tk.Frame(self.root, bg=BG)
        footer.pack(fill="x", padx=28, pady=(10, 18))
        self.label(footer, "Secure connection • License checks use the az Tool Worker API", MUTED, 8).pack(anchor="w")
        if self.license_key.get().strip():
            self.status.set("Saved key loaded — validate before use")

    def activate(self):
        key = self.license_key.get().strip()
        if not key:
            messagebox.showerror("License", "Enter your license key first.")
            return
        self.status.set("Checking license…")
        threading.Thread(target=self._activate_worker, args=(key,), daemon=True).start()

    def _activate_worker(self, key):
        try:
            result = post("/api/activate", {"key": key, "device_id": device_id()})
            if result.get("ok"):
                self.state["license_key"] = key
                save_state(self.state)
                self.root.after(0, lambda: self.status.set("Activated • license accepted"))
                self.root.after(0, lambda: self.expiry.set(str(result.get("expires_at") or result.get("expires") or "Check account")))
            else:
                self.root.after(0, lambda: self.status.set("Activation failed"))
                self.root.after(0, lambda: messagebox.showerror("License", result.get("message", "Activation was rejected.")))
        except Exception as exc:
            self.root.after(0, lambda: self.status.set("Server unavailable"))
            self.root.after(0, lambda: messagebox.showerror("Connection", f"Could not contact the license server.\n\n{exc}"))

    def request_link(self):
        key = self.license_key.get().strip()
        discord_id = self.discord_id.get().strip()
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
            result = post("/api/link/request", {
                "key": key, "device_id": device_id(), "discord_id": discord_id
            })
            if result.get("ok"):
                self.state["discord_id"] = discord_id
                self.state["link_request_id"] = result.get("request_id") or result.get("id")
                save_state(self.state)
                self.root.after(0, lambda: self.link_status.set("Request sent. Check Discord and approve the bot's message."))
                self._polling = True
                threading.Thread(target=self._poll_link_status, daemon=True).start()
            else:
                self.root.after(0, lambda: self.link_status.set("Request was not accepted by the server."))
                self.root.after(0, lambda: messagebox.showerror("Discord verification", result.get("message", "Request failed.")))
        except Exception as exc:
            self.root.after(0, lambda: self.link_status.set("Could not reach the verification service."))
            self.root.after(0, lambda: messagebox.showerror("Connection", f"Verification request failed.\n\n{exc}"))

    def _poll_link_status(self):
        request_id = self.state.get("link_request_id")
        discord_id = self.state.get("discord_id")
        if not request_id:
            return
        while self._polling:
            try:
                result = post("/api/link/request-status", {"request_id": request_id, "discord_id": discord_id})
                status = str(result.get("status", "")).lower()
                if status in ("confirmed", "approved", "linked", "accepted"):
                    self.root.after(0, lambda: self.link_status.set("Discord verified."))
                    return
                if status in ("rejected", "expired", "denied"):
                    self.root.after(0, lambda: self.link_status.set("Request rejected or expired. Submit a new request if needed."))
                    return
            except Exception:
                pass
            time.sleep(4)

    def radar_unavailable(self):
        messagebox.showinfo("Radar", "Radar is intentionally disabled until the screen detector and secure screenshot-delivery flow are implemented and tested.")

    def close(self):
        self._polling = False
        self.root.destroy()


def main():
    root = tk.Tk()
    app = AzToolApp(root)
    root.protocol("WM_DELETE_WINDOW", app.close)
    root.mainloop()


if __name__ == "__main__":
    main()
