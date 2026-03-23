import hashlib
import hmac
import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=True)


class TuyaClient:
    """Shared Tuya Cloud API client (auth + signed requests)."""

    def __init__(self):
        self.access_id = os.getenv("TUYA_ACCESS_ID")
        self.access_key = os.getenv("TUYA_ACCESS_KEY")
        self.endpoint = os.getenv("TUYA_API_ENDPOINT", "https://openapi.tuyaus.com")
        self.token = None

    def _generate_sign(self, method: str, path: str, body: str = "") -> tuple[str, str]:
        t = str(int(time.time() * 1000))
        content_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
        string_to_sign = f"{method}\n{content_sha256}\n\n{path}"
        msg = self.access_id + (self.token or "") + t + string_to_sign
        sign = hmac.new(
            self.access_key.encode("utf-8"),
            msg.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest().upper()
        return sign, t

    def request(self, method: str, path: str, body=None) -> dict:
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
        return requests.request(method, url, headers=headers, data=payload).json()

    def connect(self) -> bool:
        res = self.request("GET", "/v1.0/token?grant_type=1")
        if res.get("success"):
            self.token = res["result"]["access_token"]
            return True
        return False

    def ensure_connected(self) -> bool:
        if not self.token:
            return self.connect()
        return True
