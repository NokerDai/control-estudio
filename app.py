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
# CARGA DE MARKDOWN DESDE SECRETS
# -------------------------------------------------------------------
MD_FACUNDO = st.secrets["md"]["facundo"]
MD_IVAN = st.secrets["md"]["ivan"]

# -------------------------------------------------------------------
# CARGA DE CREDENCIALES GOOGLE
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
# ZONA HORARIA
# -------------------------------------------------------------------
TZ = ZoneInfo("America/Argentina/Cordoba")

def ahora_str():
    return datetime.now(TZ).isoformat(sep=" ", timespec="seconds")

def parse_datetime(s):
    if not s or str(s).strip() == "":
        raise ValueError("Marca vacía")
    s = str(s).strip()
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return datetime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, tzinfo=TZ)
        else:
            return dt.astimezone(TZ)
    except Exception:
        pass
    fmts = [
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                return datetime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, tzinfo=TZ)
            else:
                return dt.astimezone(TZ)
        except Exception:
            continue
    raise ValueError(f"Formato inválido en marca temporal: {s}")

# -------------------------------------------------------------------
# FILA DINÁMICA
# -------------------------------------------------------------------
FILA_BASE = 170
FECHA_BASE = date(2025, 12, 2)

def fila_para_fecha(fecha_actual):
    delta = (fecha_actual - FECHA_BASE).days
    return FILA_BASE + delta

hoy = datetime.now(TZ).date()
TIME_ROW = fila_para_fecha(hoy)
MARCAS_ROW = 2

# -------------------------------------------------------------------
# HOJAS Y USUARIOS
# -------------------------------------------------------------------
SHEET_FACUNDO = "F. Economía"
SHEET_IVAN = "I. Física"
SHEET_MARCAS = "marcas"

USERS = {
    "Facundo": {
        "Matemática para Economistas 1": {
            "time": f"'{SHEET_FACUNDO}'!B{TIME_ROW}",
            "est":  f"'{SHEET_MARCAS}'!B{MARCAS_ROW}",
        },
        "Matemática para Economistas 2": {
            "time": f"'{SHEET_FACUNDO}'!C{TIME_ROW}",
            "est":  f"'{SHEET_MARCAS}'!C{MARCAS_ROW}",
        },
        "Macroeconomía 1": {
            "time": f"'{SHEET_FACUNDO}'!D{TIME_ROW}",
            "est":  f"'{SHEET_MARCAS}'!D{MARCAS_ROW}",
        },
        "Historia": {
            "time": f"'{SHEET_FACUNDO}'!E{TIME_ROW}",
            "est":  f"'{SHEET_MARCAS}'!E{MARCAS_ROW}",
        },
    },

    "Iván": {
        "Física": {
            "time": f"'{SHEET_IVAN}'!B{TIME_ROW}",
            "est":  f"'{SHEET_MARCAS}'!F{MARCAS_ROW}",
        },
        "Análisis": {
            "time": f"'{SHEET_IVAN}'!C{TIME_ROW}",
            "est":  f"'{SHEET_MARCAS}'!G{MARCAS_ROW}",
        },
    }
}

# -------------------------------------------------------------------
# FUNCIONES DE TIEMPO
# -------------------------------------------------------------------
def hms_a_segundos(hms):
    if not hms or str(hms).strip() == "":
        return 0
    h, m, s = map(int, hms.split(":"))
    return h*3600 + m*60 + s

def segundos_a_hms(seg):
    h = seg // 3600
    m = (seg % 3600) // 60
    s = seg % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def hms_a_fraction(hms):
    return hms_a_segundos(hms) / 86400

def hms_a_minutos(hms):
    return hms_a_segundos(hms) / 60

def enable_manual_input(materia_key):
    st.session_state[f"show_manual_{materia_key}"] = True

# -------------------------------------------------------------------
# LECTURA / ESCRITURA SHEETS
# -------------------------------------------------------------------
def cargar_todo():
    sheet_id = st.secrets["sheet_id"]
    ranges = []
    for user, materias in USERS.items():
        for m, info in materias.items():
            ranges.append(info["est"])
            ranges.append(info["time"])
    res = sheet.values().batchGet(
        spreadsheetId=sheet_id,
        ranges=ranges,
        valueRenderOption="FORMATTED_VALUE"
    ).execute()
    values = res.get("valueRanges", [])
    data = {u: {"estado": {}, "tiempos": {}} for u in USERS}
    idx = 0
    for user, materias in USERS.items():
        for materia, info in materias.items():
            est_val = values[idx].get("values", [[]])
            est_val = est_val[0][0] if est_val and est_val[0] else ""
            idx += 1
            time_val = values[idx].get("values", [[]])
            time_val = time_val[0][0] if time_val and time_val[0] else "00:00:00"
            idx += 1
            data[user]["estado"][materia] = est_val
            data[user]["tiempos"][materia] = time_val
    return data

def cargar_resumen_marcas():
    sheet_id = st.secrets["sheet_id"]
    ranges = [
        f"'{SHEET_MARCAS}'!C{TIME_ROW}",
        f"'{SHEET_MARCAS}'!B{TIME_ROW}",
        f"'{SHEET_MARCAS}'!E{TIME_ROW}",
        f"'{SHEET_MARCAS}'!D{TIME_ROW}",
    ]
    try:
        res = sheet.values().batchGet(
            spreadsheetId=sheet_id,
            ranges=ranges,
            valueRenderOption="FORMATTED_VALUE"
        ).execute()
        vr = res.get("valueRanges", [])
    except Exception:
        vr = [{} for _ in ranges]
    def _get(i):
        try:
            val = vr[i].get("values", [[]])[0][0]
            return "" if val is None else val
        except:
            return ""
    return {
        "Facundo": {"per_min": _get(0), "total": _get(2)},
        "Iván": {"per_min": _get(1), "total": _get(3)}
    }

def batch_write(updates):
    sheet_id = st.secrets["sheet_id"]
    body = {
        "valueInputOption": "USER_ENTERED",
        "data": [{"range": r, "values": [[v]]} for r, v in updates]
    }
    sheet.values().batchUpdate(spreadsheetId=sheet_id, body=body).execute()

def limpiar_estudiando(materias):
    updates = [(datos["est"], "") for materia, datos in materias.items()]
    batch_write(updates)

def acumular_tiempo(usuario, materia, minutos_sumar):
    info = USERS[usuario][materia]
    res = sheet.values().get(
        spreadsheetId=st.secrets["sheet_id"],
        range=info["est"]
    ).execute()
    valor_prev = res.get("values", [[0]])[0][0] or 0
    try:
        valor_prev = float(valor_prev)
    except:
        valor_prev = 0
    nuevo_total = valor_prev + minutos_sumar
    batch_write([(info["est"], nuevo_total)])

# -------------------------------------------------------------------
# POPUP
# -------------------------------------------------------------------
def show_md_popup(flag_key, title, md_text, close_key):
    if not st.session_state.get(flag_key, False):
        return
    if hasattr(st, "modal"):
        try:
            with st.modal(title):
                st.markdown(md_text)
                if st.button("Cerrar", key=close_key):
                    st.session_state[flag_key] = False
                    st.experimental_rerun()
        except Exception:
            with st.expander(title, expanded=True):
                st.markdown(md_text)
                if st.button("Cerrar", key=close_key+"_fb"):
                    st.session_state[flag_key] = False
                    st.experimental_rerun()
    else:
        with st.expander(title, expanded=True):
            st.markdown(md_text)
            if st.button("Cerrar", key=close_key+"_fb2"):
                st.session_state[flag_key] = False
                st.experimental_rerun()

# -------------------------------------------------------------------
# LOGIN MANUAL
# -------------------------------------------------------------------
if "usuario_seleccionado" not in st.session_state:
    st.title("¿Quién sos? 👤")
    col_u1, col_u2 = st.columns(2)
    with col_u1:
        if st.button("Soy Facundo", use_container_width=True):
            st.session_state["usuario_seleccionado"] = "Facundo"
            st.experimental_rerun()
    with col_u2:
        if st.button("Soy Iván", use_container_width=True):
            st.session_state["usuario_seleccionado"] = "Iván"
            st.experimental_rerun()
    st.stop()

USUARIO_ACTUAL = st.session_state["usuario_seleccionado"]

if st.sidebar.button("Cerrar sesión / Cambiar usuario"):
    del st.session_state["usuario_seleccionado"]
    st.experimental_rerun()

# -------------------------------------------------------------------
# INTERFAZ PRINCIPAL
# -------------------------------------------------------------------
st.title("⏳ Control de Estudio")

datos = cargar_todo()
resumen_marcas = cargar_resumen_marcas()

# BOTONES: ACTUALIZAR
col_btn1, col_btn2 = st.columns([0.8, 0.2])
with col_btn1:
    if st.button("🔄 Actualizar tiempos"):
        st.experimental_rerun()
# Hora arriba opcional
# with col_btn2:
#     st.write(ahora_str())

otro = "Iván" if USUARIO_ACTUAL == "Facundo" else "Facundo"
colA, colB = st.columns(2)

# PANEL USUARIO ACTUAL
with colA:
    st.subheader(f"👤 {USUARIO_ACTUAL}")
    if st.button("ℹ️ Info", key=f"info_btn_{USUARIO_ACTUAL}"):
        st.session_state[f"show_info_{USUARIO_ACTUAL}"] = True
    md_text = MD_FACUNDO if USUARIO_ACTUAL == "Facundo" else MD_IVAN
    show_md_popup(f"show_info_{USUARIO_ACTUAL}", f"Información de {USUARIO_ACTUAL}", md_text, f"cerrar_{USUARIO_ACTUAL}")
    
# PANEL OTRO USUARIO
with colB:
    st.subheader(f"👤 {otro}")
    if st.button("ℹ️ Info", key=f"info_btn_{otro}"):
        st.session_state[f"show_info_{otro}"] = True
    md_text_otro = MD_FACUNDO if otro == "Facundo" else MD_IVAN
    show_md_popup(f"show_info_{otro}", f"Información de {otro}", md_text_otro, f"cerrar_{otro}")
