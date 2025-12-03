import json
from google.oauth2 import service_account
import streamlit as st
from googleapiclient.discovery import build
from datetime import datetime, date
from zoneinfo import ZoneInfo

# -------------------------------------------------------------------
# CONFIGURACIÓN STREAMLIT
# -------------------------------------------------------------------
st.set_page_config(
    page_title="Control de Estudio",
    page_icon="⏳",
    layout="centered"
)

# -------------------------------------------------------------------
# CARGA DE CREDENCIALES
# -------------------------------------------------------------------
try:
    key_dict = json.loads(st.secrets["textkey"])
    creds = service_account.Credentials.from_service_account_info(
        key_dict,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
except KeyError:
    st.error("Error: Falta configurar el secreto 'textkey'.")
    st.stop()

service = build("sheets", "v4", credentials=creds)
sheet = service.spreadsheets()

# -------------------------------------------------------------------
# ZONA HORARIA ARGENTINA
# -------------------------------------------------------------------
TZ = ZoneInfo("America/Argentina/Cordoba")

def ahora_str():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

def parse_datetime(s):
    if not s or str(s).strip() == "":
        raise ValueError("Marca vacía")
    s = str(s).strip().lstrip("'")
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S%z")
        return dt.astimezone(TZ)
    except:
        pass
    dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    return dt.replace(tzinfo=TZ)

# -------------------------------------------------------------------
# FILA DINÁMICA SEGÚN FECHA
# -------------------------------------------------------------------
FILA_BASE = 170
FECHA_BASE = date(2025, 12, 2)

def fila_para_fecha(fecha_actual):
    delta = (fecha_actual - FECHA_BASE).days
    return FILA_BASE + delta

hoy = date.today()
TIME_ROW = fila_para_fecha(hoy)
MARCAS_ROW = 2

# -------------------------------------------------------------------
# HOJAS
# -------------------------------------------------------------------
SHEET_FACUNDO = "F. Economía"
SHEET_IVAN = "I. Física"
SHEET_MARCAS = "marcas"

# -------------------------------------------------------------------
# COLUMNAS PARA PESOS DIARIOS
# -------------------------------------------------------------------
PESOS_COLS = {"Facundo": "H", "Iván": "I"}

# -------------------------------------------------------------------
# COLUMNAS DE ESTADO PERSISTENTE EN 'marcas'
# -------------------------------------------------------------------
STATE_COLS = {
    "Facundo": {
        "precio_puntos": "J",
        "puntos": "K",
        "pesos_acumulados": "L",
        "canje_del_dia": "M",
        "puntos_canjeados_hoy": "N",
    },
    "Iván": {
        "precio_puntos": "J",
        "puntos": "K",
        "pesos_acumulados": "L",
        "canje_del_dia": "M",
        "puntos_canjeados_hoy": "N",
    }
}

# -------------------------------------------------------------------
# CLASE Persona
# -------------------------------------------------------------------
class Persona:
    def __init__(self, nombre):
        self.nombre = nombre
        self.precio_puntos = 180
        self.max_puntos = 360
        self.min_puntos = 180
        self.max_canje_valor = 1000
        self.puntos = 0
        self.puntos_canjeados_hoy = 0
        self.pesos_acumulados = 0.0
        self.canje_del_dia = 0.0

    def max_canje(self, pesos_a_canjear):
        espacio = self.max_canje_valor - self.canje_del_dia
        if espacio <= 0: return 0.0
        return round(min(pesos_a_canjear, espacio), 2)

    def pasar_dia(self):
        tasa = 500.0 / self.precio_puntos
        pesos_obtenidos = round(self.puntos * tasa, 2)
        pesos_permitidos = self.max_canje(pesos_obtenidos)
        self.pesos_acumulados = round(self.pesos_acumulados + pesos_permitidos, 2)
        self.canje_del_dia += pesos_permitidos
        pesos_no_canjeados = round(pesos_obtenidos - pesos_permitidos, 2)
        self.puntos = int(round(pesos_no_canjeados / tasa)) if pesos_no_canjeados > 0 else 0
        if self.canje_del_dia < 500:
            dec = max((self.precio_puntos - self.puntos_canjeados_hoy) * 0.1, 10)
            self.precio_puntos = max(self.precio_puntos - dec, self.min_puntos)
        elif self.canje_del_dia > 500:
            inc = max((self.puntos_canjeados_hoy - self.precio_puntos) * 0.3, 10)
            self.precio_puntos = min(self.precio_puntos + inc, self.max_puntos)
        return pesos_permitidos, pesos_no_canjeados

# -------------------------------------------------------------------
# MATERIAS POR USUARIO
# -------------------------------------------------------------------
USERS = {
    "Iván": {
        "Física": {"time": f"'{SHEET_IVAN}'!B{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!F{MARCAS_ROW}"},
        "Análisis": {"time": f"'{SHEET_IVAN}'!C{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!G{MARCAS_ROW}"},
    },
    "Facundo": {
        "Matemática para Economistas 1": {"time": f"'{SHEET_FACUNDO}'!B{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!B{MARCAS_ROW}"},
        "Matemática para Economistas 2": {"time": f"'{SHEET_FACUNDO}'!C{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!C{MARCAS_ROW}"},
        "Macroeconomía 1": {"time": f"'{SHEET_FACUNDO}'!D{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!D{MARCAS_ROW}"},
        "Historia": {"time": f"'{SHEET_FACUNDO}'!E{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!E{MARCAS_ROW}"},
    }
}

# -------------------------------------------------------------------
# FUNCIONES TIEMPO
# -------------------------------------------------------------------
def hms_a_segundos(hms):
    if not hms: return 0
    s = str(hms).strip().lstrip("'")
    if s == "": return 0
    parts = [int(p) for p in s.split(":")]
    if len(parts) == 3: h, m, sec = parts
    elif len(parts) == 2: h, m, sec = 0, parts[0], parts[1]
    else: return 0
    return h*3600 + m*60 + sec

def segundos_a_hms(seg):
    h = seg // 3600
    m = (seg % 3600) // 60
    s = seg % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def hms_a_fraction(hms):
    return hms_a_segundos(hms)/86400.0

# -------------------------------------------------------------------
# LECTURA Y ESCRITURA GOOGLE SHEETS
# -------------------------------------------------------------------
def cargar_todo():
    sheet_id = st.secrets["sheet_id"]
    ranges = []
    for user, materias in USERS.items():
        for m, info in materias.items():
            ranges.append(info["est"])
            ranges.append(info["time"])
    res = sheet.values().batchGet(spreadsheetId=sheet_id, ranges=ranges, valueRenderOption="FORMATTED_VALUE").execute()
    values = res.get("valueRanges", [])
    data = {u: {"estado": {}, "tiempos": {}} for u in USERS}
    idx = 0
    for user, materias in USERS.items():
        for materia, info in materias.items():
            est_val = values[idx].get("values", [[]])[0][0] if values[idx].get("values") else ""
            est_val = str(est_val).lstrip("'")
            idx +=1
            time_val = values[idx].get("values", [[]])[0][0] if values[idx].get("values") else "00:00:00"
            time_val = str(time_val).lstrip("'")
            idx +=1
            data[user]["estado"][materia] = est_val
            data[user]["tiempos"][materia] = time_val
    return data

def batch_write(updates):
    sheet_id = st.secrets["sheet_id"]
    body = {"valueInputOption": "USER_ENTERED","data":[{"range": r,"values":[[v]]} for r,v in updates]}
    sheet.values().batchUpdate(spreadsheetId=sheet_id, body=body).execute()

# -------------------------------------------------------------------
# CARGAR PERSONAS DESDE MARCAS
# -------------------------------------------------------------------
def cargar_personas():
    personas = {}
    sheet_id = st.secrets["sheet_id"]
    for nombre in ["Facundo","Iván"]:
        cols = STATE_COLS[nombre]
        ranges = [f"'{SHEET_MARCAS}'!{c}{TIME_ROW}" for c in cols.values()]
        res = sheet.values().batchGet(spreadsheetId=sheet_id, ranges=ranges, valueRenderOption="FORMATTED_VALUE").execute()
        vals = res.get("valueRanges",[])
        p = Persona(nombre)
        p.precio_puntos = float(vals[0].get("values",[["180"]])[0][0])
        p.puntos = int(vals[1].get("values",[["0"]])[0][0])
        p.pesos_acumulados = float(vals[2].get("values",[["0"]])[0][0])
        p.canje_del_dia = float(vals[3].get("values",[["0"]])[0][0])
        p.puntos_canjeados_hoy = int(vals[4].get("values",[["0"]])[0][0])
        personas[nombre] = p
    return personas

def guardar_estado(personas):
    updates=[]
    for nombre,p in personas.items():
        cols=STATE_COLS[nombre]
        updates.extend([
            (f"'{SHEET_MARCAS}'!{cols['precio_puntos']}{TIME_ROW}", p.precio_puntos),
            (f"'{SHEET_MARCAS}'!{cols['puntos']}{TIME_ROW}", p.puntos),
            (f"'{SHEET_MARCAS}'!{cols['pesos_acumulados']}{TIME_ROW}", p.pesos_acumulados),
            (f"'{SHEET_MARCAS}'!{cols['canje_del_dia']}{TIME_ROW}", p.canje_del_dia),
            (f"'{SHEET_MARCAS}'!{cols['puntos_canjeados_hoy']}{TIME_ROW}", p.puntos_canjeados_hoy),
        ])
    if updates:
        batch_write(updates)

# -------------------------------------------------------------------
# REGISTRAR PESOS DIARIOS
# -------------------------------------------------------------------
def registrar_pesos_diarios(datos, personas):
    updates=[]
    registros={}
    for nombre,persona in personas.items():
        materias=USERS[nombre]
        total_seg=0
        for materia,info in materias.items():
            total_seg += hms_a_segundos(datos[nombre]["tiempos"][materia])
        minutos=total_seg//60
        persona.puntos += int(minutos)
        pesos, pesos_no = persona.pasar_dia()
        # guardar pesos diarios
        col = PESOS_COLS[nombre]
        rango = f"'{SHEET_MARCAS}'!{col}{TIME_ROW}"
        updates.append((rango,pesos))
        registros[nombre]={"minutos":minutos,"pesos_registrados":pesos,"pesos_no":pesos_no}
    if updates: batch_write(updates)
    guardar_estado(personas)
    return registros

# -------------------------------------------------------------------
# UI: seleccionar usuario
# -------------------------------------------------------------------
if "usuario_seleccionado" not in st.session_state:
    st.title("¿Quién sos? 👤")
    col_u1,col_u2=st.columns(2)
    with col_u1:
        if st.button("Soy Facundo",use_container_width=True):
            st.session_state["usuario_seleccionado"]="Facundo"; st.rerun()
    with col_u2:
        if st.button("Soy Iván",use_container_width=True):
            st.session_state["usuario_seleccionado"]="Iván"; st.rerun()
    st.stop()

USUARIO_ACTUAL = st.session_state["usuario_seleccionado"]
if st.sidebar.button("Cerrar sesión / Cambiar usuario"):
    del st.session_state["usuario_seleccionado"]
    st.rerun()

# -------------------------------------------------------------------
# CARGAR DATOS
# -------------------------------------------------------------------
datos = cargar_todo()
personas = cargar_personas()

st.title("⏳ Control de Estudio con registro de pesos diarios")

if st.button("🔄 Actualizar tiempos"):
    st.rerun()

if st.button("Registrar pesos del día"):
    registros = registrar_pesos_diarios(datos, personas)
    st.success("Pesos diarios registrados en 'marcas'.")
    for nombre,info in registros.items():
        st.write(f"{nombre}: minutos={info['minutos']}, pesos={info['pesos_registrados']}, no canjeados={info['pesos_no']}")
