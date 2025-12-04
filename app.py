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
# CARGA ARCHIVOS MARKDOWN DESDE SECRETS (NO EXPUESTO EN GITHUB)
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

# Servicio Google Sheets
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
# FILA DINÁMICA SEGÚN LA FECHA
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
# UTILS UI
# -------------------------------------------------------------------
def enable_manual_input(materia_key):
    st.session_state[f"show_manual_{materia_key}"] = True

# -------------------------------------------------------------------
# FORMATEO MONETARIO
# -------------------------------------------------------------------
def parse_float_or_zero(s):
    s = str(s).strip()
    if s == "":
        return 0.0
    s = s.replace("$", "").replace("ARS", "").replace(" ", "")
    s = s.replace(".", "")
    s = s.replace(",", ".")
    try:
        return float(s)
    except:
        return 0.0

def formato_moneda(num):
    if num is None:
        return "$ 0,00"
    entero = int(num)
    decimales = abs(num - entero)
    entero_fmt = f"{entero:,}".replace(",", ".")
    decimales_fmt = f"{decimales:.2f}".split(".")[1]
    return f"$ {entero_fmt},{decimales_fmt}"

# -------------------------------------------------------------------
# LECTURA MASIVA MATERIAS
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
# SOLO CARGA PER_MIN — NO MÁS TOTAL DEL EXCEL
# -------------------------------------------------------------------
def cargar_resumen_marcas():
    sheet_id = st.secrets["sheet_id"]
    ranges = [
        f"'{SHEET_MARCAS}'!C{TIME_ROW}",  # Facundo per_min
        f"'{SHEET_MARCAS}'!B{TIME_ROW}",  # Iván per_min
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
            return vr[i].get("values", [[]])[0][0]
        except:
            return ""

    return {
        "Facundo": {"per_min": _get(0)},
        "Iván": {"per_min": _get(1)}
    }

# -------------------------------------------------------------------
# ESCRITURA MASIVA
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
# INTERFAZ PRINCIPAL
# -------------------------------------------------------------------
datos = cargar_todo()
resumen_marcas = cargar_resumen_marcas()

if st.button("🔄 Actualizar tiempos"):
    st.rerun()

otro = "Iván" if USUARIO_ACTUAL == "Facundo" else "Facundo"
colA, colB = st.columns(2)

# -------------------------------------------------------------------
# PANEL USUARIO ACTUAL
# -------------------------------------------------------------------
with colA:
    st.subheader(f"👤 {USUARIO_ACTUAL}")

    with st.expander(f"ℹ️ Fe", expanded=False):
        st.markdown(MD_FACUNDO if USUARIO_ACTUAL == "Facundo" else MD_IVAN)

    # === CÁLCULO TOTAL DINÁMICO ===
    try:
        per_min_str = resumen_marcas[USUARIO_ACTUAL]["per_min"]
        per_min_val = parse_float_or_zero(per_min_str)

        minutos_totales = 0
        for materia, info in USERS[USUARIO_ACTUAL].items():
            tiempo_base = hms_a_minutos(datos[USUARIO_ACTUAL]["tiempos"][materia])
            est_raw = datos[USUARIO_ACTUAL]["estado"][materia]

            minutos_prog = 0
            if str(est_raw).strip() != "":
                try:
                    inicio = parse_datetime(est_raw)
                    minutos_prog = (datetime.now(TZ) - inicio).total_seconds() / 60
                except:
                    pass

            minutos_totales += tiempo_base + minutos_prog

        total_val = minutos_totales * per_min_val
        total_fmt = formato_moneda(total_val)

        st.markdown(f"**{formato_moneda(per_min_val)} por minuto | {total_fmt} total**")

    except Exception:
        st.markdown("**— | —**")

    mis_materias = USERS[USUARIO_ACTUAL]

    # Detectar si alguna materia está en curso
    materia_en_curso = None
    for m, info in mis_materias.items():
        if str(datos[USUARIO_ACTUAL]["estado"][m]).strip() != "":
            materia_en_curso = m
            break

    # Bloque materias usuario actual
    for materia, info in mis_materias.items():
        est_raw = datos[USUARIO_ACTUAL]["estado"][materia]
        tiempo_acum = datos[USUARIO_ACTUAL]["tiempos"][materia]

        # Calcular tiempo total
        tiempo_anadido_seg = 0
        if str(est_raw).strip() != "":
            try:
                inicio = parse_datetime(est_raw)
                tiempo_anadido_seg = int((datetime.now(TZ) - inicio).total_seconds())
            except:
                tiempo_anadido_seg = 0

        tiempo_total = hms_a_segundos(tiempo_acum) + max(0, tiempo_anadido_seg)
        tiempo_total_hms = segundos_a_hms(tiempo_total)

        col_name, col_time, col_actions = st.columns([0.6, 0.2, 0.2], gap="small")

        # Nombre materia
        with col_name:
            st.markdown(f"**{materia}**")

        # Tiempo
        with col_time:
            st.markdown(f"🕒 {tiempo_total_hms}")

        # Botones
        with col_actions:
            btn_start, btn_edit = st.columns([1,1], gap="small")

            # Start/Stop
            with btn_start:
                if materia_en_curso == materia:
                    if st.button("⛔", key=f"det_{materia}"):
                        diff_seg = int((datetime.now(TZ) - parse_datetime(est_raw)).total_seconds())
                        acumular_tiempo(USUARIO_ACTUAL, materia, diff_seg/60)
                        batch_write([
                            (info["time"], hms_a_fraction(segundos_a_hms(diff_seg + hms_a_segundos(tiempo_acum)))),
                            (info["est"], "")
                        ])
                        st.rerun()
                else:
                    if materia_en_curso is None:
                        if st.button("▶", key=f"est_{materia}"):
                            limpiar_estudiando(mis_materias)
                            batch_write([(info["est"], ahora_str())])
                            st.rerun()

            # Editar
            with btn_edit:
                if st.button("✏️", key=f"edit_{materia}", on_click=enable_manual_input, args=[materia]):
                    pass

        # Input manual
        if st.session_state.get(f"show_manual_{materia}", False):
            nuevo = st.text_input("Nuevo tiempo (HH:MM:SS):", key=f"in_{materia}")
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

    with st.expander(f"ℹ️ Fe", expanded=False):
        st.markdown(MD_FACUNDO if otro == "Facundo" else MD_IVAN)

    # === TOTAL DINÁMICO OTRO USUARIO ===
    try:
        per_min_str = resumen_marcas[otro]["per_min"]
        per_min_val = parse_float_or_zero(per_min_str)

        minutos_totales = 0
        for materia, info in USERS[otro].items():
            tiempo_base = hms_a_minutos(datos[otro]["tiempos"][materia])
            est_raw = datos[otro]["estado"][materia]

            minutos_prog = 0
            if str(est_raw).strip() != "":
                try:
                    inicio = parse_datetime(est_raw)
                    minutos_prog = (datetime.now(TZ) - inicio).total_seconds() / 60
                except:
                    pass

            minutos_totales += tiempo_base + minutos_prog

        total_val = minutos_totales * per_min_val
        total_fmt = formato_moneda(total_val)

        st.markdown(f"**{formato_moneda(per_min_val)} por minuto | {total_fmt} total**")

    except Exception:
        st.markdown("**— | —**")

    # Materias del otro usuario
    for materia, info in USERS[otro].items():
        est_raw = datos[otro]["estado"][materia]
        tiempo = datos[otro]["tiempos"][materia]

        tiempo_anadido = 0
        if str(est_raw).strip() != "":
            try:
                tiempo_anadido = int((datetime.now(TZ) - parse_datetime(est_raw)).total_seconds())
            except:
                tiempo_anadido = 0

        total_seg = hms_a_segundos(tiempo) + max(0, tiempo_anadido)

        box = st.container()
        with box:
            st.markdown(f"**{materia}**")
            st.write(f"🕒 Total: **{segundos_a_hms(total_seg)}**")
            if str(est_raw).strip() != "":
                st.caption(f"Base: {tiempo} | En proceso: +{segundos_a_hms(tiempo_anadido)}")
                st.markdown("🟢 Estudiando")
            else:
                st.markdown("⚪")
