import time
import hmac
import hashlib
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

class TuyaCloudTool:
    def __init__(self):
        self.access_id = os.getenv("TUYA_ACCESS_ID")
        self.access_key = os.getenv("TUYA_ACCESS_KEY")
        self.endpoint = "https://openapi.tuyaus.com"
        self.device_id = os.getenv("TUYA_LAMP_DEVICE_ID", "ebc84326c1546a8d72mp5b")
        self.token = None

    def _generate_sign(self, method, path, body=""):
        """Implementação manual da assinatura HMAC-SHA256 da Tuya v2.0"""
        t = str(int(time.time() * 1000))
        content_sha256 = hashlib.sha256(body.encode('utf-8')).hexdigest()
        string_to_sign = f"{method}\n{content_sha256}\n\n{path}"
        
        # A mensagem muda se houver token ou não
        msg = self.access_id + (self.token if self.token else "") + t + string_to_sign
        sign = hmac.new(
            self.access_key.encode('utf-8'),
            msg.encode('utf-8'),
            hashlib.sha256
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
            "Content-Type": "application/json"
        }
        if self.token:
            headers["access_token"] = self.token

        response = requests.request(method, url, headers=headers, data=payload)
        return response.json()

    def connect(self):
        """Obtém o token de acesso (OAuth2)"""
        path = "/v1.0/token?grant_type=1"
        res = self._request("GET", path)
        if res.get("success"):
            self.token = res["result"]["access_token"]
            return True
        return False

    def get_status(self):
        """Retorna o status formatado para o usuário ou LLM"""
        path = f"/v1.0/devices/{self.device_id}/status"
        res = self._request("GET", path)
        if res.get("success"):
            status_map = {item['code']: item['value'] for item in res['result']}
            # Normaliza o brilho (Tuya 10-1000 -> 0-100%)
            raw_bright = status_map.get('bright_value_v2', 0)
            status_map['brightness_percent'] = round((raw_bright / 1000) * 100)
            return status_map
        return res

    def control(self, turn_on=True):
        """Acende ou apaga a lâmpada"""
        path = f"/v1.0/devices/{self.device_id}/commands"
        payload = {"commands": [{"code": "switch_led", "value": turn_on}]}
        return self._request("POST", path, payload)

    def get_consumption(self):
        """Busca estatísticas de energia acumulada (se disponível)"""
        # Estatística total acumulada
        path = f"/v1.0/devices/{self.device_id}/statistics/total"
        return self._request("GET", path)

# --- Exemplo de Uso Prático ---2
if __name__ == "__main__":
    lamp = TuyaCloudTool()
    
    if lamp.connect():
        print("[1] Lâmpada conectada!")
        
        # Consultar Status
        status = lamp.get_status()
        print(f"Status Atual: {'Ligada' if status['switch_led'] else 'Desligada'}")
        print(f"Brilho: {status['brightness_percent']}%")

        # Acender/Apagar (Exemplo: Inverter o estado atual)
        # new_state = not status['switch_led']
        # print(f"[2] Alterando estado para: {new_state}")
        # lamp.control(turn_on=new_state)

        # Consultar Consumo
        energy = lamp.get_consumption()
        print(f"[3] Dados de Energia: {energy.get('result', 'Não suportado pelo hardware')}")
    else:
        print("[!] Erro de autenticação. Verifique as chaves no .env")