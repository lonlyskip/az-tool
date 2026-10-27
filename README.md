# az Tool

Windows desktop client for the az Tool licensing service.

## Current rebuild branch

This branch introduces `az_tool.py`, an English dark UI connected to the deployed Cloudflare Worker:
`https://az-tool-license.a-abdilaziz-a.workers.dev`

### Included in this build
- License activation using the existing `/api/activate` endpoint and a device identifier.
- Discord-link request using `/api/link/request`.
- Local storage of the entered license key and Discord ID in the user's AppData folder.
- Dark UI with status and subscription display placeholders.
- Network calls run on background threads so the window remains responsive.

### Run locally (Windows)
Install Python 3.11+ and run:

```cmd
py az_tool.py
```

### Build an EXE
Install PyInstaller, then run:

```cmd
py -m pip install pyinstaller
py -m PyInstaller --onefile --windowed --name "az Tool" az_tool.py
```

The executable will be in `dist`.

## Not finished yet
The radar is intentionally disabled in this build. Fortnite notification OCR/screen detection, tightly cropped screenshots, safe duplicate handling, secure delivery to the correct Discord user, and end-to-end verification against the live Worker/Bot still need implementation and testing. Do not advertise this build as having a working radar yet.

## Security notes
- Never put `ADMIN_TOKEN`, Discord bot tokens, or Cloudflare secrets in the client or repository.
- License/device checks on a client are not strong anti-tamper protection by themselves.
- Use HTTPS for all production requests and test API response shapes before distributing an EXE.
- Keep automation compliant with the target game's rules.
