import tinytuya
import sys

# --- CONFIGURAÇÕES ---
# Use o prefixo 'r' para garantir que caracteres como ':' e '}' sejam lidos corretamente
DEVICE_ID = 'ebc84326c1546a8d72mp5b'
LOCAL_KEY = r'NY9c:b&jh}t}Wt[0'
IP_ADDRESS = '192.168.1.28'  # <--- CERTIFIQUE-SE QUE O IP ESTÁ CORRETO

# Inicializa como BulbDevice
lamp = tinytuya.BulbDevice(DEVICE_ID, IP_ADDRESS, LOCAL_KEY)

def try_command(action):
    # Versões para testar: 3.3 é a mais comum, 3.1 para antigas, 3.4/3.5 para novas
    versions = [3.3, 3.1, 3.4, 3.5]
    
    success = False
    for v in versions:
        print(f"[*] Tentando protocolo versão {v}...")
        lamp.set_version(v)
        
        # Tenta obter o status antes de enviar o comando
        status = lamp.status()
        
        if 'Error' not in status:
            print(f"[✓] Conectado com sucesso usando a versão {v}!")
            if action == "on":
                lamp.turn_on()
                print("[✓] Lâmpada ligada.")
            else:
                lamp.turn_off()
                print("[✓] Lâmpada desligada.")
            success = True
            break
        else:
            print(f"[!] Falha na versão {v}: {status.get('Error')}")

    if not success:
        print("\n[!] Não foi possível conectar. Verifique:")
        print("1. Se o IP da lâmpada mudou (tente rodar 'python -m tinytuya scan').")
        print("2. Se o seu computador e a lâmpada estão no MESMO Wi-Fi (2.4GHz).")
        print("3. Se o firewall do Windows está bloqueando conexões de saída.")

if __name__ == "__main__":
    action_input = sys.argv[1] if len(sys.argv) > 1 else "on"
    try_command(action_input)