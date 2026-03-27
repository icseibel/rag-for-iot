"""
Tests for device_registry.py.

Stubs injected by test_app_rag.py are evicted from sys.modules before the
real module is imported so these tests always operate on the production code.
"""
import sys
from unittest.mock import MagicMock, patch

import pytest

# Evict any stubs that test_app_rag.py may have registered first
for _name in ("device_registry", "tuya_client"):
    sys.modules.pop(_name, None)

from device_registry import DeviceRegistry, _primary_switch_code, _normalize_brightness  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers / free functions
# ---------------------------------------------------------------------------

class TestPrimarySwitchCode:
    def test_prefers_switch_led(self):
        assert _primary_switch_code({"switch_led": True, "switch_1": True}) == "switch_led"

    def test_falls_back_to_switch_1(self):
        assert _primary_switch_code({"switch_1": True}) == "switch_1"

    def test_picks_lowest_numbered_switch(self):
        assert _primary_switch_code({"switch_3": True, "switch_1": True}) == "switch_1"

    def test_defaults_to_switch_1_when_no_match(self):
        assert _primary_switch_code({"bright_value_v2": 500}) == "switch_1"

    def test_handles_empty_status(self):
        assert _primary_switch_code({}) == "switch_1"


class TestNormalizeBrightness:
    def test_adds_brightness_percent(self):
        result = _normalize_brightness({"bright_value_v2": 500})
        assert result["brightness_percent"] == 50

    def test_rounds_to_nearest_integer(self):
        result = _normalize_brightness({"bright_value_v2": 333})
        assert result["brightness_percent"] == 33

    def test_noop_when_key_absent(self):
        result = _normalize_brightness({"switch_led": True})
        assert "brightness_percent" not in result

    def test_full_brightness(self):
        result = _normalize_brightness({"bright_value_v2": 1000})
        assert result["brightness_percent"] == 100


# ---------------------------------------------------------------------------
# DeviceRegistry
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_client():
    client = MagicMock()
    client.ensure_connected.return_value = True
    return client


@pytest.fixture
def registry(mock_client):
    return DeviceRegistry(mock_client)


def _make_info_response(device_id, name="Lamp", category="dj", online=True):
    return {
        "success": True,
        "result": {"id": device_id, "name": name, "category": category, "online": online},
    }


def _make_status_response(items):
    return {"success": True, "result": [{"code": k, "value": v} for k, v in items.items()]}


class TestLoad:
    def test_loads_devices_from_env(self, registry, mock_client):
        mock_client.request.side_effect = [
            _make_info_response("dev1", "Lamp"),
            _make_status_response({"switch_led": True}),
        ]
        with patch.dict("os.environ", {"TUYA_DEVICE_IDS": "dev1"}):
            with patch("device_registry._load_custom_labels", return_value={}):
                result = registry.load()

        assert result is True
        assert "dev1" in registry.devices
        assert registry.devices["dev1"]["info"]["name"] == "Lamp"

    def test_returns_false_when_no_ids(self, registry):
        with patch.dict("os.environ", {"TUYA_DEVICE_IDS": ""}):
            assert registry.load() is False

    def test_returns_false_when_connection_fails(self, registry, mock_client):
        mock_client.ensure_connected.return_value = False
        with patch.dict("os.environ", {"TUYA_DEVICE_IDS": "dev1"}):
            assert registry.load() is False

    def test_custom_labels_override_api_name(self, registry, mock_client):
        mock_client.request.side_effect = [
            _make_info_response("dev1", "API Name"),
            _make_status_response({"switch_led": False}),
        ]
        custom = {"dev1": {"name": "Custom Name", "description": "My lamp"}}
        with patch.dict("os.environ", {"TUYA_DEVICE_IDS": "dev1"}):
            with patch("device_registry._load_custom_labels", return_value=custom):
                registry.load()

        assert registry.devices["dev1"]["info"]["name"] == "Custom Name"
        assert registry.devices["dev1"]["info"]["description"] == "My lamp"

    def test_loads_multiple_devices(self, registry, mock_client):
        mock_client.request.side_effect = [
            _make_info_response("dev1", "Lamp"),
            _make_status_response({"switch_led": True}),
            _make_info_response("dev2", "Switch", category="kg"),
            _make_status_response({"switch_1": False}),
        ]
        with patch.dict("os.environ", {"TUYA_DEVICE_IDS": "dev1,dev2"}):
            with patch("device_registry._load_custom_labels", return_value={}):
                registry.load()

        assert set(registry.devices.keys()) == {"dev1", "dev2"}


class TestFetchInfoChannels:
    def test_channels_passed_through_from_custom_labels(self, registry, mock_client):
        mock_client.request.return_value = _make_info_response("dev1")
        channels = {"switch_1": "Sala", "switch_2": "Churrasqueira", "switch_3": "Muro"}
        custom = {"dev1": {"name": "Triple", "channels": channels}}
        with patch("device_registry._load_custom_labels", return_value=custom):
            info = registry._fetch_info("dev1")
        assert info["channels"] == channels

    def test_channels_empty_when_not_in_custom_labels(self, registry, mock_client):
        mock_client.request.return_value = _make_info_response("dev1")
        with patch("device_registry._load_custom_labels", return_value={}):
            info = registry._fetch_info("dev1")
        assert info["channels"] == {}

    def test_channels_included_on_api_failure(self, registry, mock_client):
        mock_client.request.return_value = {"success": False}
        channels = {"switch_1": "Sala"}
        custom = {"dev1": {"channels": channels}}
        with patch("device_registry._load_custom_labels", return_value=custom):
            info = registry._fetch_info("dev1")
        assert info["channels"] == channels


class TestFetchInfo:
    def test_returns_fallback_on_api_failure(self, registry, mock_client):
        mock_client.request.return_value = {"success": False}
        with patch("device_registry._load_custom_labels", return_value={}):
            info = registry._fetch_info("dev1")
        assert info["id"] == "dev1"
        assert info["online"] is False
        assert info["category"] == "unknown"

    def test_online_field_reflects_api(self, registry, mock_client):
        mock_client.request.return_value = _make_info_response("dev1", online=False)
        with patch("device_registry._load_custom_labels", return_value={}):
            info = registry._fetch_info("dev1")
        assert info["online"] is False


class TestFetchStatus:
    def test_converts_list_to_dict(self, registry, mock_client):
        mock_client.request.return_value = _make_status_response(
            {"switch_led": True, "bright_value_v2": 500}
        )
        status = registry._fetch_status("dev1")
        assert status["switch_led"] is True
        assert status["brightness_percent"] == 50

    def test_returns_empty_dict_on_failure(self, registry, mock_client):
        mock_client.request.return_value = {"success": False}
        assert registry._fetch_status("dev1") == {}


class TestControl:
    def test_calls_post_commands_endpoint(self, registry, mock_client):
        mock_client.request.return_value = {"success": True}
        registry.control("dev1", [{"code": "switch_led", "value": True}])
        mock_client.request.assert_called_once_with(
            "POST",
            "/v1.0/devices/dev1/commands",
            {"commands": [{"code": "switch_led", "value": True}]},
        )

    def test_returns_failure_when_not_connected(self, registry, mock_client):
        mock_client.ensure_connected.return_value = False
        result = registry.control("dev1", [{"code": "switch_led", "value": True}])
        assert result["success"] is False


class TestRefreshStatus:
    def test_updates_in_memory_state(self, registry, mock_client):
        registry._devices = {
            "dev1": {"info": {"name": "Lamp"}, "status": {"switch_led": False}}
        }
        mock_client.request.return_value = _make_status_response({"switch_led": True})
        snapshot = registry.refresh_status()
        assert snapshot["dev1"]["status"]["switch_led"] is True

    def test_returns_empty_when_not_connected(self, registry, mock_client):
        mock_client.ensure_connected.return_value = False
        assert registry.refresh_status() == {}


class TestBuildContext:
    def test_returns_message_when_no_devices(self, registry):
        assert "TUYA_DEVICE_IDS" in registry.build_context()

    def test_includes_device_name_and_status(self, registry):
        registry._devices = {
            "dev1": {
                "info": {"name": "Lamp", "description": "", "category": "dj", "online": True},
                "status": {"switch_led": True},
            }
        }
        ctx = registry.build_context()
        assert "Lamp" in ctx
        assert "dev1" in ctx
        assert "online" in ctx

    def test_includes_channels_when_present(self, registry):
        registry._devices = {
            "dev1": {
                "info": {
                    "name": "Triple",
                    "description": "",
                    "category": "kg",
                    "online": True,
                    "channels": {"switch_1": "Sala", "switch_2": "Churrasqueira"},
                },
                "status": {},
            }
        }
        ctx = registry.build_context()
        assert "Sala" in ctx
        assert "Churrasqueira" in ctx

    def test_includes_description_when_present(self, registry):
        registry._devices = {
            "dev1": {
                "info": {"name": "Lamp", "description": "Living room", "category": "dj", "online": True},
                "status": {},
            }
        }
        assert "Living room" in registry.build_context()


class TestFindByName:
    def test_finds_by_substring(self, registry):
        registry._devices = {"dev1": {"info": {"name": "Living Room Lamp"}, "status": {}}}
        result = registry.find_by_name("living")
        assert result is not None
        assert result[0] == "dev1"

    def test_case_insensitive(self, registry):
        registry._devices = {"dev1": {"info": {"name": "Kitchen Light"}, "status": {}}}
        assert registry.find_by_name("KITCHEN") is not None

    def test_returns_none_when_no_match(self, registry):
        registry._devices = {"dev1": {"info": {"name": "Lamp"}, "status": {}}}
        assert registry.find_by_name("garage") is None
