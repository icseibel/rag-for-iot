# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Run the main app
streamlit run src/app_rag.py
```

## Environment Configuration

Requires a `.env` file in the project root with:
- `GOOGLE_API_KEY` — Gemini API key
- `ACCESS_ID`, `ACCESS_KEY` — Tuya Cloud API credentials
- `DEVICE_ID` — Target lamp device ID
- `SWITCH_DEVICE_ID` — Target touch switch device ID
- `BASE_URL` — Tuya regional API endpoint (e.g., `https://openapi.tuyaus.com`)

## Architecture

A **Streamlit chat UI** that lets users control Tuya smart home devices via natural language. Uses Google Gemini via LangChain. Devices are discovered dynamically — no code changes needed when adding new hardware.

### Component Overview

| File | Role |
|------|------|
| `src/tuya_client.py` | Shared Tuya Cloud API client: HMAC-SHA256 signing, OAuth2 token acquisition, all HTTP requests |
| `src/device_registry.py` | `DeviceRegistry`: reads `TUYA_DEVICE_IDS`, fetches device info + live status from Tuya API, provides `control()` and `build_context()` |
| `src/app_rag.py` | Streamlit UI: sidebar device list, Portuguese command pattern matching (fast path), LLM chain fallback |
| `src/lamp_controller_mcp.py` | Legacy per-device lamp wrapper (not used by `app_rag.py` anymore) |
| `src/touch_switch_mcp.py` | Legacy per-device switch wrapper (not used by `app_rag.py` anymore) |
| `src/lamp_controller_rest.py` | Standalone REST auth helper (legacy, not used by main app) |

### Adding a New Device

Append its Tuya device ID to `TUYA_DEVICE_IDS` in `.env` — no code changes required:

```
TUYA_DEVICE_IDS=id1,id2,id3_new
```

The registry fetches the device name, category, and live status from the Tuya API on startup.

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

### Note on "RAG" Naming

FAISS and PyPDF are installed but unused. "RAG" refers to the context-enriched prompting pattern: live device state is injected into the LLM prompt at each turn.
