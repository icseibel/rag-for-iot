"""
Tests for the command-matching logic in app_rag.py.

Streamlit and LangChain are NOT imported — only the pure functions are tested
by patching the module-level globals before import.
"""
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Minimal stubs so app_rag can be imported without a real Streamlit/LangChain
# ---------------------------------------------------------------------------

def _make_stub_module(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod

# streamlit stub
st = _make_stub_module("streamlit")
st.error = MagicMock()
st.title = MagicMock()
st.sidebar = MagicMock()
st.sidebar.__enter__ = MagicMock(return_value=None)
st.sidebar.__exit__ = MagicMock(return_value=False)
st.selectbox = MagicMock(return_value="gemini-2.0-flash")
st.divider = MagicMock()
st.subheader = MagicMock()
st.caption = MagicMock()
st.warning = MagicMock()
st.session_state = {}
st.chat_input = MagicMock(return_value=None)
st.chat_message = MagicMock()
st.chat_message.return_value.__enter__ = MagicMock(return_value=None)
st.chat_message.return_value.__exit__ = MagicMock(return_value=False)
st.spinner = MagicMock()
st.spinner.return_value.__enter__ = MagicMock(return_value=None)
st.spinner.return_value.__exit__ = MagicMock(return_value=False)
st.markdown = MagicMock()

# langchain / google stubs
for mod_name in [
    "langchain_core",
    "langchain_core.output_parsers",
    "langchain_core.prompts",
    "langchain_core.runnables",
    "langchain_google_genai",
    "dotenv",
]:
    _make_stub_module(mod_name)

sys.modules["langchain_core.output_parsers"].StrOutputParser = MagicMock()
sys.modules["langchain_core.prompts"].ChatPromptTemplate = MagicMock()
sys.modules["langchain_core.runnables"].RunnableLambda = MagicMock(side_effect=lambda f: f)
sys.modules["langchain_core.runnables"].RunnablePassthrough = MagicMock()
sys.modules["langchain_google_genai"].ChatGoogleGenerativeAI = MagicMock()
sys.modules["dotenv"].load_dotenv = MagicMock()

# device_registry / tuya_client stubs
_make_stub_module("device_registry")
_make_stub_module("tuya_client")

_mock_registry = MagicMock()
_mock_client = MagicMock()

sys.modules["device_registry"].DeviceRegistry = MagicMock(return_value=_mock_registry)
sys.modules["device_registry"]._primary_switch_code = MagicMock(return_value="switch_led")
sys.modules["tuya_client"].TuyaClient = MagicMock(return_value=_mock_client)

_mock_registry.load.return_value = True
_mock_registry.devices = {}

sys.path.insert(0, "src")

import app_rag  # noqa: E402  (must come after stubs)
from app_rag import normalizar_texto, executar_comando_direto, _bulk_control


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_registry():
    """Give each test a clean registry state."""
    _mock_registry.devices = {}
    sys.modules["device_registry"]._primary_switch_code.return_value = "switch_led"
    app_rag.registry = _mock_registry
    yield


def _device(name, online=True, status=None):
    return {
        "info": {"name": name, "online": online, "description": ""},
        "status": status or {"switch_led": True},
    }


# ---------------------------------------------------------------------------
# normalizar_texto
# ---------------------------------------------------------------------------

class TestNormalizarTexto:
    def test_lowercases(self):
        assert normalizar_texto("LIGAR") == "ligar"

    def test_strips_whitespace(self):
        assert normalizar_texto("  ligar  ") == "ligar"

    def test_removes_accents(self):
        assert normalizar_texto("Lâmpada") == "lampada"
        assert normalizar_texto("desligar iluminação") == "desligar iluminacao"


# ---------------------------------------------------------------------------
# executar_comando_direto — bulk operations
# ---------------------------------------------------------------------------

class TestBulkCommands:
    def setup_method(self):
        _mock_registry.devices = {
            "dev1": _device("Lamp"),
            "dev2": _device("Switch"),
        }

    def test_bulk_off_tudo(self):
        _mock_registry.control.return_value = {"success": True}
        result = executar_comando_direto("desligar tudo")
        assert result is not None
        text, needs_beautify = result
        assert needs_beautify is False
        assert "Desliguei" in text

    def test_bulk_on_todos(self):
        _mock_registry.control.return_value = {"success": True}
        result = executar_comando_direto("ligar todos")
        assert result is not None
        text, _ = result
        assert "Liguei" in text

    def test_bulk_off_takes_priority_over_on(self):
        """'desligar' must be checked before 'ligar' to avoid substring matches."""
        _mock_registry.control.return_value = {"success": True}
        result = executar_comando_direto("desligar todos os dispositivos")
        text, _ = result
        assert "Desliguei" in text


# ---------------------------------------------------------------------------
# executar_comando_direto — list / status all
# ---------------------------------------------------------------------------

class TestListCommands:
    def setup_method(self):
        _mock_registry.devices = {"dev1": _device("Lamp")}
        _mock_registry.refresh_status.return_value = {"dev1": _device("Lamp")}

    def test_listar_triggers_refresh(self):
        result = executar_comando_direto("listar")
        assert result is not None
        _, needs_beautify = result
        assert needs_beautify is True
        _mock_registry.refresh_status.assert_called()

    def test_mostrar_todos_triggers_refresh(self):
        result = executar_comando_direto("mostrar todos")
        assert result is not None

    def test_status_geral(self):
        result = executar_comando_direto("status geral")
        assert result is not None


# ---------------------------------------------------------------------------
# executar_comando_direto — single device targeting
# ---------------------------------------------------------------------------

class TestSingleDeviceCommands:
    def setup_method(self):
        _mock_registry.devices = {"dev1": _device("Lampada Sala")}
        _mock_registry.control.return_value = {"success": True}
        _mock_registry._fetch_status.return_value = {"switch_led": False}

    def test_match_by_device_id(self):
        result = executar_comando_direto("ligar dev1")
        assert result is not None
        text, _ = result
        assert "Liguei" in text

    def test_match_by_name_word(self):
        result = executar_comando_direto("ligar lampada")
        assert result is not None
        text, _ = result
        assert "Liguei" in text

    def test_turn_off_device(self):
        result = executar_comando_direto("desligar lampada")
        assert result is not None
        text, _ = result
        assert "Desliguei" in text

    def test_status_device(self):
        result = executar_comando_direto("status lampada")
        assert result is not None
        _, needs_beautify = result
        assert needs_beautify is True

    def test_single_device_used_without_name(self):
        """When only one device exists, it's used even without a name match."""
        result = executar_comando_direto("ligar")
        assert result is not None

    def test_control_failure_returns_error_message(self):
        _mock_registry.control.return_value = {"success": False, "msg": "timeout"}
        result = executar_comando_direto("ligar lampada")
        text, _ = result
        assert "Falha" in text or "falha" in text

    def test_returns_none_for_unknown_action(self):
        """Device matched but no known action → fall through to LLM."""
        result = executar_comando_direto("brilho lampada")
        assert result is None

    def test_returns_none_when_no_device_matched(self):
        result = executar_comando_direto("ligar garagem")
        # No device named 'garagem' and more than zero devices with no single fallback
        # (two devices → no single-device shortcut)
        _mock_registry.devices = {
            "dev1": _device("Lamp"),
            "dev2": _device("Switch"),
        }
        result = executar_comando_direto("ligar garagem")
        assert result is None


# ---------------------------------------------------------------------------
# _bulk_control
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# executar_comando_direto — multi-channel device
# ---------------------------------------------------------------------------

def _multichannel_device(name="Interruptor Triple"):
    return {
        "info": {
            "name": name,
            "online": True,
            "description": "",
            "channels": {
                "switch_1": "Sala",
                "switch_2": "Churrasqueira",
                "switch_3": "Muro",
            },
        },
        "status": {"switch_1": True, "switch_2": False, "switch_3": True},
    }


class TestMultiChannelCommands:
    def setup_method(self):
        _mock_registry.devices = {"triple1": _multichannel_device()}
        _mock_registry.control.return_value = {"success": True}

    def test_ligar_sala_uses_switch_1(self):
        result = executar_comando_direto("ligar sala")
        assert result is not None
        text, _ = result
        assert "Sala" in text
        cmd = _mock_registry.control.call_args[0][1]
        assert cmd == [{"code": "switch_1", "value": True}]

    def test_desligar_churrasqueira_uses_switch_2(self):
        result = executar_comando_direto("desligar churrasqueira")
        assert result is not None
        text, _ = result
        assert "Churrasqueira" in text
        cmd = _mock_registry.control.call_args[0][1]
        assert cmd == [{"code": "switch_2", "value": False}]

    def test_ligar_muro_uses_switch_3(self):
        result = executar_comando_direto("ligar muro")
        assert result is not None
        cmd = _mock_registry.control.call_args[0][1]
        assert cmd == [{"code": "switch_3", "value": True}]

    def test_channel_name_in_response(self):
        result = executar_comando_direto("ligar churrasqueira")
        text, _ = result
        assert "Churrasqueira" in text

    def test_accent_insensitive_channel_match(self):
        """'churrasqueira' with/without accent should both match."""
        result = executar_comando_direto("ligar churrasqueira")
        cmd = _mock_registry.control.call_args[0][1]
        assert cmd[0]["code"] == "switch_2"

    def test_no_channel_match_falls_back_to_primary(self):
        """Command with no channel keyword → _primary_switch_code is used."""
        with patch.object(app_rag, "_primary_switch_code", return_value="switch_primary"):
            result = executar_comando_direto("ligar interruptor")
        assert result is not None
        cmd = _mock_registry.control.call_args[0][1]
        assert cmd[0]["code"] == "switch_primary"


class TestBulkControl:
    def test_reports_success_per_device(self):
        _mock_registry.devices = {
            "dev1": _device("Lamp"),
            "dev2": _device("Switch"),
        }
        _mock_registry.control.return_value = {"success": True}
        text = _bulk_control(turn_on=True)
        assert "Lamp" in text
        assert "Switch" in text

    def test_reports_failure_per_device(self):
        _mock_registry.devices = {"dev1": _device("Lamp")}
        _mock_registry.control.return_value = {"success": False, "msg": "offline"}
        text = _bulk_control(turn_on=False)
        assert "falha" in text.lower() or "offline" in text
