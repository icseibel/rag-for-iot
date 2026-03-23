import json
import os
from pathlib import Path

from tuya_client import TuyaClient

_DEVICES_CONFIG = Path(__file__).resolve().parent.parent / "devices.json"


def _load_custom_labels() -> dict[str, dict]:
    """Load name/description overrides from devices.json (optional)."""
    if not _DEVICES_CONFIG.exists():
        return {}
    try:
        return json.loads(_DEVICES_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _normalize_brightness(status: dict) -> dict:
    if "bright_value_v2" in status:
        status["brightness_percent"] = round((status["bright_value_v2"] / 1000) * 100)
    return status


def _primary_switch_code(status: dict) -> str:
    """Determine the on/off command code from the device's live status keys."""
    if "switch_led" in status:
        return "switch_led"
    for i in range(1, 7):
        if f"switch_{i}" in status:
            return f"switch_{i}"
    return "switch_1"


class DeviceRegistry:
    """
    Manages all Tuya devices listed in the TUYA_DEVICE_IDS environment variable
    (comma-separated device IDs).

    Device metadata (name, category, online state) and live status are fetched
    from the Tuya Cloud API at startup and refreshed on demand. Adding a new
    device requires only appending its ID to TUYA_DEVICE_IDS — no code changes.
    """

    def __init__(self, client: TuyaClient):
        self.client = client
        # device_id -> {"info": {...}, "status": {...}}
        self._devices: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self) -> bool:
        """Fetch info + status for all configured device IDs. Returns True on success."""
        raw = os.getenv("TUYA_DEVICE_IDS", "")
        device_ids = [d.strip() for d in raw.split(",") if d.strip()]
        if not device_ids:
            return False
        if not self.client.ensure_connected():
            return False
        self._devices = {}
        for device_id in device_ids:
            self._devices[device_id] = {
                "info": self._fetch_info(device_id),
                "status": self._fetch_status(device_id),
            }
        return True

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    def _fetch_info(self, device_id: str) -> dict:
        custom = _load_custom_labels().get(device_id, {})
        res = self.client.request("GET", f"/v1.0/devices/{device_id}")
        if res.get("success"):
            r = res["result"]
            return {
                "id": device_id,
                "name": custom.get("name") or r.get("name", device_id),
                "description": custom.get("description", ""),
                "category": r.get("category", "unknown"),
                "online": r.get("online", False),
            }
        return {
            "id": device_id,
            "name": custom.get("name", device_id),
            "description": custom.get("description", ""),
            "category": "unknown",
            "online": False,
        }

    def _fetch_status(self, device_id: str) -> dict:
        res = self.client.request("GET", f"/v1.0/devices/{device_id}/status")
        if res.get("success"):
            status = {item["code"]: item["value"] for item in res["result"]}
            return _normalize_brightness(status)
        return {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh_status(self) -> dict[str, dict]:
        """Re-fetch live status for all devices and return a snapshot."""
        if not self.client.ensure_connected():
            return {}
        for device_id in self._devices:
            self._devices[device_id]["status"] = self._fetch_status(device_id)
        return self.snapshot()

    def snapshot(self) -> dict[str, dict]:
        """Return current in-memory state: {device_id: {info, status}}."""
        return {k: dict(v) for k, v in self._devices.items()}

    def control(self, device_id: str, commands: list[dict]) -> dict:
        """
        Send commands to a device.
        commands example: [{"code": "switch_led", "value": True}]
        """
        if not self.client.ensure_connected():
            return {"success": False, "msg": "Falha na autenticação"}
        return self.client.request(
            "POST", f"/v1.0/devices/{device_id}/commands", {"commands": commands}
        )

    def find_by_name(self, fragment: str) -> tuple[str, dict] | None:
        """Find a device whose name contains the given fragment (case-insensitive)."""
        fragment = fragment.lower()
        for device_id, data in self._devices.items():
            if fragment in data["info"]["name"].lower():
                return device_id, data
        return None

    # ------------------------------------------------------------------
    # Context for the LLM
    # ------------------------------------------------------------------

    def build_context(self) -> str:
        """
        Build a text block describing every registered device and its live state.
        Called before each LLM invocation so the model always has current data.
        """
        if not self._devices:
            return "Nenhum dispositivo configurado em TUYA_DEVICE_IDS."

        lines = ["Dispositivos registrados e estado atual:"]
        for device_id, data in self._devices.items():
            info = data["info"]
            status = data["status"]
            online = "online" if info.get("online") else "offline"
            status_str = json.dumps(status, ensure_ascii=False) if status else "indisponível"
            desc = f" | descrição={info['description']}" if info.get("description") else ""
            lines.append(
                f"  - {info['name']}{desc} | id={device_id} | categoria={info['category']}"
                f" | {online} | estado={status_str}"
            )

        lines.append(
            "\nPara controlar um dispositivo use registry.control(device_id, commands)."
        )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def devices(self) -> dict[str, dict]:
        return self._devices
