# AFK Tool starter (Windows client + license API)

## Important
- This is a starter project, not a finished commercial product.
- The client sends keyboard input to the currently focused app. It does not detect Fortnite's lobby state. `P` is sent on a timer, so tune/disable it if it causes unwanted actions.
- Check the target game's rules before using or selling automation tools.
- Never publish `ADMIN_TOKEN`; keep it only in your server host's environment variables.
- Use HTTPS in production. Do not run Flask's development server publicly.

## Files
- `client.py`: English Tkinter client, Start/Stop, license key entry, basic keyboard loop.
- `server.py`: Flask API, one-device license activation, expiry, key creation and revocation.
- `requirements-server.txt`: server dependency.

## 1. Test the license server locally
Install Python 3.11+ on your server/development PC, then in the project folder:

```cmd
py -m pip install -r requirements-server.txt
```

Set an admin token in Windows CMD (choose your own long random value):

```cmd
set ADMIN_TOKEN=replace-with-a-long-random-secret
```

Run the server for local testing:

```cmd
py server.py
```

The local URL is `http://127.0.0.1:8000`. For local testing only, edit `LICENSE_SERVER` in `client.py` to that URL. For a customer EXE, deploy the API to a host with HTTPS and replace the URL with that deployed HTTPS address.

## 2. Create license keys
With the server running, use a separate terminal. Replace the token and choose days/count:

```cmd
curl -X POST http://127.0.0.1:8000/admin/create -H "Content-Type: application/json" -H "X-Admin-Token: replace-with-a-long-random-secret" -d "{\"days\":30,\"count\":5}"
```

Revoke a key:

```cmd
curl -X POST http://127.0.0.1:8000/admin/revoke -H "Content-Type: application/json" -H "X-Admin-Token: replace-with-a-long-random-secret" -d "{\"key\":\"XXXXX-XXXXX-XXXXX\"}"
```

## 3. Build the Windows EXE
Install PyInstaller:

```cmd
py -m pip install pyinstaller
```

Set `LICENSE_SERVER` in `client.py` to your deployed HTTPS API URL, then:

```cmd
py -m PyInstaller --onefile --windowed --name AFKTool client.py
```

The EXE will be in `dist\\AFKTool.exe`.

## Commercial hardening before selling
- Add an admin dashboard, payment flow, audit logs, rate limiting, backups, monitoring, and customer support.
- Device binding here is a convenience, not strong anti-tamper security; local identifiers can be changed or spoofed.
- Do not place signing secrets or admin credentials in the client.
- Use a production WSGI server, HTTPS, and a persistent database when hosted.
- Keep a way to migrate licenses and reset device bindings for legitimate customers.
