import time
import json
import requests
import csv
from io import StringIO
from google.oauth2 import service_account
import google.auth.transport.requests
from datetime import datetime, time as dtime
import os

# ================== CONFIGURACIÓN ==================

SERVICE_ACCOUNT_FILE = os.environ.get("SERVICE_ACCOUNT_FILE", "service_account.json")
PROJECT_ID = os.environ.get("PROJECT_ID", "")
CSV_URL = os.environ.get("CSV_URL", "")

USERS = [
    {"name": "Facundo", "token": os.environ.get("USER1_TOKEN", ""), "cell_row": 1, "trigger_value": 3},
    {"name": "Iván", "token": os.environ.get("USER2_TOKEN", ""), "cell_row": 0, "trigger_value": 3},
]

START_HOUR = dtime(8, 0)
END_HOUR   = dtime(22, 0)
# ================== MENSAJES ==================

PROVERB_TITLE = "Proverbios 6"
PROVERB_BODY = (
    "6 ¡Anda, perezoso, fíjate en la hormiga!\n"
    "¡Fíjate en lo que hace, y adquiere sabiduría!\n"
    "7 No tiene quien la mande,\n"
    "ni quien la vigile ni gobierne;\n"
    "8 con todo, en el verano almacena provisiones\n"
    "y durante la cosecha recoge alimentos.\n"
    "9 Perezoso, ¿cuánto tiempo más seguirás acostado?\n"
    "10 Un corto sueño, una breve siesta,\n"
    "un pequeño descanso, cruzado de brazos…\n"
    "11 ¡y te asaltará la pobreza como un bandido,\n"
    "y la escasez como un hombre armado!"
)

INSULT_TITLE = "¿Qué esperás?"
INSULT_BODY = "Tu orgullo tiene que estar en lo que hacés cada día, no en lo que sos."

# ================== ESTADO ==================

user_toggle = {user["name"]: False for user in USERS}
proverb_counter = {user["name"]: 0 for user in USERS}

# ================== FUNCIONES ==================

def is_within_schedule():
    now = datetime.now().time()
    return START_HOUR <= now <= END_HOUR

def get_access_token():
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/firebase.messaging"]
    )
    request = google.auth.transport.requests.Request()
    credentials.refresh(request)
    return credentials.token

def send_notification(access_token, token, title, body):
    url = f"https://fcm.googleapis.com/v1/projects/{PROJECT_ID}/messages:send"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; UTF-8"
    }

    payload = {
        "message": {
            "token": token,
            "notification": {
                "title": title,
                "body": body
            },
            "android": {
                "priority": "HIGH"
            }
        }
    }

    try:
        r = requests.post(url, headers=headers, data=json.dumps(payload))
        print(f"   → Enviado ({r.status_code})")
    except Exception as e:
        print("   → Error enviando:", e)

def check_sheet_and_notify(access_token):
    try:
        r = requests.get(CSV_URL, timeout=10)
        r.raise_for_status()
        rows = list(csv.reader(StringIO(r.text)))

        if not is_within_schedule():
            print("Fuera de horario.")
            return

        print(f"\n--- Revisión {datetime.now().strftime('%H:%M:%S')} ---")

        for user in USERS:
            name = user["name"]
            row_idx = user["cell_row"]
            trigger = user["trigger_value"]

            if len(rows) <= row_idx:
                continue

            current_val = rows[row_idx][0].strip()
            print(f"{name}: {current_val}")

            # ========= ES MENOR O IGUAL AL TRIGGER → alterna cada 30 min =========
            if int(float(current_val)) <= trigger:
                if user_toggle[name]:
                    send_notification(
                        access_token,
                        user["token"],
                        INSULT_TITLE,
                        INSULT_BODY
                    )
                else:
                    send_notification(
                        access_token,
                        user["token"],
                        PROVERB_TITLE,
                        PROVERB_BODY
                    )

                user_toggle[name] = not user_toggle[name]
                proverb_counter[name] = 0

            # ========= NO ES CERO → proverbio cada 2 horas =========
            else:
                proverb_counter[name] += 1
                if proverb_counter[name] >= 4:
                    send_notification(
                        access_token,
                        user["token"],
                        PROVERB_TITLE,
                        PROVERB_BODY
                    )
                    proverb_counter[name] = 0

    except Exception as e:
        print("Error:", e)

# ================== MAIN ==================

if __name__ == "__main__":
    print("📡 Monitor iniciado")

    token = get_access_token()
    check_sheet_and_notify(token)
