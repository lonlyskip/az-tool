# az Tool

Windows desktop client for the az Tool licensing service.

## Run locally (Windows)

Install Python 3.11+, then run:

```cmd
py -m pip install -r requirements.txt
py az_tool.py
```

The OCR engine is provided by `rapidocr-onnxruntime`; a separate Tesseract install is not required.

## Build a Windows EXE

A GitHub Actions workflow builds the app when `az_tool.py`, `requirements.txt`, or the workflow changes on branch `az-tool-rebuild`.

1. Open the repository on GitHub and select **Actions**.
2. Open **Build az Tool for Windows** and select the latest successful run.
3. Under **Artifacts**, download `az-Tool-Windows` and extract `az Tool.exe`.

You can also build locally:

```cmd
py -m pip install pyinstaller
pyinstaller --noconfirm --clean --onefile --windowed --name "az Tool" --collect-all rapidocr_onnxruntime --collect-all onnxruntime --hidden-import win32timezone az_tool.py
```

The executable is written to `dist\az Tool.exe`.

## Implemented

- Dark desktop interface named **az Tool** with the **Licensed Edition** concept.
- License activation and server-side validation.
- Discord link request and approval status polling.
- START/STOP radar controls; the radar is gated behind license and Discord verification.
- OCR detection for the phrase “Ascended Brainrot Spawned”.
- Captures only the configured notification region while Fortnite is the foreground window.
- Encodes the cropped notification in memory and uploads it to the Worker at `/api/radar/event`; it does not intentionally save screenshot files to disk.
- Worker queue integration is expected at `/bot/radar-events` and `/bot/radar-delivered`, with the Discord bot responsible for sending the image DM.

## Important test notes

- The detection region is configured for a 1920×1080 display. Other resolutions or UI scales need a region adjustment.
- OCR may need tuning against a real in-game notification. The app has not been verified against a live Fortnite event in this repository workflow; test with Fortnite open and the bot online before relying on it.
- The app requires network access to the configured Worker.
- Do not put Discord bot tokens or Cloudflare admin tokens in the Windows app. Those belong on the bot/server only.
- The local device identifier is a convenience binding, not strong anti-tamper protection.
