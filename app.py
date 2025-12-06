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
    page_title="Control de Estudio - Dark",
    page_icon="⏳",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -------------------------------------------------------------------
# FORZAR MODO OSCURO (CSS)
# -------------------------------------------------------------------
st.markdown(
    """
    <style>
    /* Forzar fondo oscuro y texto claro */
    html, body, .main, .stApp {
        background: #0b0d10 !important;
        color: #e6eef8 !important;
    }

    /* Tarjetas */
    .card {
        background: #0f1720;
        border: 1px solid rgba(255,255,255,0.03);
        padding: 18px;
        border-radius: 12px;
        margin-bottom: 18px;
        box-shadow: 0 4px 18px rgba(2,6,23,0.6);
    }

    /* Titulos y textos */
    .big-number { font-size: 36px; font-weight: 700; color: #f1f5f9; }
    .muted { color: #9aa4b2; }

    /* Responsive: apilar columnas en pantallas pequeñas */
    @media (max-width: 900px) {
        .desktop-cols { display:block !important; }
    }

    /* Botones: mejorar contraste */

/* Botones solo en filas de materias */
.buttons-row {
    display: flex !important;
    flex-direction: row !important;
    gap: 0.5rem !important;
}

@media (max-width: 600px) {
    .buttons-row {
        flex-direction: row !important;
    }
}

/* --- FIX: mantener botones lado a lado incluso en móvil --- */
.stColumns {
    display: flex !important;
    flex-direction: row !important;
    gap: 0.5rem !important;
}

@media (max-width: 600px) {
    .stColumns {
        flex-direction: row !important;
    }
}

/* Botón interno */
    button.stButton>button {
        background-color: #1f2937;
        color: #e6eef8;
        border-radius: 8px;
        padding: 6px 12px;
        border: 1px solid rgba(255,255,255,0.04);
    }

    /* Inputs */
    .stTextInput>div>div>input {
        background: #0b1220;
        color: #e6eef8;
        border: 1px solid rgba(255,255,255,0.04);
        border-radius: 6px;
    }

    /* Progress bar container custom (for our HTML bars) */
    .prog-track { background: #111827; height: 10px; border-radius: 8px; }
    .prog-fill { height: 100%; border-radius: 8px; transition: width 0.35s ease; }
    </style>
    """,
    unsafe_allow_html=True,
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

# -------------------------------------------------------------------
# FUNCIONES DE UI (acciones)
# -------------------------------------------------------------------

def iniciar_estudio(usuario, materia, info):
    # limpia marcas de todos y pone la marca actual
    limpiar_estudiando(USERS[usuario])
    batch_write([(info["est"], ahora_str())])
    st.rerun()


def detener_estudio(usuario, materia, info, est_raw, tiempo_acum):
    try:
        diff_seg = int((datetime.now(TZ) - parse_datetime(est_raw)).total_seconds())
    except:
        diff_seg = 0
    acumular_tiempo(usuario, materia, diff_seg / 60)
    # escribir nuevo tiempo como fracción de día
    nuevo_total_seg = diff_seg + hms_a_segundos(tiempo_acum)
    batch_write([
        (info["time"], hms_a_fraction(segundos_a_hms(nuevo_total_seg))),
        (info["est"], "")
    ])
    st.rerun()


def editar_manual(nuevo, info, materia):
    try:
        # nuevo en HH:MM:SS -> escribimos fracción
        frac = hms_a_fraction(nuevo)
        batch_write([(info["time"], frac)])
        # ocultar input
        st.session_state[f"show_manual_{materia}"] = False
        st.rerun()
    except Exception:
        st.error("Formato inválido (usar HH:MM:SS)")


def calcular_total_con_progreso(datos_local, usuario, materia):
    tiempo = datos_local[usuario]["tiempos"][materia]
    est_raw = datos_local[usuario]["estado"][materia]
    tiempo_anad = 0
    if str(est_raw).strip() != "":
        try:
            tiempo_anad = int((datetime.now(TZ) - parse_datetime(est_raw)).total_seconds())
        except:
            tiempo_anad = 0
    total_seg = hms_a_segundos(tiempo) + max(0, tiempo_anad)
    return total_seg

# -------------------------------------------------------------------
# INTERFAZ PRINCIPAL (diseño dark y responsivo)
# -------------------------------------------------------------------

datos = cargar_todo()
resumen_marcas = cargar_resumen_marcas()

if st.button("🔄 Actualizar tiempos"):
    st.rerun()

otro = "Iván" if USUARIO_ACTUAL == "Facundo" else "Facundo"

# calculos de usuario actual
mis_materias = USERS[USUARIO_ACTUAL]

try:
    per_min_str = resumen_marcas[USUARIO_ACTUAL].get("per_min", "")
    per_min_val = parse_float_or_zero(per_min_str)

    minutos_totales = 0.0
    for materia, info in mis_materias.items():
        base_hms = datos[USUARIO_ACTUAL]["tiempos"][materia]
        minutos_base = hms_a_minutos(base_hms)

        est_raw = datos[USUARIO_ACTUAL]["estado"][materia]
        minutos_progreso = 0
        if str(est_raw).strip() != "":
            try:
                inicio = parse_datetime(est_raw)
                minutos_progreso = (datetime.now(TZ) - inicio).total_seconds() / 60
            except:
                minutos_progreso = 0

        minutos_totales += minutos_base + minutos_progreso

    total_calc = minutos_totales * per_min_val

    # objetivo usuario actual
    if USUARIO_ACTUAL == "Iván":
        objetivo_actual = leer_marca_col("O")
    else:
        objetivo_actual = leer_marca_col("P")

    pago_por_objetivo_actual = per_min_val * objetivo_actual
    objetivo_actual_hms = segundos_a_hms(int(objetivo_actual * 60))

    progreso = min(total_calc / max(1, pago_por_objetivo_actual), 1.0)
except Exception:
    total_calc = 0.0
    per_min_val = 0.0
    objetivo_actual_hms = "00:00:00"
    progreso = 0.0

# calculos del otro
try:
    per_min_str_otro = resumen_marcas[otro].get("per_min", "")
    per_min_val_otro = parse_float_or_zero(per_min_str_otro)

    mins_otro = 0.0
    for materia, info in USERS[otro].items():
        base_hms = datos[otro]["tiempos"][materia]
        mins_base = hms_a_minutos(base_hms)

        est_raw = datos[otro]["estado"][materia]
        mins_prog = 0
        if str(est_raw).strip() != "":
            try:
                inicio = parse_datetime(est_raw)
                mins_prog = (datetime.now(TZ) - inicio).total_seconds() / 60
            except:
                mins_prog = 0

        mins_otro += mins_base + mins_prog

    total_otro = mins_otro * per_min_val_otro

    if otro == "Iván":
        objetivo_otro = leer_marca_col("O")
    else:
        objetivo_otro = leer_marca_col("P")

    pago_por_objetivo_otro = per_min_val_otro * objetivo_otro
    objetivo_otro_hms = segundos_a_hms(int(objetivo_otro * 60))

    progreso_otro = min(total_otro / max(1, pago_por_objetivo_otro), 1.0)
except Exception:
    total_otro = 0.0
    per_min_val_otro = 0.0
    objetivo_otro_hms = "00:00:00"
    progreso_otro = 0.0

# ------------- Diseño: tarjeta usuario actual -------------
st.markdown(f"<div class='card'>", unsafe_allow_html=True)
st.markdown(f"### 👤 {USUARIO_ACTUAL}")

with st.expander("ℹ️ No pensar, actuar."):
    st.markdown(MD_FACUNDO if USUARIO_ACTUAL == "Facundo" else MD_IVAN)

st.markdown(f"<div class='big-number'>${total_calc:.2f}</div>", unsafe_allow_html=True)

# barra de progreso personalizada
prog_pct = int(progreso * 100)
if prog_pct < 50:
    color = '#d9534f'
elif prog_pct < 90:
    color = '#f0ad4e'
else:
    color = '#5cb85c'

st.markdown(
    f"<div class='prog-track' style='width:100%;'><div class='prog-fill' style='width:{prog_pct}%; background:{color};'></div></div>",
    unsafe_allow_html=True,
)

st.markdown(f"<div class='muted'>{per_min_val:.2f} por minuto — Objetivo: {objetivo_actual_hms}</div>", unsafe_allow_html=True)

# estado actual
materia_en_curso = None
for m, info in mis_materias.items():
    if str(datos[USUARIO_ACTUAL]["estado"][m]).strip() != "":
        materia_en_curso = m
        break

if materia_en_curso:
    st.success(f"🟢 Estudiando **{materia_en_curso}** ahora")
else:
    st.info("No estás estudiando ahora mismo.")

st.markdown("---")
st.markdown("**Materias**")

for materia, info in mis_materias.items():
    est_raw = datos[USUARIO_ACTUAL]["estado"][materia]
    tiempo_acum = datos[USUARIO_ACTUAL]["tiempos"][materia]

    tiempo_anad_seg = 0
    if str(est_raw).strip() != "":
        try:
            inicio = parse_datetime(est_raw)
            tiempo_anad_seg = int((datetime.now(TZ) - inicio).total_seconds())
        except:
            tiempo_anad_seg = 0

    tiempo_total_seg = hms_a_segundos(tiempo_acum) + max(0, tiempo_anad_seg)
    tiempo_total_hms = segundos_a_hms(tiempo_total_seg)

    st.markdown(f"**{materia}** — 🕒 {tiempo_total_hms}")

    st.markdown("<div class='buttons-row'>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([0.4, 0.3, 0.3])
    with c1:
        if materia_en_curso == materia:
            if st.button("⛔ Detener", key=f"det_{USUARIO_ACTUAL}_{materia}"):
                detener_estudio(USUARIO_ACTUAL, materia, info, est_raw, tiempo_acum)
        else:
            if materia_en_curso is None:
                if st.button("▶ Iniciar", key=f"est_{USUARIO_ACTUAL}_{materia}"):
                    iniciar_estudio(USUARIO_ACTUAL, materia, info)
    with c2:
        if st.button("✏️ Editar", key=f"edit_{USUARIO_ACTUAL}_{materia}", on_click=enable_manual_input, args=[materia]):
            pass
    with c3:
        if str(est_raw).strip() != "":
            st.markdown("🟢 En curso")
        else:
            st.markdown("⚪")

    if st.session_state.get(f"show_manual_{materia}", False):
        st.markdown("</div>", unsafe_allow_html=True)
        nuevo = st.text_input("Nuevo tiempo (HH:MM:SS):", key=(f"show_manual_{materia}", False)uevo tiempo (HH:MM:SS):", key=f"in_{USUARIO_ACTUAL}_{materia}")
        if st.button("Guardar", key=f"save_{USUARIO_ACTUAL}_{materia}"):
            editar_manual(nuevo, info, materia)

st.markdown("</div>", unsafe_allow_html=True)

# ------------- Tarjeta otro usuario -------------
st.markdown(f"<div class='card'>", unsafe_allow_html=True)
st.markdown(f"### 👤 {otro}")

with st.expander("ℹ️ No pensar, actuar."):
    st.markdown(MD_FACUNDO if otro == "Facundo" else MD_IVAN)

# estado del otro
materia_otro_en_curso = next((m for m, v in datos[otro]["estado"].items() if str(v).strip() != ""), None)
if materia_otro_en_curso:
    st.success(f"🟢 {otro} está estudiando **{materia_otro_en_curso}** ahora")
else:
    st.info(f"{otro} no está estudiando ahora mismo.")

st.markdown(f"<div class='big-number'>${total_otro:.2f}</div>", unsafe_allow_html=True)

# barra de progreso otro
prog_otro_pct = int(progreso_otro * 100)
if prog_otro_pct < 50:
    color_otro = '#d9534f'
elif prog_otro_pct < 90:
    color_otro = '#f0ad4e'
else:
    color_otro = '#5cb85c'

st.markdown(
    f"<div class='prog-track' style='width:100%;'><div class='prog-fill' style='width:{prog_otro_pct}%; background:{color_otro};'></div></div>",
    unsafe_allow_html=True,
)

st.markdown(f"<div class='muted'>{per_min_val_otro:.2f} por minuto — Objetivo: {objetivo_otro_hms}</div>", unsafe_allow_html=True)

st.markdown("---")
st.markdown("**Materias**")
for materia, info in USERS[otro].items():
    total_seg = calcular_total_con_progreso(datos, otro, materia)
    est_raw = datos[otro]["estado"][materia]

    st.markdown(f"**{materia}** — 🕒 {segundos_a_hms(total_seg)}")
    if str(est_raw).strip() != "":
        st.caption(f"Base: {datos[otro]['tiempos'][materia]} | En proceso: +{segundos_a_hms(int(total_seg - hms_a_segundos(datos[otro]['tiempos'][materia])))}")
        st.markdown("🟢 Estudiando")
    else:
        st.markdown("⚪")

st.markdown("</div>", unsafe_allow_html=True)

# Footer rápido
st.markdown("<div class='muted' style='margin-top:12px;'>Diseño: Modo oscuro forzado • Responsive • Indicador de estudio en tiempo real</div>", unsafe_allow_html=True)
