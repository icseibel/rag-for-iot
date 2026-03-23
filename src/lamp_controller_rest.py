import time
import hmac
import hashlib
import requests
import os
from dotenv import load_dotenv

load_dotenv()

# Configs
# ACCESS_ID="4uw75yppgjvkdyuhckfd"
# ACCESS_KEY="592169ccad534d2e870b02272188a996"

ACCESS_ID = os.getenv("TUYA_ACCESS_ID")
ACCESS_KEY = os.getenv("TUYA_ACCESS_KEY")
ENDPOINT = "https://openapi.tuyaus.com" # Western America
DEVICE_ID = "ebc84326c1546a8d72mp5b"

def calculate_sign(msg, key):
    return hmac.new(
        key.encode('utf-8'),
        msg.encode('utf-8'),
        hashlib.sha256
    ).hexdigest().upper()

def get_tuya_headers(path, method="GET", body=""):
    """Tuya Signature V2 Logic"""
    t = str(int(time.time() * 1000))
    # For token request, access_token is empty
    # For command requests, you'd append the token here (simplified for login)
    
    # 1. Create content-sha256 of the body
    content_sha256 = hashlib.sha256(body.encode('utf-8')).hexdigest()
    
    # 2. String to sign (Concatenate method, content_sha256, headers, path)
    string_to_sign = f"{method}\n{content_sha256}\n\n{path}"
    
    # 3. Final message: ACCESS_ID + t + string_to_sign
    msg = ACCESS_ID + t + string_to_sign
    sign = calculate_sign(msg, ACCESS_KEY)
    
    return {
        "client_id": ACCESS_ID,
        "sign": sign,
        "t": t,
        "sign_method": "HMAC-SHA256",
        "Content-Type": "application/json"
    }

def get_token():
    path = "/v1.0/token?grant_type=1"
    headers = get_tuya_headers(path, "GET")
    url = f"{ENDPOINT}{path}"
    
    response = requests.get(url, headers=headers)
    return response.json()

# Implementation of the control logic
def send_command(token, turn_on=True):
    path = f"/v1.0/devices/{DEVICE_ID}/commands"
    method = "POST"
    
    # Body must be string for signature
    import json
    payload = json.dumps({"commands": [{"code": "switch_led", "value": turn_on}]})
    print(f"Payload for command: {payload}")
    
    # Re-calculate sign with Token
    t = str(int(time.time() * 1000))
    content_sha256 = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    string_to_sign = f"{method}\n{content_sha256}\n\n{path}"
    
    msg = ACCESS_ID + token + t + string_to_sign
    sign = calculate_sign(msg, ACCESS_KEY)
    
    headers = {
        "client_id": ACCESS_ID,
        "access_token": token,
        "sign": sign,
        "t": t,
        "sign_method": "HMAC-SHA256",
        "Content-Type": "application/json"
    }
    
    url = f"{ENDPOINT}{path}"
    return requests.post(url, headers=headers, data=payload).json()

if __name__ == "__main__":
    token_res = get_token()
    if token_res.get("success"):
        token = token_res["result"]["access_token"]
        print(f"Token obtained! Controlling lamp...")
        print(send_command(token, turn_on=False))