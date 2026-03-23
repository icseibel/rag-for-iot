import time
import hmac
import hashlib
import requests
import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=True)


class TuyaTouchSwitchTool:
    def __init__(self):
        self.access_id = os.getenv("TUYA_ACCESS_ID")
        self.access_key = os.getenv("TUYA_ACCESS_KEY")
        self.endpoint = os.getenv("TUYA_API_ENDPOINT", "https://openapi.tuyaus.com")
        self.device_id = os.getenv("TUYA_TOUCH_SWITCH_DEVICE_ID", "eb9ee8a187397e9f33l8iw")
        self.token = None

    def _generate_sign(self, method, path, body=""):
        t = str(int(time.time() * 1000))
        content_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
        string_to_sign = f"{method}\n{content_sha256}\n\n{path}"
        msg = self.access_id + (self.token if self.token else "") + t + string_to_sign
        sign = hmac.new(
            self.access_key.encode("utf-8"),
            msg.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest().upper()
        return sign, t

    def _request(self, method, path, body=None):
        url = f"{self.endpoint}{path}"
        payload = json.dumps(body) if body else ""
        sign, t = self._generate_sign(method, path, payload)

        headers = {
            "client_id": self.access_id,
            "sign": sign,
            "t": t,
            "sign_method": "HMAC-SHA256",
            "Content-Type": "application/json",
        }
        if self.token:
            headers["access_token"] = self.token

        response = requests.request(method, url, headers=headers, data=payload)
        return response.json()

    def connect(self):
        path = "/v1.0/token?grant_type=1"
        res = self._request("GET", path)
        if res.get("success"):
            self.token = res["result"]["access_token"]
            return True
        return False

    def get_status(self):
        path = f"/v1.0/devices/{self.device_id}/status"
        res = self._request("GET", path)
        if res.get("success"):
            return {item["code"]: item["value"] for item in res["result"]}
        return res

    def control(self, turn_on=True, channel=1):
        path = f"/v1.0/devices/{self.device_id}/commands"
        payload = {"commands": [{"code": f"switch_{channel}", "value": turn_on}]}
        return self._request("POST", path, payload)

    def toggle(self, channel=1):
        status = self.get_status()
        if not isinstance(status, dict) or status.get("success") is False:
            return status
        current_value = bool(status.get(f"switch_{channel}", False))
        return self.control(turn_on=not current_value, channel=channel)
