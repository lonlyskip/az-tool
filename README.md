# az Tool

Windows desktop client for the az Tool licensing service.

## Download for Windows

**[Download the latest az Tool release](https://github.com/lonlyskip/az-tool/releases/latest)**

Open the latest release and download **az tool.exe**. This link stays the same; it always opens the newest published release.

Every successful workflow run on the `az-tool-rebuild` branch publishes a new GitHub Release automatically. The build artifact is also retained in GitHub Actions for 14 days.

## Run locally (Windows)

Install Python 3.11+, then run:

```cmd
py -m pip install -r requirements.txt
py az_tool.py
```

The OCR engine is provided by `rapidocr-onnxruntime`; a separate Tesseract install is not required.

## Build

The GitHub Actions workflow builds a single-file Windows executable with Nuitka and publishes it as a GitHub Release whenever the relevant application files change on `az-tool-rebuild`.

You can also build locally with Nuitka:

```cmd
py -m pip install -r requirements.txt nuitka zstandard
py make_icon.py
py -m nuitka --mode=onefile --windows-console-mode=disable --assume-yes-for-downloads --enable-plugin=tk-inter --include-package=rapidocr_onnxruntime --include-package-data=rapidocr_onnxruntime --include-package=onnxruntime --include-data-files=assets/az-tool-icon.ico=az-tool-icon.ico --include-data-files=IMG_4552.jpg=IMG_4552.jpg --output-filename="az tool.exe" az_tool.py
```

## Implemented

- Dark desktop interface named **az Tool** with the **Licensed Edition** concept.
- License activation and server-side validation.
- Discord link request and approval status polling.
- START/STOP radar controls; the radar is gated behind license and Discord verification.
- OCR detection for the phrase “Ascended Brainrot Spawned”.
- Captures the configured notification region while Fortnite is the foreground window.
- Encodes the cropped notification in memory and uploads it to the Worker at `/api/radar/event`; it does not intentionally save screenshot files to disk.
- Worker queue integration is expected at `/bot/radar-events` and `/bot/radar-delivered`, with the Discord bot responsible for sending the image DM.

## Important test notes

- OCR detection and notification-region behavior should be tested on the intended display resolution and UI scale.
- The app has not been verified against a live Fortnite event in this repository workflow; test it before relying on it.
- The app requires network access to the configured Worker.
- Do not put Discord bot tokens or Cloudflare admin tokens in the Windows app. Those belong on the bot/server only.
- The local device identifier is a convenience binding, not strong anti-tamper protection.
- Check the applicable game rules before using automated input features.
