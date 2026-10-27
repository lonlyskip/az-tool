# az Tool

Windows desktop client for the az Tool licensing service.

## Run (Windows)

Install Python 3.11+, install the Python dependencies, and install the **Tesseract OCR Windows application** separately. Make sure `tesseract.exe` is on PATH (or configure `pytesseract.pytesseract.tesseract_cmd` in `az_tool.py`).

```cmd
py -m pip install -r requirements.txt
py az_tool.py
```

## Current implementation

- Dark English desktop UI.
- License activation against the deployed Cloudflare Worker.
- Discord-link request and polling for approval.
- Spawn Radar toggle, gated on license activation and Discord-link approval.
- Monitors only while Fortnite is the foreground window.
- OCR scans a bottom-centre region for “Ascended Brainrot Spawned” and saves a crop around the detected notification to `%APPDATA%\az Tool\captures`.
- Duplicate suppression uses the recognized notification text and a short cooldown, so later distinct events can still be detected.
- Radar can be stopped from the UI.

## Important status: Discord delivery is not wired end-to-end yet

The deployed Worker/Bot currently does not expose a verified image-event upload + bot-DM delivery route. This build **only saves the cropped notification locally** and reports that status in the UI; it does not claim to DM screenshots. To complete that safely, the Worker must accept authenticated event uploads after validating license/device/link status, and the bot must deliver the image to the linked Discord ID. Do not put bot tokens or admin secrets in this desktop client.

## Build an EXE

```cmd
py -m pip install pyinstaller
py -m PyInstaller --onefile --windowed --name "az Tool" az_tool.py
```

Tesseract OCR is a separate Windows dependency and is not bundled by that command. Test on the target PC before distributing the EXE.

## Security notes

- Never put `ADMIN_TOKEN`, Discord bot tokens, or Cloudflare secrets in the client or repository.
- Client-side device IDs are not strong anti-tamper protection by themselves.
- All production requests must use HTTPS.
