"""
Tests for tuya_client.py.

Stubs injected by test_app_rag.py are evicted from sys.modules before the
real module is imported so these tests always operate on the production code.
"""
import hashlib
import hmac
import json
import sys
from unittest.mock import MagicMock, patch

import pytest

# Evict any stubs that test_app_rag.py may have registered first
sys.modules.pop("tuya_client", None)

with patch("dotenv.load_dotenv"):
    from tuya_client import TuyaClient


@pytest.fixture
def client():
    with patch("dotenv.load_dotenv"):
        c = TuyaClient()
    c.access_id = "test_id"
    c.access_key = "test_key"
    c.endpoint = "https://openapi.tuyaus.com"
    c.token = None
    return c


class TestGenerateSign:
    def test_returns_uppercase_hex_and_timestamp(self, client):
        sign, t = client._generate_sign("GET", "/v1.0/token?grant_type=1")
        assert sign == sign.upper()
        assert t.isdigit()

    def test_sign_changes_with_different_body(self, client):
        with patch("time.time", return_value=1700000000.0):
            sign_empty, _ = client._generate_sign("POST", "/v1.0/devices/abc/commands", "")
            sign_body, _ = client._generate_sign(
                "POST", "/v1.0/devices/abc/commands", '{"commands":[]}'
            )
        assert sign_empty != sign_body

    def test_sign_changes_with_token(self, client):
        with patch("time.time", return_value=1700000000.0):
            sign_no_token, _ = client._generate_sign("GET", "/v1.0/devices/abc")
        client.token = "mytoken"
        with patch("time.time", return_value=1700000000.0):
            sign_with_token, _ = client._generate_sign("GET", "/v1.0/devices/abc")
        assert sign_no_token != sign_with_token

    def test_sign_is_deterministic_for_same_timestamp(self, client):
        with patch("time.time", return_value=1700000000.0):
            sign1, t1 = client._generate_sign("GET", "/v1.0/devices/abc")
            sign2, t2 = client._generate_sign("GET", "/v1.0/devices/abc")
        assert sign1 == sign2
        assert t1 == t2

    def test_sign_matches_manual_hmac_calculation(self, client):
        with patch("time.time", return_value=1700000000.0):
            sign, t = client._generate_sign("GET", "/v1.0/devices/abc")

        content_sha256 = hashlib.sha256(b"").hexdigest()
        string_to_sign = f"GET\n{content_sha256}\n\n/v1.0/devices/abc"
        msg = "test_id" + "" + t + string_to_sign
        expected = hmac.new(
            b"test_key", msg.encode("utf-8"), hashlib.sha256
        ).hexdigest().upper()
        assert sign == expected


class TestRequest:
    def test_sends_required_headers(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        with patch("requests.request", return_value=mock_response) as mock_req:
            client.request("GET", "/v1.0/devices/abc")
            headers = mock_req.call_args.kwargs["headers"]
            assert headers["client_id"] == "test_id"
            assert headers["sign_method"] == "HMAC-SHA256"
            assert "access_token" not in headers

    def test_includes_access_token_when_set(self, client):
        client.token = "mytoken"
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        with patch("requests.request", return_value=mock_response) as mock_req:
            client.request("GET", "/v1.0/devices/abc")
            assert mock_req.call_args.kwargs["headers"]["access_token"] == "mytoken"

    def test_serializes_body_as_json(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        body = {"commands": [{"code": "switch_led", "value": True}]}
        with patch("requests.request", return_value=mock_response) as mock_req:
            client.request("POST", "/v1.0/devices/abc/commands", body)
            assert json.loads(mock_req.call_args.kwargs["data"]) == body

    def test_sends_empty_string_body_when_none(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        with patch("requests.request", return_value=mock_response) as mock_req:
            client.request("GET", "/v1.0/devices/abc")
            assert mock_req.call_args.kwargs["data"] == ""


class TestConnect:
    def test_stores_token_on_success(self, client):
        with patch.object(
            client, "request",
            return_value={"success": True, "result": {"access_token": "tok123"}}
        ):
            assert client.connect() is True
            assert client.token == "tok123"

    def test_returns_false_on_failure(self, client):
        with patch.object(client, "request", return_value={"success": False, "msg": "invalid"}):
            assert client.connect() is False
            assert client.token is None


class TestEnsureConnected:
    def test_calls_connect_when_no_token(self, client):
        with patch.object(client, "connect", return_value=True) as mock_connect:
            assert client.ensure_connected() is True
            mock_connect.assert_called_once()

    def test_skips_connect_when_token_exists(self, client):
        client.token = "existing"
        with patch.object(client, "connect") as mock_connect:
            assert client.ensure_connected() is True
            mock_connect.assert_not_called()
