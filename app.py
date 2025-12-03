import json
from datetime import datetime, date
from zoneinfo import ZoneInfo
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build

# -----------------------------
# CONFIGURACIÓN DE STREAMLIT
# -----------------------------
st.set_page_config(page_title="Control de Estudio con Canje", page_icon="⏳", layout="centered")

# -----------------------------
# CARGA DE CREDENCIALES GOOGLE
# -----------------------------
try:
    key_dict = json.loads(st.secrets["textkey"])
    creds = service_account.Credentials.from_service_account_info(
        key_dict,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
except KeyError:
    st.error("Falta configurar el secreto 'textkey'.")
    st.stop()

service = build("sheets", "v4", credentials=creds)
sheet = service.spreadsheets()

SHEET_ID = st.secrets["sheet_id"]

# -----------------------------
# CONFIG ZONA HORARIA
# -----------------------------
TZ = ZoneInfo("America/Argentina/Cordoba")

def ahora_str():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

def parse_datetime(s):
    if not s or s.strip() == "":
        return None
    return datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)

# -----------------------------
# FILAS POR FECHA
# -----------------------------
FILA_BASE = 170
FECHA_BASE = date(2025, 12, 2)  # fila 170 = 2/12/2025

def fila_para_fecha(fecha_actual):
    return FILA_BASE + (fecha_actual - FECHA_BASE).days

hoy = date.today()
TIME_ROW = fila_para_fecha(hoy)
MARCAS_ROW = 2  # fila fija para marcas de inicio

# -----------------------------
# HOJAS
# -----------------------------
SHEET_FACUNDO = "F. Economía"
SHEET_IVAN = "I. Física"
SHEET_MARCAS = "marcas"

# -----------------------------
# USUARIOS Y MATERIAS
# -----------------------------
USERS = {
    "Facundo": {
        "Matemática para Economistas 1": {"time": f"'{SHEET_FACUNDO}'!B{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!B{MARCAS_ROW}"},
        "Matemática para Economistas 2": {"time": f"'{SHEET_FACUNDO}'!C{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!C{MARCAS_ROW}"},
        "Macroeconomía 1": {"time": f"'{SHEET_FACUNDO}'!D{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!D{MARCAS_ROW}"},
        "Historia": {"time": f"'{SHEET_FACUNDO}'!E{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!E{MARCAS_ROW}"},
    },
    "Iván": {
        "Física": {"time": f"'{SHEET_IVAN}'!B{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!F{MARCAS_ROW}"},
        "Análisis": {"time": f"'{SHEET_IVAN}'!C{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!G{MARCAS_ROW}"},
    }
}

# -----------------------------
# CONFIG CANJE DIARIO
# -----------------------------
MAX_CANJE = 500  # pesos máximo diario
PRECIO_PUNTOS_INICIAL = 180  # minutos por $500
MIN_PRECIO = 180
MAX_PRECIO = 360

# -----------------------------
# FUNCIONES DE CONVERSIÓN
# -----------------------------
def hms_a_segundos(hms):
    if not hms or hms.strip() == "":
        return 0
    h, m, s = map(int, hms.split(":"))
    return h*3600 + m*60 + s

def segundos_a_hms(seg):
    h = seg // 3600
    m = (seg % 3600) // 60
    s = seg % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def minutos_a_pesos(minutos, precio_puntos):
    tasa = 500 / precio_puntos
    return round(minutos * tasa, 2)

def hms_a_minutos(hms):
    return hms_a_segundos(hms) / 60

# -----------------------------
# FUNCIONES GOOGLE SHEETS
# -----------------------------
def batch_write(updates):
    body = {"valueInputOption": "USER_ENTERED", "data":[{"range": r, "values":[[v]]} for r,v in updates]}
    sheet.values().batchUpdate(spreadsheetId=SHEET_ID, body=body).execute()

def cargar_todo():
    ranges = []
    for user, materias in USERS.items():
        for m, info in materias.items():
            ranges.append(info["est"])
            ranges.append(info["time"])
    res = sheet.values().batchGet(spreadsheetId=SHEET_ID, ranges=ranges, valueRenderOption="FORMATTED_VALUE").execute()
    values = res.get("valueRanges", [])
    data = {u: {"estado": {}, "tiempos": {}} for u in USERS}
    idx = 0
    for user, materias in USERS.items():
        for materia, info in materias.items():
            est_val = values[idx].get("values",[[]])
            est_val = est_val[0][0] if est_val and est_val[0] else ""
            idx += 1
            time_val = values[idx].get("values",[[]])
            time_val = time_val[0][0] if time_val and time_val[0] else "00:00:00"
            idx +=1
            data[user]["estado"][materia] = est_val
            data[user]["tiempos"][materia] = time_val
    return data

# -----------------------------
# FUNCION PASAR DIA
# -----------------------------
def pasar_dia_usuario(usuario, data_usuario):
    """
    Convierte los minutos del día a pesos y ajusta precio_puntos
    """
    # 1. Sumar minutos de todas las materias
    minutos_dia = sum(hms_a_minutos(t) for t in data_usuario["tiempos"].values())

    # 2. Leer valores previos de marcas
    range_precio = f"'{SHEET_MARCAS}'!{usuario}_precio"  # puede ser celda definida por usuario
    range_pesos = f"'{SHEET_MARCAS}'!{usuario}_pesos"

    # Por simplicidad guardamos en st.session_state
    precio_puntos = st.session_state.get(f"{usuario}_precio", PRECIO_PUNTOS_INICIAL)
    pesos_acum = st.session_state.get(f"{usuario}_pesos", 0)

    pesos_obtenidos = minutos_a_pesos(minutos_dia, precio_puntos)
    pesos_permitidos = min(pesos_obtenidos, MAX_CANJE)
    pesos_no_canjeados = pesos_obtenidos - pesos_permitidos

    # Ajuste precio_puntos
    if pesos_permitidos < MAX_CANJE:
        precio_puntos = max(precio_puntos - max((MAX_CANJE - pesos_permitidos) * 0.1, 10), MIN_PRECIO)
    else:
        precio_puntos = min(precio_puntos + max((pesos_permitidos - MAX_CANJE) * 0.3, 10), MAX_PRECIO)

    # Guardar en session_state
    st.session_state[f"{usuario}_precio"] = round(precio_puntos)
    st.session_state[f"{usuario}_pesos"] = pesos_acum + pesos_permitidos

    # Reset tiempos del día
    for m in data_usuario["tiempos"].keys():
        batch_write([(USERS[usuario][m]["time"], "00:00:00")])

# -----------------------------
# SELECCIÓN DE USUARIO
# -----------------------------
if "usuario_seleccionado" not in st.session_state:
    st.title("¿Quién sos? 👤")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Soy Facundo"):
            st.session_state["usuario_seleccionado"] = "Facundo"
            st.rerun()
    with col2:
        if st.button("Soy Iván"):
            st.session_state["usuario_seleccionado"] = "Iván"
            st.rerun()
    st.stop()

USUARIO_ACTUAL = st.session_state["usuario_seleccionado"]
if st.sidebar.button("Cambiar usuario"):
    del st.session_state["usuario_seleccionado"]
    st.rerun()

# -----------------------------
# INTERFAZ PRINCIPAL
# -----------------------------
st.title("⏳ Control de Estudio con Canje")

datos = cargar_todo()

# -----------------------------
# Detectar paso de día
# -----------------------------
FECHA_KEY = "ultima_fecha"
if FECHA_KEY not in st.session_state:
    st.session_state[FECHA_KEY] = hoy

if st.session_state[FECHA_KEY] < hoy:
    for usuario in USERS.keys():
        pasar_dia_usuario(usuario, datos[usuario])
    st.session_state[FECHA_KEY] = hoy
    st.rerun()

# -----------------------------
# Mostrar materias y tiempos
# -----------------------------
st.subheader(f"👤 {USUARIO_ACTUAL}")

mis_materias = USERS[USUARIO_ACTUAL]
materia_en_curso = None
for m, info in mis_materias.items():
    if datos[USUARIO_ACTUAL]["estado"][m].strip() != "":
        materia_en_curso = m
        break

for materia, info in mis_materias.items():
    tiempo = datos[USUARIO_ACTUAL]["tiempos"][materia]
    est = datos[USUARIO_ACTUAL]["estado"][materia]
    tiempo_seg = hms_a_segundos(tiempo)
    tiempo_total_hms = segundos_a_hms(tiempo_seg)
    st.markdown(f"**{materia}** - {tiempo_total_hms}")

    b1, b2 = st.columns([0.2, 0.2])
    with b1:
        if st.button("▶", key=f"est_{materia}"):
            # iniciar estudio
            batch_write([(info["est"], ahora_str())])
            st.rerun()
    with b2:
        if st.button("⛔", key=f"det_{materia}"):
            # detener estudio y acumular minutos
            if est.strip() != "":
                inicio = parse_datetime(est)
                diff = int((datetime.now(TZ) - inicio).total_seconds())
                tiempo_total = tiempo_seg + diff
                batch_write([(info["time"], segundos_a_hms(tiempo_total)), (info["est"], "")])
                st.rerun()

# -----------------------------
# Mostrar pesos acumulados
# -----------------------------
st.subheader("💰 Canje y pesos acumulados")
for usuario in USERS.keys():
    precio = st.session_state.get(f"{usuario}_precio", PRECIO_PUNTOS_INICIAL)
    pesos = st.session_state.get(f"{usuario}_pesos", 0)
    st.write(f"{usuario}: ${pesos} acumulados | Precio puntos: {precio} minutos/$500")

