# az Tool

Windows desktop client for the az Tool licensing service.

## Run (Windows)

Install Python 3.11+, then run:

```cmd
py -m pip install -r requirements.txt
py az_tool.py
```

OCR is provided by the `rapidocr-onnxruntime` Python package; **you do not need to install Tesseract or another separate OCR program**. The first package installation downloads its dependencies/models.

## Current implementation

- Dark desktop UI, license activation, and Discord-link request/approval polling.
- Radar button is gated on license activation and Discord approval.
- Monitors the bottom-centre notification region only while Fortnite is the foreground window.
- Uses bundled Python OCR dependencies to detect “Ascended Brainrot Spawned” and save a crop to `%APPDATA%\az Tool\captures`.
- Attempts to suppress repeated detections of the same OCR text.

## Important limitations

The capture region is currently configured for a 1920×1080 display and may need adjustment for another resolution or UI scale. Test before relying on it.

**Discord screenshot delivery is not wired end-to-end yet.** The current Worker/Bot implementation has not been verified to provide a secure image-event upload and DM route, so this build saves the crop locally and does not claim to send it to Discord.

## Build an EXE

```cmd
py -m pip install pyinstaller
py -m PyInstaller --onefile --windowed --name "az Tool" az_tool.py
```

The OCR package dependencies may increase the EXE size. Test the resulting executable on the target PC.

## Security

Never place Discord bot tokens, Cloudflare secrets, or admin tokens in this desktop client or repository. Client-side device IDs alone are not strong anti-tamper protection.
