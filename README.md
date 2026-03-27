# RAG Agent for Tuya Smart Devices

Streamlit chat application that controls Tuya smart home devices using natural language (Portuguese) with Google Gemini through LangChain.

## Quick Start

```bash
python -m venv .venv
```

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run src/app_rag.py
```

Open:

- Local: `http://localhost:8501`
- Local network: `http://YOUR_PC_IP:8501`

## What this project does

- Loads devices dynamically from `TUYA_DEVICE_IDS` in `.env`
- Optionally applies friendly names/descriptions from `devices.json`
- Supports direct command matching for common actions (faster path)
- Falls back to an LLM chain with live device context when needed
- Shows online/offline state and metadata in the Streamlit sidebar

## Architecture at a glance

Main components:

- `src/tuya_client.py`: Tuya Cloud API client (token + signed requests)
- `src/device_registry.py`: dynamic device loading, status fetch, control API
- `src/app_rag.py`: Streamlit UI, command matching, formatter chain, agent chain
- `devices.json`: optional per-device labels and channel names

Request flow:

1. App starts and calls `DeviceRegistry.load()`
2. Registry fetches metadata and current status for all IDs in `TUYA_DEVICE_IDS`
3. User message is first evaluated by `executar_comando_direto()`
4. If matched, command is executed directly (on/off/status/list)
5. If not matched, message goes to Gemini with `registry.build_context()`

See `ARCHITECTURE.md` for the detailed Mermaid workflow diagram.

## Local setup and run

### 1) Prerequisites

- Python 3.11+ (3.11 or 3.12 recommended)
- Tuya Cloud credentials
- Google AI API key (Gemini)

### 2) Create and activate virtual environment

```bash
python -m venv .venv
```

Windows (PowerShell):

```powershell
.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
source .venv/bin/activate
```

### 3) Install dependencies

```bash
pip install -r requirements.txt
```

### 4) Configure environment variables

Create `.env` in the project root with at least:

```env
GOOGLE_API_KEY=your_gemini_key
TUYA_ACCESS_ID=your_tuya_access_id
TUYA_ACCESS_KEY=your_tuya_access_key
TUYA_API_ENDPOINT=https://openapi.tuyaus.com
TUYA_DEVICE_IDS=id1,id2,id3
```

### 5) Run the app

```bash
streamlit run src/app_rag.py
```

The project includes `.streamlit/config.toml` with:

- `address = "0.0.0.0"`
- `port = 8501`
- `headless = true`

So the app is available at:

- Local machine: `http://localhost:8501`
- Same local network: `http://YOUR_PC_IP:8501`

## Add a new device

1. Add the Tuya device ID to `TUYA_DEVICE_IDS` in `.env`
2. Optional: add a friendly name/description in `devices.json`

Example:

```json
{
  "id3_new": {
    "name": "Front Yard Light",
    "description": "Outdoor lamp near the gate"
  }
}
```

No code changes are required.

## Run tests

```bash
python -m pytest tests/ -v
```

### Test command variants

Run all tests:

```bash
python -m pytest tests/ -v
```

Run a single test file:

```bash
python -m pytest tests/test_device_registry.py -v
```

Run a single test case:

```bash
python -m pytest tests/test_device_registry.py::test_load_success -v
```

Show print/log output while testing:

```bash
python -m pytest tests/ -v -s
```

## Notes

- The app UI and command parser are currently Portuguese-focused.
- FAISS and PyPDF dependencies are installed but not used by the current runtime flow.
