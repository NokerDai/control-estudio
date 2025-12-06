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

# -------------------------------------------------------------------
# LECTURAS OPTIMIZADAS (1 request para la fila de 'marcas', cached)
# -------------------------------------------------------------------
@st.cache_data(ttl=10)
def leer_marcas_row_cached(row):
    """
    Lee B{row}:P{row} de la hoja 'marcas' y devuelve un dict con claves 'B'..'P' -> float.
    TTL corto para que la app sea reactiva pero reduzca llamadas.
    """
    cols = [chr(c) for c in range(ord('B'), ord('P') + 1)]  # B..P
    rango = f"'{SHEET_MARCAS}'!B{row}:P{row}"
    try:
        res = sheet.values().get(
            spreadsheetId=st.secrets["sheet_id"],
            range=rango,
            valueRenderOption="FORMATTED_VALUE"
        ).execute()
        values = res.get("values", [[]])
        row_vals = values[0] if values and values[0] else []
    except:
        row_vals = []

    # Map columns to floats (si falta un valor, -> 0.0)
    mapped = {}
    for i, col in enumerate(cols):
        v = row_vals[i] if i < len(row_vals) else ""
        mapped[col] = parse_float_or_zero(v)
    return mapped

def cargar_resumen_marcas():
    """
    Usa la fila cached de marcas para devolver per_min de Facundo (C) e Iván (B).
    Devuelve strings iguales a lo que usabas antes ("" si vacío).
    """
    marcas = leer_marcas_row_cached(TIME_ROW)
    # Obtener como string original si quieres, pero aquí devolvemos como string formateado simple
    per_min_fac = "" if marcas.get("C", 0) == 0 else str(marcas.get("C", 0))
    per_min_ivan = "" if marcas.get("B", 0) == 0 else str(marcas.get("B", 0))
    return {
        "Facundo": {"per_min": per_min_fac},
        "Iván": {"per_min": per_min_ivan}
    }

# -------------------------------------------------------------------
# CARGA DE ESTADO Y TIEMPOS
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
# INTERFAZ PRINCIPAL
# -------------------------------------------------------------------
datos = cargar_todo()
resumen_marcas = cargar_resumen_marcas()
marcas_row = leer_marcas_row_cached(TIME_ROW)  # diccionario B..P -> float cached

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

    # -------- CALCULAR TOTAL (NO EXCEL) --------
    try:
        per_min_str = resumen_marcas[USUARIO_ACTUAL].get("per_min", "")
        per_min_val = parse_float_or_zero(per_min_str)

        minutos_totales = 0.0
        mis_materias = USERS[USUARIO_ACTUAL]

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

        # --- calcular pago por objetivo del usuario actual usando el dict cached marcas_row
        objetivo = 0
        if otro == "Iván":
            objetivo = marcas_row.get("O", 0.0)
        else:  # Facundo
            objetivo = marcas_row.get("P", 0.0)
        pago_por_objetivo_actual = per_min_val * objetivo

        # mostrar línea con $ escapados para que Markdown no interprete LaTeX
        st.markdown(
            f"<b><span style='color: #00c853;'>\\${total_calc:.2f}</span> total | "
            f"\\${per_min_val:.2f} por minuto | "
            f"\\${pago_por_objetivo_actual:.2f} por {objetivo/60:.2f} horas</b>",
            unsafe_allow_html=True
        )
    except Exception as e:
        # Para debugging podés descomentar: st.error(str(e))
        st.markdown("**— | —**")

    # -------- MATERIAS --------
    materia_en_curso = None
    for m, info in mis_materias.items():
        if str(datos[USUARIO_ACTUAL]["estado"][m]).strip() != "":
            materia_en_curso = m
            break

    for materia, info in mis_materias.items():
        est_raw = datos[USUARIO_ACTUAL]["estado"][materia]
        tiempo_acum = datos[USUARIO_ACTUAL]["tiempos"][materia]

        tiempo_anadido_seg = 0
        if str(est_raw).strip() != "":
            try:
                inicio = parse_datetime(est_raw)
                tiempo_anadido_seg = int((datetime.now(TZ) - inicio).total_seconds())
            except:
                tiempo_anadido_seg = 0

        tiempo_total_seg = hms_a_segundos(tiempo_acum) + max(0, tiempo_anadido_seg)
        tiempo_total_hms = segundos_a_hms(tiempo_total_seg)

        col_name, col_time, col_actions = st.columns([0.6, 0.2, 0.2], gap="small")

        with col_name:
            st.markdown(f"**{materia}**")

        with col_time:
            st.markdown(f"🕒 {tiempo_total_hms}")

        with col_actions:
            btn_start, btn_edit = st.columns([1,1], gap="small")

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

            with btn_edit:
                if st.button("✏️", key=f"edit_{materia}", on_click=enable_manual_input, args=[materia]):
                    pass

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
# PANEL OTRO USUARIO (SOLO LECTURA)
# -------------------------------------------------------------------
with colB:
    st.subheader(f"👤 {otro}")

    with st.expander(f"ℹ️ Fe", expanded=False):
        st.markdown(MD_FACUNDO if otro == "Facundo" else MD_IVAN)

    # -------- TOTAL OTRO USUARIO --------
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

        # --- calcular pago por objetivo del 'otro' usando marcas_row (cached)
        objetivo_otro = 0
        if otro == "Iván":
            objetivo_otro = marcas_row.get("O", 0.0)
        else:  # Facundo
            objetivo_otro = marcas_row.get("P", 0.0)
        pago_por_objetivo_otro = per_min_val_otro * objetivo_otro

        st.markdown(
            f"<b><span style='color: #00c853;'>\\${total_otro:.2f}</span> | "
            f"\\${per_min_val_otro:.2f} por minuto | "
            f"\\${pago_por_objetivo_otro:.2f} por {objetivo_otro/60:.2f} horas</b>",
            unsafe_allow_html=True
        )
    except Exception as e:
        # Para debugging: st.error(str(e))
        st.markdown("**— | —**")

    # -------- MATERIAS OTRO --------
    for materia, info in USERS[otro].items():
        est_raw = datos[otro]["estado"][materia]
        tiempo = datos[otro]["tiempos"][materia]

        tiempo_anad = 0
        if str(est_raw).strip() != "":
            try:
                tiempo_anad = int((datetime.now(TZ) - parse_datetime(est_raw)).total_seconds())
            except:
                tiempo_anad = 0

        total_seg = hms_a_segundos(tiempo) + max(0, tiempo_anad)

        box = st.container()
        with box:
            st.markdown(f"**{materia}**")
            st.write(f"🕒 Total: **{segundos_a_hms(total_seg)}**")
            if str(est_raw).strip() != "":
                st.caption(f"Base: {tiempo} | En proceso: +{segundos_a_hms(tiempo_anad)}")
                st.markdown("🟢 Estudiando")
            else:
                st.markdown("⚪")





