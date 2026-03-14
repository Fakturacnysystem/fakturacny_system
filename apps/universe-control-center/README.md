# Universe Control Center App

Universe Control Center is now installable as a Progressive Web App on both macOS and iPhone.

## Local URL

- `http://127.0.0.1:8081/ui`

## macOS

1. Open the URL in Safari.
2. Use `File` -> `Add to Dock`.
3. Launch it from the Dock like a native app.

## iPhone

1. Open the URL in Safari.
2. Tap `Share`.
3. Tap `Add to Home Screen`.
4. Launch it from the Home Screen as a standalone app.

## Notes

- The app stores the bearer token only in browser local storage on that device.
- The app manifest, service worker, and touch icons are served by the FastAPI gateway.
- For best realtime behaviour, keep the backend stack running with `gateway-api`, `realtime-worker`, and `redis`.
