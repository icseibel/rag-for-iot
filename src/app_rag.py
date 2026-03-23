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


def _formatar_snapshot_raw(snapshot: dict) -> str:
    """Builds a structured text block from a snapshot — input for the formatter chain."""
    linhas = []
    for device_id, data in snapshot.items():
        info = data["info"]
        status = data["status"]
        online = "online" if info.get("online") else "offline"
        desc = f" ({info['description']})" if info.get("description") else ""
        status_str = json.dumps(status, ensure_ascii=False) if status else "indisponível"
        linhas.append(f"- {info['name']}{desc} | {online} | {status_str}")
    return "\n".join(linhas) if linhas else "Nenhum dispositivo encontrado."


# ---------------------------------------------------------------------------
# Direct command execution (fast path, no LLM)
# Returns (response_text, needs_beautify) or None to fall through to the LLM.
# ---------------------------------------------------------------------------

def executar_comando_direto(prompt: str) -> tuple[str, bool] | None:
    """
    Match simple Portuguese commands and execute them directly against the registry.
    Returns (text, needs_beautify) or None if the prompt should go to the LLM chain.
    """
    texto = normalizar_texto(prompt)

    # --- bulk on/off ("acender/ligar todos", "apagar/desligar tudo") ---
    bulk = "todos" in texto or "tudo" in texto or "todos os dispositivos" in texto

    if bulk and any(p in texto for p in ["apagar", "desligar"]):
        resultados = _bulk_control(turn_on=False)
        return resultados, False

    if bulk and any(p in texto for p in ["acender", "ligar"]):
        resultados = _bulk_control(turn_on=True)
        return resultados, False

    # --- list / status all ---
    if bulk or any(p in texto for p in ["listar", "mostrar todos", "quais dispositivos",
                                         "status geral", "estado geral"]):
        snapshot = registry.refresh_status()
        raw = "Status de todos os dispositivos:\n" + _formatar_snapshot_raw(snapshot)
        return raw, True  # needs beautification

    # --- find target device ---
    target_id, target_data = None, None

    # 1. match by device ID substring
    for device_id, data in registry.devices.items():
        if device_id in texto:
            target_id, target_data = device_id, data
            break

    # 2. match by any word of the device name
    if target_id is None:
        for device_id, data in registry.devices.items():
            name_norm = normalizar_texto(data["info"]["name"])
            if any(word in texto for word in name_norm.split() if len(word) > 3):
                target_id, target_data = device_id, data
                break

    # 3. single device → use it without ambiguity
    if target_id is None and len(registry.devices) == 1:
        target_id, target_data = next(iter(registry.devices.items()))

    if target_id is None:
        return None  # hand off to LLM

    name = target_data["info"]["name"]
    status = target_data["status"]

    # --- status / estado ---
    if "status" in texto or "estado" in texto:
        refreshed = registry._fetch_status(target_id)
        raw = f"Status de {name}:\n{json.dumps(refreshed, ensure_ascii=False)}"
        return raw, True  # needs beautification

    # --- on / off ---
    switch_code = _primary_switch_code(status)

    if any(p in texto for p in ["apagar", "desligar"]):
        res = registry.control(target_id, [{"code": switch_code, "value": False}])
        if isinstance(res, dict) and res.get("success"):
            return f"Pronto! Desliguei **{name}**.", False
        return f"Falha ao desligar {name}: {json.dumps(res, ensure_ascii=False)}", False

    if any(p in texto for p in ["acender", "ligar"]):
        res = registry.control(target_id, [{"code": switch_code, "value": True}])
        if isinstance(res, dict) and res.get("success"):
            return f"Pronto! Liguei **{name}**.", False
        return f"Falha ao ligar {name}: {json.dumps(res, ensure_ascii=False)}", False

    return None  # prompt matched a device but no known action → LLM


def _bulk_control(turn_on: bool) -> str:
    acao = "Liguei" if turn_on else "Desliguei"
    linhas = []
    for device_id, data in registry.devices.items():
        name = data["info"]["name"]
        switch_code = _primary_switch_code(data["status"])
        res = registry.control(device_id, [{"code": switch_code, "value": turn_on}])
        if isinstance(res, dict) and res.get("success"):
            linhas.append(f"✅ {name}")
        else:
            linhas.append(f"❌ {name} — falha: {res.get('msg', 'erro desconhecido')}")
    return f"{acao} todos os dispositivos:\n" + "\n".join(linhas)


# ---------------------------------------------------------------------------
# LLM chains
# ---------------------------------------------------------------------------

def criar_chain_agente(modelo_llm: str):
    """Main chain: answers open-ended questions with live device context."""
    prompt_template = ChatPromptTemplate.from_template(
        """Você é um assistente de dispositivos inteligentes Tuya.
Responda em português do Brasil, de forma clara, amigável e objetiva.
Ao descrever o estado dos dispositivos, explique os valores de forma amigável — evite JSON bruto.

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


def criar_chain_formatador(modelo_llm: str):
    """Presentation agent: converts raw status data into friendly Portuguese prose."""
    prompt_template = ChatPromptTemplate.from_template(
        """Você é um assistente de casa inteligente. Transforme os dados técnicos abaixo \
em uma resposta clara, amigável e bem formatada em português do Brasil.
Use linguagem natural. Substitua valores técnicos por descrições compreensíveis \
(ex: brilho em %, temperatura de cor como "luz quente/fria", true/false como "ligado/desligado").
Use emojis com moderação para tornar a leitura agradável.

Dados técnicos:
{dados}

Resposta amigável:"""
    )
    llm = ChatGoogleGenerativeAI(model=modelo_llm)
    return prompt_template | llm | StrOutputParser()


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
            st.caption(f"{online} **{info['name']}**")
            if info.get("description"):
                st.caption(f"  {info['description']}")
    else:
        st.warning("Nenhum dispositivo carregado.")

chain = criar_chain_agente(modelo_selecionado)
formatter = criar_chain_formatador(modelo_selecionado)

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
                result = executar_comando_direto(prompt)
                if result is None:
                    answer = chain.invoke(prompt)
                else:
                    raw, needs_beautify = result
                    answer = formatter.invoke({"dados": raw}) if needs_beautify else raw
                st.markdown(answer)
            except Exception as exc:
                answer = (
                    "Não consegui gerar a resposta agora. "
                    f"Verifique o modelo Gemini e as credenciais Tuya. ({exc})"
                )
                st.warning(answer)

    st.session_state["messages"].append({"role": "assistant", "content": answer})
