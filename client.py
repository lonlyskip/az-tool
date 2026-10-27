import os
import sys
import json
import time
import random
import hashlib
import threading
import tkinter as tk
from tkinter import messagebox, filedialog
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import ctypes
from ctypes import wintypes

APP_NAME = "AFK Tool"
# Replace this with your deployed license server URL before building the EXE.
LICENSE_SERVER = "https://YOUR-SERVER.example.com"
LICENSE_FILE = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "AFKTool", "license.json")

# Windows SendInput keyboard support
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
ULONG_PTR = wintypes.WPARAM

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]

class INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]

def press_key(vk, hold=0.08):
    down = INPUT(type=INPUT_KEYBOARD, union=INPUT_UNION(
        ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=0, time=0, dwExtraInfo=0)))
    up = INPUT(type=INPUT_KEYBOARD, union=INPUT_UNION(
        ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)))
    ctypes.windll.user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
    time.sleep(hold)
    ctypes.windll.user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))

VK = {"W": 0x57, "A": 0x41, "S": 0x53, "D": 0x44, "P": 0x50, "ESC": 0x1B}

def device_id():
    # Stable-enough local identifier for basic device binding; not a secret.
    raw = "|".join([
        os.getenv("COMPUTERNAME", ""),
        os.getenv("PROCESSOR_IDENTIFIER", ""),
        os.getenv("USERNAME", "")
    ])
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()

def api_post(path, payload, timeout=8):
    data = json.dumps(payload).encode("utf-8")
    req = Request(LICENSE_SERVER.rstrip("/") + path, data=data,
                  headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def load_saved_key():
    try:
        with open(LICENSE_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("key", "")
    except Exception:
        return ""

def save_key(key):
    os.makedirs(os.path.dirname(LICENSE_FILE), exist_ok=True)
    with open(LICENSE_FILE, "w", encoding="utf-8") as f:
        json.dump({"key": key}, f)

class App:
    def __init__(self, root):
        self.root = root
        root.title(APP_NAME)
        root.geometry("470x540")
        root.configure(bg="#1b1b1f")
        root.resizable(False, False)
        self.running = threading.Event()
        self.worker = None
        self.image_path = ""
        self.status = tk.StringVar(value="Not activated")
        self.key_var = tk.StringVar(value=load_saved_key())
        self.p_interval = tk.StringVar(value="12")
        self.action_interval = tk.StringVar(value="1.5")

        tk.Label(root, text="AFK TOOL", font=("Segoe UI", 20, "bold"),
                 bg="#1b1b1f", fg="#eaeaea").pack(pady=(18, 4))
        tk.Label(root, text="Keyboard automation • licensed edition",
                 font=("Segoe UI", 9), bg="#1b1b1f", fg="#9a9aa5").pack(pady=(0, 12))

        card = tk.Frame(root, bg="#26262c", padx=16, pady=14)
        card.pack(fill="x", padx=20, pady=6)
        tk.Label(card, text="LICENSE KEY", bg="#26262c", fg="#eaeaea",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        row = tk.Frame(card, bg="#26262c")
        row.pack(fill="x", pady=(6, 4))
        tk.Entry(row, textvariable=self.key_var, bg="#32323a", fg="#eaeaea",
                 insertbackground="#eaeaea", relief="flat").pack(side="left", fill="x", expand=True, ipady=8)
        tk.Button(row, text="Activate", command=self.activate, bg="#5b8cff",
                  fg="white", relief="flat", padx=12, pady=7).pack(side="left", padx=(8, 0))
        tk.Label(card, textvariable=self.status, bg="#26262c", fg="#3ddc84",
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 0))

        settings = tk.Frame(root, bg="#26262c", padx=16, pady=12)
        settings.pack(fill="x", padx=20, pady=8)
        tk.Label(settings, text="SETTINGS", bg="#26262c", fg="#eaeaea",
                 font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", columnspan=2, pady=(0, 8))
        tk.Label(settings, text="W/A/S/D action interval (seconds)", bg="#26262c",
                 fg="#eaeaea").grid(row=1, column=0, sticky="w", pady=4)
        tk.Entry(settings, textvariable=self.action_interval, width=9, bg="#32323a",
                 fg="#eaeaea", insertbackground="#eaeaea", relief="flat").grid(row=1, column=1, sticky="e")
        tk.Label(settings, text="P key interval (seconds)", bg="#26262c",
                 fg="#eaeaea").grid(row=2, column=0, sticky="w", pady=4)
        tk.Entry(settings, textvariable=self.p_interval, width=9, bg="#32323a",
                 fg="#eaeaea", insertbackground="#eaeaea", relief="flat").grid(row=2, column=1, sticky="e")
        tk.Label(settings, text="P interval is a timer, not lobby detection.",
                 bg="#26262c", fg="#ffb454", font=("Segoe UI", 8)).grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))

        tk.Button(root, text="Choose Your Image (optional)", command=self.choose_image,
                  bg="#32323a", fg="#eaeaea", relief="flat", pady=8).pack(fill="x", padx=20, pady=(2, 8))
        buttons = tk.Frame(root, bg="#1b1b1f")
        buttons.pack(fill="x", padx=20, pady=6)
        tk.Button(buttons, text="START", command=self.start, bg="#3ddc84", fg="#111111",
                  relief="flat", font=("Segoe UI", 11, "bold"), pady=12).pack(side="left", fill="x", expand=True, padx=(0, 6))
        tk.Button(buttons, text="STOP", command=self.stop, bg="#ff5c5c", fg="white",
                  relief="flat", font=("Segoe UI", 11, "bold"), pady=12).pack(side="left", fill="x", expand=True, padx=(6, 0))
        tk.Label(root, text="Use only where automation is permitted. Focus the target app before Start.",
                 bg="#1b1b1f", fg="#9a9aa5", font=("Segoe UI", 8), wraplength=420).pack(pady=10)

    def activate(self):
        key = self.key_var.get().strip()
        if not key:
            messagebox.showerror("Activation", "Enter a license key.")
            return
        try:
            result = api_post("/api/activate", {"key": key, "device_id": device_id()})
            if result.get("ok"):
                save_key(key)
                self.status.set("Activated")
                messagebox.showinfo("Activation", result.get("message", "Activation successful."))
            else:
                messagebox.showerror("Activation", result.get("message", "Activation failed."))
        except Exception as e:
            messagebox.showerror("Activation error",
                "Could not reach the license server. Check the server URL and internet connection.\n\n" + str(e))

    def licensed(self):
        key = self.key_var.get().strip()
        if not key:
            return False
        try:
            result = api_post("/api/validate", {"key": key, "device_id": device_id()})
            if result.get("ok"):
                self.status.set("Activated • license valid")
                return True
            self.status.set("License invalid or expired")
            return False
        except Exception:
            self.status.set("License server unavailable")
            return False

    def choose_image(self):
        path = filedialog.askopenfilename(title="Choose an image",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.bmp"), ("All files", "*.*")])
        if path:
            self.image_path = path
            messagebox.showinfo("Image", "Image selected. Add it to the UI layout if you want it displayed.")

    def start(self):
        if self.running.is_set():
            return
        if not self.licensed():
            messagebox.showerror("License", "Activate with a valid license before starting.")
            return
        try:
            action_interval = float(self.action_interval.get())
            p_interval = float(self.p_interval.get())
            if action_interval < 0.2 or p_interval < 2:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Settings", "Use action interval >= 0.2 seconds and P interval >= 2 seconds.")
            return
        self.running.set()
        self.worker = threading.Thread(target=self.run_loop, args=(action_interval, p_interval), daemon=True)
        self.worker.start()
        self.status.set("Running")

    def stop(self):
        self.running.clear()
        self.status.set("Stopped")

    def run_loop(self, action_interval, p_interval):
        last_p = time.monotonic()
        last_validate = time.monotonic()
        keys = ["W", "A", "S", "D"]
        while self.running.is_set():
            now = time.monotonic()
            if now - last_validate >= 60:
                if not self.licensed():
                    self.running.clear()
                    break
                last_validate = now
            key = random.choice(keys)
            press_key(VK[key], random.uniform(0.04, 0.10))
            if not self.running.is_set():
                break
            if now - last_p >= p_interval:
                press_key(VK["P"], 0.08)
                last_p = time.monotonic()
            self.running.wait if False else None
            time.sleep(action_interval)
        self.root.after(0, lambda: self.status.set("Stopped"))

def main():
    if os.name != "nt":
        print("This starter client is intended for Windows.")
        return
    root = tk.Tk()
    App(root)
    root.mainloop()

if __name__ == "__main__":
    main()
