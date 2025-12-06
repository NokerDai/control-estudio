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
    layout="wide"
)

# -------------------------------------------------------------------
# CARGA ARCHIVOS MARKDOWN DESDE SECRETS
# -------------------------------------------------------------------
MD_FACUNDO = st.secrets["md"]["facundo"]
MD_IVAN = st.secrets["md"]["ivan"]

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
    except:
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
        except:
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
# HOJAS
# -------------------------------------------------------------------
SHEET_FACUNDO = "F. Economía"
SHEET_IVAN = "I. Física"
SHEET_MARCAS = "marcas"

# -------------------------------------------------------------------
# MAPEO
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
# FUNCIONES TIEMPO
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

# -------------------------------------------------------------------
# UTILS
# -------------------------------------------------------------------
def enable_manual_input(materia_key):
    st.session_state[f"show_manual_{materia_key}"] = True

def parse_float_or_zero(s):
    if s is None:
        return 0.0
    s = str(s).replace(",", ".").strip()
    try:
        return float(s)
    except:
        return 0.0

def leer_marca_col(col):
    try:
        res = sheet.values().get(
            spreadsheetId=st.secrets["sheet_id"],
            range=f"'{SHEET_MARCAS}'!{col}{TIME_ROW}"
        ).execute()
        val = res.get("values", [[]])[0][0]
        return parse_float_or_zero(val)
    except:
        return 0.0

# -------------------------------------------------------------------
# CARGA
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
    ]

    try:
        res = sheet.values().batchGet(
            spreadsheetId=sheet_id,
            ranges=ranges,
            valueRenderOption="FORMATTED_VALUE"
        ).execute()
        vr = res.get("valueRanges", [])
    except:
        vr = [{} for _ in ranges]

    def _get(i):
        try:
            val = vr[i].get("values", [[]])[0][0]
            return "" if val is None else val
        except:
            return ""

    return {
        "Facundo": {"per_min": _get(0)},
        "Iván": {"per_min": _get(1)}
    }

# -------------------------------------------------------------------
# ESCRITURA
# -------------------------------------------------------------------
def batch_write(updates):
    sheet_id = st.secrets["sheet_id"]
    body = {
        "valueInputOption": "USER_ENTERED",
        "data": [{"range": r, "values": [[v]]} for r, v in updates]
    }
    sheet.values().batchUpdate(
        spreadsheetId=sheet_id,
        body=body
    ).execute()

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
# LOGIN
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

# =========================
#   NUEVA INTERFAZ VISUAL
# =========================

st.markdown("""
<style>
/* Estilo de tarjetas */
.card {
    background: #f7f7f9;
    padding: 20px;
    border-radius: 12px;
    margin-bottom: 20px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.08);
}

/* Contenedor responsivo: stack en mobile */
@media (max-width: 900px) {
    .desktop-cols { display: block !important; }
}
</style>
""", unsafe_allow_html=True)


# ------------------------
# TARJETA DEL USUARIO ACTUAL
# ------------------------

st.markdown(f"<div class='card'>", unsafe_allow_html=True)
st.markdown(f"### 👤 {USUARIO_ACTUAL}")

# Info motivacional
with st.expander("ℹ️ No pensar, actuar."):
    st.markdown(MD_FACUNDO if USUARIO_ACTUAL == "Facundo" else MD_IVAN)

# Total del día
st.markdown(
    f"<div style='font-size:36px; font-weight:700; margin-top:10px;'>${total_calc:.2f}</div>",
    unsafe_allow_html=True
)

# Barra de progreso
st.progress(progreso)

st.caption(f"${per_min_val:.2f} por minuto — Objetivo: {objetivo_actual_hms}")

# Estado actual del usuario
if materia_en_curso:
    st.success(f"🟢 Estudiando **{materia_en_curso}** ahora mismo")
else:
    st.info("No estás estudiando ahora mismo.")

# Materias
st.markdown("### Materias")
for materia, info in mis_materias.items():
    est_raw = datos[USUARIO_ACTUAL]["estado"][materia]

    with st.container():
        st.markdown(f"**{materia}**")
        st.write(f"Tiempo total: **{tiempo_total_hms}**")

        col1, col2, col3 = st.columns([0.4, 0.3, 0.3])

        with col1:
            if materia_en_curso == materia:
                if st.button("⛔ Detener", key=f"det_{materia}"):
                    detener_estudio(materia, info, est_raw, tiempo_acum)
            elif materia_en_curso is None:
                if st.button("▶ Iniciar", key=f"est_{materia}"):
                    iniciar_estudio(materia, info, mis_materias)

        with col2:
            if st.button("✏️ Editar", key=f"edit_{materia}", on_click=enable_manual_input, args=[materia]):
                pass

        with col3:
            if str(est_raw).strip() != "":
                st.markdown("🟢 En curso")
            else:
                st.markdown("⚪")

        if st.session_state.get(f"show_manual_{materia}", False):
            nuevo = st.text_input("Nuevo tiempo (HH:MM:SS)", key=f"in_{materia}")
            if st.button("Guardar", key=f"save_{materia}"):
                editar_manual(nuevo, info, materia)
            
st.markdown("</div>", unsafe_allow_html=True)



# ------------------------
# TARJETA DEL OTRO USUARIO
# ------------------------

st.markdown(f"<div class='card'>", unsafe_allow_html=True)
st.markdown(f"### 👤 {otro}")

# Estado del otro usuario
materia_otro_en_curso = next(
    (m for m, v in datos[otro]["estado"].items() if str(v).strip() != ""),
    None
)

if materia_otro_en_curso:
    st.success(f"🟢 {otro} está estudiando **{materia_otro_en_curso}** ahora")
else:
    st.info(f"{otro} no está estudiando ahora mismo.")

# Total del otro
st.markdown(
    f"<div style='font-size:36px; font-weight:700; margin-top:10px;'>${total_otro:.2f}</div>",
    unsafe_allow_html=True
)

st.progress(progreso_otro)
st.caption(f"${per_min_val_otro:.2f} por minuto — Objetivo: {objetivo_otro_hms}")

# Materias del otro
st.markdown("### Materias")
for materia, info in USERS[otro].items():
    total_seg = calcular_total_con_progreso(datos, otro, materia)
    est_raw = datos[otro]["estado"][materia]

    with st.container():
        st.markdown(f"**{materia}**")
        st.write(f"🕒 Total: **{segundos_a_hms(total_seg)}**")
        if str(est_raw).strip() != "":
            st.markdown("🟢 Estudiando")
        else:
            st.markdown("⚪")

st.markdown("</div>", unsafe_allow_html=True)
