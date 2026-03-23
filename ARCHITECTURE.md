# Architecture — RAG Agent (Dispositivos Inteligentes)

## Workflow

```mermaid
flowchart TD
    ENV[".env\nTUYA_DEVICE_IDS\nTUYA_ACCESS_ID / KEY\nGOOGLE_API_KEY"]

    subgraph Boot ["Inicialização"]
        TC["TuyaClient\ntuya_client.py"]
        DR["DeviceRegistry\ndevice_registry.py"]
        ENV --> TC
        TC -->|"OAuth2 token\n/v1.0/token"| DR
        DR -->|"GET /v1.0/devices/{id}\npara cada ID"| DR
        DR -->|"GET /v1.0/devices/{id}/status\npara cada ID"| DR
    end

    subgraph UI ["Streamlit — app_rag.py"]
        SIDEBAR["Sidebar\nlista dispositivos\nonline / offline"]
        INPUT["Chat Input\n(português)"]
        DR --> SIDEBAR
    end

    INPUT --> CMD{"executar_comando_direto()"}

    CMD -->|"listar / mostrar todos"| REFRESH["registry.refresh_status()\nGET status de todos"]
    CMD -->|"nome/id + ligar/desligar"| CTRL["registry.control()\nPOST /v1.0/devices/{id}/commands"]
    CMD -->|"nome/id + status"| STATUS["registry._fetch_status()\nGET /v1.0/devices/{id}/status"]
    CMD -->|"não reconhecido"| LLM

    subgraph LLM ["Cadeia LangChain (LCEL)"]
        CTX["registry.build_context()\nestado em tempo real de todos os dispositivos"]
        PROMPT["ChatPromptTemplate\ncontexto + pergunta"]
        GEMINI["Gemini\ngemini-2.0-flash\nou gemini-2.5-flash"]
        CTX --> PROMPT --> GEMINI
    end

    REFRESH --> ANSWER["Resposta ao usuário"]
    CTRL --> ANSWER
    STATUS --> ANSWER
    GEMINI --> ANSWER
    ANSWER --> CHAT["Chat Message\n(markdown)"]
```

## Como adicionar um novo dispositivo

```
# .env
TUYA_DEVICE_IDS=id_existente_1,id_existente_2,NOVO_ID
```

Nenhuma alteração de código é necessária. Na próxima inicialização, o `DeviceRegistry` consulta a API Tuya para obter nome, categoria e status do novo dispositivo automaticamente.

## Estrutura de arquivos

```
rag_agent/
├── .env                    # Credenciais e lista de dispositivos
├── requirements.txt
├── CLAUDE.md               # Guia para Claude Code
├── ARCHITECTURE.md         # Este arquivo
└── src/
    ├── app_rag.py          # Streamlit UI + lógica de comandos
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
