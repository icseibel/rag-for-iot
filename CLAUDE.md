# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Run the main app
streamlit run src/app_rag.py
```

## Running Tests

```bash
# Run all tests (use the project venv)
python -m pytest tests/ -v

# Run a single test file
python -m pytest tests/test_device_registry.py -v
```

## Environment Configuration

Requires a `.env` file in the project root with:
- `GOOGLE_API_KEY` — Gemini API key
- `TUYA_ACCESS_ID`, `TUYA_ACCESS_KEY` — Tuya Cloud API credentials
- `TUYA_DEVICE_IDS` — Comma-separated Tuya device IDs (e.g., `id1,id2,id3`)
- `TUYA_API_ENDPOINT` — Tuya regional API base URL (default: `https://openapi.tuyaus.com`)

## Architecture

A **Streamlit chat UI** that lets users control Tuya smart home devices via natural language. Uses Google Gemini via LangChain. Devices are discovered dynamically — no code changes needed when adding new hardware.

### Component Overview

| File | Role |
|------|------|
| `src/tuya_client.py` | Shared Tuya Cloud API client: HMAC-SHA256 signing, OAuth2 token acquisition, all HTTP requests |
| `src/device_registry.py` | `DeviceRegistry`: reads `TUYA_DEVICE_IDS`, fetches device info + live status from Tuya API, provides `control()` and `build_context()` |
| `src/app_rag.py` | Streamlit UI: sidebar device list, Portuguese command pattern matching (fast path), LLM chain fallback |
| `devices.json` | Optional file to override device names and descriptions by device ID (see Adding a New Device) |

### Adding a New Device

Append its Tuya device ID to `TUYA_DEVICE_IDS` in `.env` — no code changes required:

```
TUYA_DEVICE_IDS=id1,id2,id3_new
```

Optionally, add a friendly name and description in `devices.json` (root of project):

```json
{
  "id3_new": {
    "name": "Friendly Name",
    "description": "Where it is and what it does"
  }
}
```

The registry fetches the device category, online state, and live status from the Tuya API on startup. `devices.json` names take precedence over Tuya API names.

### Request Flow

1. `DeviceRegistry.load()` fetches info + status for all IDs in `TUYA_DEVICE_IDS`
2. Sidebar renders every registered device with online/offline status
3. User sends a Portuguese message → `executar_comando_direto()` matches against known patterns:
   - "listar / mostrar todos" → `registry.refresh_status()` → formatted table
   - Device name/ID + "ligar/acender" or "desligar/apagar" → `registry.control()` with the device's own switch code
   - Device name/ID + "status/estado" → `registry._fetch_status()`
4. If no pattern matches, the message goes to a LangChain LCEL chain (Gemini) with `registry.build_context()` injected as context
5. `build_context()` is called fresh on each LLM request so state is always current

### Tuya API Authentication

All calls go through `TuyaClient`. Token obtained once via `GET /v1.0/token?grant_type=1`; subsequent requests include `access_token` header. Each request is signed with HMAC-SHA256: `access_id + token + timestamp + (method + body_sha256 + path)`.

The primary switch code per device (`switch_led` for lamps, `switch_1`–`switch_N` for multi-channel switches) is inferred from the device's live status keys via `_primary_switch_code()`.

### Pattern Matching Order in `executar_comando_direto()`

Patterns are evaluated in this order to avoid substring collisions (e.g. `"ligar"` is a substring of `"desligar"`):
1. Bulk off — "desligar/apagar" + "todos/tudo"
2. Bulk on — "ligar/acender" + "todos/tudo"
3. Status all — "listar", "mostrar todos", "status geral", etc.
4. Single device (matched by ID > name > sole device): off before on for the same substring reason
5. Fallback → Agent Chain (LLM with full device context)

See `ARCHITECTURE.md` for a full Mermaid flow diagram.

### Note on "RAG" Naming

FAISS and PyPDF are installed but unused. "RAG" refers to the context-enriched prompting pattern: live device state is injected into the LLM prompt at each turn.
