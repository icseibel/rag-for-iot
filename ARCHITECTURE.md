# Architecture — RAG Agent (Dispositivos Inteligentes)

## Workflow

```mermaid
flowchart TD
    ENV[".env\nTUYA_DEVICE_IDS\nTUYA_ACCESS_ID / KEY\nGOOGLE_API_KEY"]
    DJSON["devices.json\nnome e descrição\npersonalizados por ID"]

    subgraph Boot ["Inicialização"]
        TC["TuyaClient\ntuya_client.py"]
        DR["DeviceRegistry\ndevice_registry.py"]
        ENV --> TC
        TC -->|"OAuth2 token\n/v1.0/token"| DR
        DJSON -->|"merge nome/descrição"| DR
        DR -->|"GET /v1.0/devices/{id}\npara cada ID"| DR
        DR -->|"GET /v1.0/devices/{id}/status\npara cada ID"| DR
    end

    subgraph UI ["Streamlit — app_rag.py"]
        SIDEBAR["Sidebar\nnome · descrição\nonline / offline"]
        INPUT["Chat Input\n(português)"]
        DR --> SIDEBAR
    end

    INPUT --> CMD{"executar_comando_direto()"}

    CMD -->|"apagar/desligar todos\ntudo"| BULK_OFF["_bulk_control(False)\nPOST commands para cada dispositivo"]
    CMD -->|"acender/ligar todos\ntudo"| BULK_ON["_bulk_control(True)\nPOST commands para cada dispositivo"]
    CMD -->|"listar / status geral"| REFRESH["registry.refresh_status()\nGET status de todos"]
    CMD -->|"nome/id + desligar/apagar"| CTRL_OFF["registry.control(False)\nPOST /v1.0/devices/{id}/commands"]
    CMD -->|"nome/id + ligar/acender"| CTRL_ON["registry.control(True)\nPOST /v1.0/devices/{id}/commands"]
    CMD -->|"nome/id + status/estado"| STATUS["registry._fetch_status()\nGET /v1.0/devices/{id}/status"]
    CMD -->|"não reconhecido"| AGENT_CHAIN

    BULK_OFF -->|"needs_beautify=False"| ANSWER
    BULK_ON -->|"needs_beautify=False"| ANSWER
    CTRL_OFF -->|"needs_beautify=False"| ANSWER
    CTRL_ON -->|"needs_beautify=False"| ANSWER

    REFRESH -->|"needs_beautify=True"| FMT
    STATUS -->|"needs_beautify=True"| FMT

    subgraph FMT ["Formatter Chain (LCEL)"]
        FPROMPT["ChatPromptTemplate\nconverte JSON técnico\nem texto amigável"]
        FGEMINI["Gemini"]
        FPROMPT --> FGEMINI
    end

    subgraph AGENT_CHAIN ["Agent Chain (LCEL)"]
        CTX["registry.build_context()\nestado em tempo real"]
        APROMPT["ChatPromptTemplate\ncontexto + pergunta"]
        AGEMINI["Gemini\ngemini-2.0-flash\nou gemini-2.5-flash"]
        CTX --> APROMPT --> AGEMINI
    end

    FMT --> ANSWER["Resposta final"]
    AGEMINI --> ANSWER
    ANSWER --> CHAT["Chat Message (markdown)"]
```

## Ordem de verificação de comandos

A função `executar_comando_direto()` avalia os padrões **nesta ordem** para evitar colisões de substrings (ex: `"ligar"` está contido em `"desligar"`):

1. **Bulk off** — "desligar/apagar" + "todos/tudo"
2. **Bulk on** — "ligar/acender" + "todos/tudo"
3. **Status geral** — "listar", "mostrar todos", "status geral", etc.
4. **Dispositivo específico** — match por ID > match por nome > único dispositivo
   - off antes de on pelo mesmo motivo de substring
5. **Fallback** → Agent Chain com contexto completo

## Como adicionar um novo dispositivo

**1. Registrar o ID** em `.env`:
```
TUYA_DEVICE_IDS=id1,id2,NOVO_ID
```

**2. (Opcional) Personalizar nome e descrição** em `devices.json`:
```json
{
  "NOVO_ID": {
    "name": "Nome amigável",
    "description": "Onde fica e para que serve"
  }
}
```

Sem alteração de código. O `DeviceRegistry` descobre categoria, estado online e status automaticamente via API Tuya.

## Estrutura de arquivos

```
rag_agent/
├── .env                    # Credenciais e TUYA_DEVICE_IDS
├── devices.json            # Nomes e descrições personalizados por device ID
├── requirements.txt
├── CLAUDE.md               # Guia para Claude Code
├── ARCHITECTURE.md         # Este arquivo
└── src/
    ├── app_rag.py          # Streamlit UI, command matching, chains
    ├── tuya_client.py      # Cliente HTTP Tuya (auth HMAC-SHA256)
    └── device_registry.py  # Gerenciamento dinâmico de dispositivos
```

## Fluxo de autenticação Tuya

```
TuyaClient._generate_sign()
  msg = access_id + token + timestamp + METHOD + "\n" + body_sha256 + "\n\n" + path
  sign = HMAC-SHA256(msg, access_key).upper()

Headers enviados:
  client_id, sign, t, sign_method, access_token (após login)
```
