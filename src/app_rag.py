# Sistema RAG — Controle dinâmico de dispositivos Tuya via Gemini

import json
import unicodedata
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_google_genai import ChatGoogleGenerativeAI

from device_registry import DeviceRegistry, _primary_switch_code
from tuya_client import TuyaClient

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=True)

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

client = TuyaClient()
registry = DeviceRegistry(client)

if not registry.load():
    st.error(
        "Não foi possível carregar os dispositivos. "
        "Verifique TUYA_DEVICE_IDS, TUYA_ACCESS_ID e TUYA_ACCESS_KEY no .env"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalizar_texto(texto: str) -> str:
    texto = texto.lower().strip()
    return "".join(
        ch for ch in unicodedata.normalize("NFD", texto) if unicodedata.category(ch) != "Mn"
    )


def _formatar_snapshot(snapshot: dict) -> str:
    linhas = []
    for device_id, data in snapshot.items():
        info = data["info"]
        status = data["status"]
        online = "online" if info.get("online") else "offline"
        status_str = json.dumps(status, ensure_ascii=False) if status else "indisponível"
        linhas.append(f"- **{info['name']}** ({online}): {status_str}")
    return "\n".join(linhas) if linhas else "Nenhum dispositivo encontrado."


# ---------------------------------------------------------------------------
# Direct command execution (fast path, no LLM)
# ---------------------------------------------------------------------------

def executar_comando_direto(prompt: str) -> str | None:
    """
    Match simple Portuguese commands and execute them directly against the registry.
    Returns None if the prompt should be forwarded to the LLM.
    """
    texto = normalizar_texto(prompt)

    # --- list / status all ---
    if any(p in texto for p in ["listar", "mostrar todos", "todos os dispositivos",
                                  "quais dispositivos", "status geral", "estado geral"]):
        snapshot = registry.refresh_status()
        return "Status atual de todos os dispositivos:\n" + _formatar_snapshot(snapshot)

    # --- find target device ---
    target_id, target_data = None, None

    # 1. match by device ID substring
    for device_id, data in registry.devices.items():
        if device_id in texto:
            target_id, target_data = device_id, data
            break

    # 2. match by device name (any word fragment)
    if target_id is None:
        for device_id, data in registry.devices.items():
            name_norm = normalizar_texto(data["info"]["name"])
            if any(word in texto for word in name_norm.split()):
                target_id, target_data = device_id, data
                break

    # 3. single device → use it; multiple → no ambiguous match
    if target_id is None and len(registry.devices) == 1:
        target_id, target_data = next(iter(registry.devices.items()))

    if target_id is None:
        return None  # hand off to LLM

    name = target_data["info"]["name"]
    status = target_data["status"]

    # --- status / estado ---
    if "status" in texto or "estado" in texto:
        refreshed = registry._fetch_status(target_id)
        return f"Estado de **{name}**: {json.dumps(refreshed, ensure_ascii=False)}"

    # --- on / off ---
    switch_code = _primary_switch_code(status)

    if any(p in texto for p in ["acender", "ligar"]):
        res = registry.control(target_id, [{"code": switch_code, "value": True}])
        if isinstance(res, dict) and res.get("success"):
            return f"Pronto! Liguei **{name}**."
        return f"Falha ao ligar {name}: {json.dumps(res, ensure_ascii=False)}"

    if any(p in texto for p in ["apagar", "desligar"]):
        res = registry.control(target_id, [{"code": switch_code, "value": False}])
        if isinstance(res, dict) and res.get("success"):
            return f"Pronto! Desliguei **{name}**."
        return f"Falha ao desligar {name}: {json.dumps(res, ensure_ascii=False)}"

    return None  # prompt matched a device but no known action → LLM


# ---------------------------------------------------------------------------
# LLM chain
# ---------------------------------------------------------------------------

def criar_chain_agente(modelo_llm: str):
    prompt_template = ChatPromptTemplate.from_template(
        """Você é um assistente de dispositivos inteligentes Tuya.
Responda em português do Brasil, de forma clara e objetiva.
Ao descrever o estado dos dispositivos, explique os valores de forma amigável ao usuário.

Contexto dos dispositivos (atualizado em tempo real):
{context}

Pergunta do usuário: {question}

Resposta:"""
    )

    buscador_contexto = RunnableLambda(lambda _: registry.build_context())
    llm = ChatGoogleGenerativeAI(model=modelo_llm)

    return (
        {"context": buscador_contexto, "question": RunnablePassthrough()}
        | prompt_template
        | llm
        | StrOutputParser()
    )


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

st.title("Assistente RAG — Dispositivos Inteligentes")

with st.sidebar:
    st.subheader("Configuração")
    modelo_selecionado = st.selectbox(
        "Modelo Gemini",
        ["gemini-2.0-flash", "gemini-2.5-flash"],
        index=0,
    )
    st.divider()
    st.subheader("Dispositivos registrados")
    if registry.devices:
        for device_id, data in registry.devices.items():
            info = data["info"]
            online = "🟢" if info.get("online") else "🔴"
            st.caption(f"{online} {info['name']} ({info['category']})")
    else:
        st.warning("Nenhum dispositivo carregado.")

chain = criar_chain_agente(modelo_selecionado)

if "messages" not in st.session_state:
    st.session_state["messages"] = []

for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

prompt = st.chat_input("Peça para ligar, desligar, listar ou consultar status dos dispositivos...")
if prompt:
    st.session_state["messages"].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Processando..."):
            try:
                answer = executar_comando_direto(prompt)
                if answer is None:
                    answer = chain.invoke(prompt)
                st.markdown(answer)
            except Exception as exc:
                answer = (
                    "Não consegui gerar a resposta agora. "
                    f"Verifique o modelo Gemini e as credenciais Tuya. ({exc})"
                )
                st.warning(answer)

    st.session_state["messages"].append({"role": "assistant", "content": answer})
