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

# Servicio Google Sheets
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
    s = str(s).strip()
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S%z")
        return dt.astimezone(TZ)
    except:
        pass
    dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    return dt.replace(tzinfo=TZ)

# -------------------------------------------------------------------
# FILA DINÁMICA SEGÚN LA FECHA
# -------------------------------------------------------------------
FILA_BASE = 170
FECHA_BASE = date(2025, 12, 2)  # fila 170 = 2/12/2025

def fila_para_fecha(fecha_actual):
    delta = (fecha_actual - FECHA_BASE).days
    return FILA_BASE + delta

hoy = date.today()
TIME_ROW = fila_para_fecha(hoy)
MARCAS_ROW = 2  # sigue fija para las marcas de inicio

# -------------------------------------------------------------------
# HOJAS
# -------------------------------------------------------------------
SHEET_FACUNDO = "F. Economía"
SHEET_IVAN = "I. Física"
SHEET_MARCAS = "marcas"

# -------------------------------------------------------------------
# MAPEO DE USUARIOS Y MATERIAS
# -------------------------------------------------------------------
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
    if not hms or hms.strip() == "":
        return 0
    h, m, s = map(int, hms.split(":"))
    return h*3600 + m*60 + s

def segundos_a_hms(seg):
    h = seg // 3600
    m = (seg % 3600) // 60
    s = seg % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def hms_a_fraction(hms):
    """Convierte 'HH:MM:SS' a fracción de día para Google Sheets."""
    return hms_a_segundos(hms) / 86400

# -------------------------------------------------------------------
# UTILS PARA UI Y ESTADO
# -------------------------------------------------------------------
def enable_manual_input(materia_key):
    st.session_state[f"show_manual_{materia_key}"] = True

# -------------------------------------------------------------------
# LECTURA MASIVA
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

# -------------------------------------------------------------------
# ESCRITURA MASIVA
# -------------------------------------------------------------------
def batch_write(updates):
    sheet_id = st.secrets["sheet_id"]
    body = {
        "valueInputOption": "USER_ENTERED",  # permite interpretar duración
        "data": [{"range": r, "values": [[v]]} for r, v in updates]
    }
    sheet.values().batchUpdate(
        spreadsheetId=sheet_id,
        body=body
    ).execute()

def limpiar_estudiando(materias):
    updates = [(datos["est"], "") for materia, datos in materias.items()]
    batch_write(updates)

# -------------------------------------------------------------------
# SELECCIÓN DE USUARIO
# -------------------------------------------------------------------
if "usuario_seleccionado" not in st.session_state:
    st.title("¿Quién sos? 👤")
    col_u1, col_u2 = st.columns(2)

    with col_u1:
        if st.button("Soy Facundo", use_container_width=True):
            st.session_state["usuario_seleccionado"] = "Facundo"
            st.rerun()

    with col_u2:
        if st.button("Soy Iván", use_container_width=True):
            st.session_state["usuario_seleccionado"] = "Iván"
            st.rerun()

    st.stop()

USUARIO_ACTUAL = st.session_state["usuario_seleccionado"]

if st.sidebar.button("Cerrar sesión / Cambiar usuario"):
    del st.session_state["usuario_seleccionado"]
    st.rerun()

# -------------------------------------------------------------------
# INTERFAZ PRINCIPAL
# -------------------------------------------------------------------
st.title("⏳ Control de Estudio")
datos = cargar_todo()

if st.button("🔄 Actualizar tiempos"):
    st.rerun()

otro = "Iván" if USUARIO_ACTUAL == "Facundo" else "Facundo"
colA, colB = st.columns(2)

# -------------------------------------------------------------------
# PANEL USUARIO ACTUAL
# -------------------------------------------------------------------
with colA:
    st.subheader(f"👤 {USUARIO_ACTUAL}")
    mis_materias = USERS[USUARIO_ACTUAL]

    materia_en_curso = None
    for m, info in mis_materias.items():
        if datos[USUARIO_ACTUAL]["estado"][m].strip() != "":
            materia_en_curso = m
            break

    for materia, info in mis_materias.items():
        est_raw = datos[USUARIO_ACTUAL]["estado"][materia]
        tiempo_acum = datos[USUARIO_ACTUAL]["tiempos"][materia]

        box = st.container()
        with box:
            st.markdown(f"**{materia}**")

            tiempo_anadido_seg = 0
            if est_raw.strip() != "":
                inicio = parse_datetime(est_raw)
                tiempo_anadido_seg = int((datetime.now(TZ) - inicio).total_seconds())

            tiempo_acum_seg = hms_a_segundos(tiempo_acum)
            tiempo_total = tiempo_acum_seg + max(0, tiempo_anadido_seg)
            tiempo_total_hms = segundos_a_hms(tiempo_total)

            st.write(f"🕒 Total: **{tiempo_total_hms}**")

            if est_raw.strip() != "":
                st.caption(f"Base: {tiempo_acum} | En proceso: +{segundos_a_hms(tiempo_anadido_seg)}")
                st.markdown("🟢 **Estudiando**")
            else:
                st.markdown("⚪")

            b1, b2, _ = st.columns([0.2, 0.2, 0.6])

            if materia_en_curso == materia:
                with b1:
                    if st.button("⛔", key=f"det_{materia}"):
                        diff = int((datetime.now(TZ) - parse_datetime(est_raw)).total_seconds())
                        nuevo_total = tiempo_acum_seg + max(0, diff)
                        batch_write([
                            (info["time"], hms_a_fraction(segundos_a_hms(nuevo_total))),
                            (info["est"], "")
                        ])
                        st.rerun()
                continue

            if materia_en_curso is not None:
                continue

            with b1:
                if st.button("▶", key=f"est_{materia}"):
                    limpiar_estudiando(mis_materias)
                    batch_write([(info["est"], ahora_str())])
                    st.rerun()

            with b2:
                if st.button("✏️", key=f"edit_{materia}", on_click=enable_manual_input, args=[materia]):
                    pass

            if st.session_state.get(f"show_manual_{materia}", False):
                nuevo = st.text_input(f"Nuevo tiempo (HH:MM:SS):", key=f"in_{materia}")
                if st.button("Guardar", key=f"save_{materia}"):
                    try:
                        batch_write([(info["time"], hms_a_fraction(nuevo))])
                        st.session_state[f"show_manual_{materia}"] = False
                        st.rerun()
                    except:
                        st.error("Formato inválido (usar HH:MM:SS)")

# -------------------------------------------------------------------
# PANEL OTRO USUARIO (solo lectura)
# -------------------------------------------------------------------
with colB:
    st.subheader(f"👤 {otro}")

    for materia, info in USERS[otro].items():
        est_raw = datos[otro]["estado"][materia]
        tiempo = datos[otro]["tiempos"][materia]

        box = st.container()
        with box:
            st.markdown(f"**{materia}**")

            tiempo_anadido = 0
            if est_raw.strip() != "":
                tiempo_anadido = int((datetime.now(TZ) - parse_datetime(est_raw)).total_seconds())

            total = hms_a_segundos(tiempo) + max(0, tiempo_anadido)
            st.write(f"🕒 Total: **{segundos_a_hms(total)}**")

            if est_raw.strip() != "":
                st.caption(f"Base: {tiempo} | En proceso: +{segundos_a_hms(tiempo_anadido)}")
                st.markdown("🟢 Estudiando")
            else:
                st.markdown("⚪")
