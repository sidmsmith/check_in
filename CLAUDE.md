# Check In Kiosk (check_in) — Project Instructions

This project follows the global `AGENTS.md` and `SECURITY_BASELINE.md`.
The notes below cover only what's specific to this repository.

Note: `Work/appt-app` is a separate, archived (read-only on GitHub)
repo that is also titled "Check In Kiosk" — this repo (`check_in`) is
the active one. Don't confuse the two.

## Version identifiers

Three places, in sync at `v0.1.5`:

- `package.json` — the `version` field
- `index.html` — the `<title>` ("Check In Kiosk vX.Y.Z")
- `api/index.py` — the `app_version` value in the status payload

## Local development

- `node server.js` — Express, serves `index.html`/`public/` and proxies
  `/api/*` to the Flask backend (port 3000 by default, via `PORT` env
  var)
- `python api/index.py` — Flask backend, port 5000 (`app.run(port=5000,
  debug=True)`)

In production (Vercel), `server.js` routes `/api/*` to `api/index.py`
directly instead of proxying to localhost.
