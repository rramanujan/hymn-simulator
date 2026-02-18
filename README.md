# HYMN Simulator

A web-based simulator for a small hypothetical CPU ("HYMN machine"), with:

- Assembly editing in the browser
- Interactive memory/register bit editing
- Step-by-step or full-program execution
- Input/output support (`read` / `write`)
- Per-user execution sessions

The backend is a Flask API, and the frontend is a static single-page app.

## Project Structure

- `app.py`: Flask app and API endpoints (`/api/*`)
- `simulator.py`: CPU + assembler implementation
- `static/index.html`: main UI
- `static/docs.html`: instruction/reference docs page
- `test_app.py`: backend regression tests

## Requirements

- Python 3.9+
- Dependencies in `requirements.txt`

## Run Locally

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Start the server:

```bash
python app.py
```

3. Open:

- [http://localhost:5000](http://localhost:5000)
- Docs: [http://localhost:5000/docs](http://localhost:5000/docs)

## API Overview

All simulator API endpoints are `POST` and require a `session` string in JSON.

- `/api/load`: load code + optional input buffer
- `/api/step`: execute one instruction
- `/api/run`: execute until halt, input wait, or timeout
- `/api/reset`: clear session state
- `/api/memory`: mutate a memory location (`address`, `decimal`)
- `/api/register`: mutate `pc` or `ac`
- `/api/input`: provide one input value while waiting for `read`

### Example

```bash
curl -X POST http://localhost:5000/api/load \
  -H "Content-Type: application/json" \
  -d '{"session":"demo","code":"load 3\nwrite\nhalt\n7","input":[]}'
```

## Safety and Session Behavior

- **Execution timeout**: default is 60 seconds for `/api/run`
- **Session isolation**: each client uses a unique session ID
- **Session cleanup**:
  - time-to-live (TTL): default 7200 seconds
  - max sessions: default 1000 (least-recently-used eviction)

## Configuration

Environment variables:

- `PORT` (default: `5000`)
- `EXECUTION_TIMEOUT_SECONDS` (default: `60`)
- `SESSION_TTL_SECONDS` (default: `7200`)
- `MAX_SESSIONS` (default: `1000`)

## Tests

Run unit tests:

```bash
python -m unittest -v
```

Current tests cover:

- session isolation between users
- required session ID validation
- execution timeout behavior for an infinite loop

## Deployment Notes

- `Procfile` runs: `gunicorn app:app`
- `Dockerfile` is included for container-based deployment
