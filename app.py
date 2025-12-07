import re
import json
from datetime import datetime, date, timedelta, time as dt_time
import os
import streamlit as st

# timezone helpers
try:
    from zoneinfo import ZoneInfo
    _HAS_ZONEINFO = True
except Exception:
    ZoneInfo = None
    _HAS_ZONEINFO = False
    try:
        import pytz
    except Exception:
        pytz = None

# Google auth + requests session (evita httplib2)
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from requests.exceptions import RequestException

# auto refresh
from streamlit_autorefresh import st_autorefresh
st_autorefresh(interval=30000, key="auto_refresh")

# -------------------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA Y ESTILOS CSS (MOBILE FIRST)
# -------------------------------------------------------------------
st.set_page_config(
    page_title="Control de Estudio",
    page_icon="⏳",
    layout="centered"
)

# CSS actualizado: tiempo más chico (1.6rem)
st.markdown("""
    <style>
    html, body, [class*="css"] {
        font-size: 18px !important; 
    }
    h1 { font-size: 2.5rem !important; }
    h2 { font-size: 2rem !important; }
    h3 { font-size: 1.5rem !important; }
    
    .materia-card {
        background-color: #262730;
        border: 1px solid #464b5c;
        padding: 20px;
        border-radius: 15px;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .materia-title {
        font-size: 1.4rem;
        font-weight: bold;
        color: #ffffff;
        margin-bottom: 5px;
    }
    .materia-time {
        font-size: 1.6rem; /* Más chico */
        font-weight: bold;
        color: #00e676;
        font-family: 'Courier New', monospace;
        margin-bottom: 15px;
    }
    .status-badge {
        display: inline-block;
        padding: 5px 10px;
        border-radius: 12px;
        font-size: 0.9rem;
        font-weight: bold;
        margin-bottom: 10px;
    }
    .status-active {
        background-color: rgba(0, 230, 118, 0.2);
        color: #00e676;
        border: 1px solid #00e676;
    }
    
    div.stButton > button {
        height: 3.5rem;
        font-size: 1.2rem !important;
        font-weight: bold !important;
        border-radius: 12px !important;
    }
    </style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------------
# ZONA HORARIA Y UTILS
# -------------------------------------------------------------------
def _argentina_now_global():
    if ZoneInfo is not None:
        return datetime.now(ZoneInfo('America/Argentina/Cordoba'))
    if 'pytz' in globals() and pytz is not None:
        return datetime.now(pytz.timezone('America/Argentina/Cordoba'))
    return datetime.now()

def ahora_str():
    dt = _argentina_now_global()
    try:
        return dt.isoformat(sep=" ", timespec="seconds")
    except:
        return dt.strftime("%Y-%m-%d %H:%M:%S")

def parse_datetime(s):
    if not s or str(s).strip() == "":
        raise ValueError("Marca vacía")
    s = str(s).strip()
    TZ = _argentina_now_global().tzinfo

    try:
        # admitir Z -> +00:00
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=TZ)
        return dt.astimezone(TZ)
    except:
        pass

    fmts = ["%Y-%m-%d %H:%M:%S%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"]
    for fmt in fmts:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=TZ)
            return dt.astimezone(TZ)
        except:
            continue
    raise ValueError(f"Formato inválido: {s}")

def hms_a_segundos(hms):
    if not hms: return 0
    try:
        h, m, s = map(int, hms.split(":"))
        return h*3600 + m*60 + s
    except:
        return 0

def segundos_a_hms(seg):
    h = seg // 3600
    m = (seg % 3600) // 60
    s = seg % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def hms_a_fraction(hms): return hms_a_segundos(hms) / 86400
def hms_a_minutos(hms): return hms_a_segundos(hms) / 60
def parse_float_or_zero(s):
    if s is None: return 0.0
    try: return float(str(s).replace(",", ".").strip())
    except: return 0.0

def parse_time_cell_to_seconds(val):
    """Acepta 'HH:MM:SS' o fracción (0.5) o segundos como string y devuelve segundos int."""
    if val is None: return 0
    s = str(val).strip()
    if s == "": return 0
    # HH:MM:SS
    if ":" in s:
        try:
            return hms_a_segundos(s)
        except:
            return 0
    # fracción de día o número
    try:
        f = float(s.replace(",", "."))
        # si está entre 0 y 1 lo tomamos como fracción de día
        if 0 <= f <= 1:
            return int(f * 86400)
        # si es razonablemente grande, asumimos segundos
        if f > 86400:
            return int(f)
        # si está en (1,86400) lo tomamos como segundos
        return int(f)
    except:
        return 0

def replace_row_in_range(range_str, new_row):
    if not isinstance(range_str, str):
        return range_str
    return re.sub(r'(\d+)(\s*$)', str(new_row), range_str)

# -------------------------------------------------------------------
# SESIÓN AUTORIZADA (AuthorizedSession) - reemplaza googleapiclient
# -------------------------------------------------------------------
@st.cache_resource
def get_sheets_session():
    try:
        key_dict = json.loads(st.secrets["textkey"])
    except Exception as e:
        st.error(f"Error leyendo st.secrets['textkey']: {e}")
        st.stop()
    try:
        creds = service_account.Credentials.from_service_account_info(
            key_dict,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        return AuthorizedSession(creds)
    except Exception as e:
        st.error(f"Error creando credenciales: {e}")
        st.stop()

session = get_sheets_session()

def sheets_batch_get(spreadsheet_id, ranges):
    """
    Llama a sheets.values:batchGet y devuelve el JSON (o lanza excepción con detalle).
    """
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values:batchGet"
    params = []
    for r in ranges:
        params.append(("ranges", r))
    params.append(("valueRenderOption", "FORMATTED_VALUE"))
    try:
        resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except RequestException as e:
        # mostrar detalle para debug
        raise RuntimeError(f"Error HTTP en batchGet: {e}\nRespuesta: {getattr(e.response,'text',None)}")

def sheets_get_single(spreadsheet_id, range_str):
    """
    Llama a sheets.values.get de forma directa (single range).
    """
    # encode range in URL path (API accept range as URL query param)
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{range_str}"
    params = {"valueRenderOption": "FORMATTED_VALUE"}
    try:
        resp = session.get(url, params=params, timeout=30)
        if resp.status_code == 404:
            # tal vez range tiene caracteres; fallback a batchGet
            res = sheets_batch_get(spreadsheet_id, [range_str])
            # normalizar
            return res
        resp.raise_for_status()
        return resp.json()
    except RequestException as e:
        raise RuntimeError(f"Error HTTP en get single range '{range_str}': {e}\nRespuesta: {getattr(e.response,'text',None)}")

def sheets_batch_update(spreadsheet_id, updates):
    """
    updates: list de (range, value)
    Ejecuta values:batchUpdate con valueInputOption USER_ENTERED
    """
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values:batchUpdate"
    data = {
        "valueInputOption": "USER_ENTERED",
        "data": [{"range": r, "values": [[v]]} for r, v in updates]
    }
    try:
        resp = session.post(url, json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except RequestException as e:
        raise RuntimeError(f"Error HTTP en batchUpdate: {e}\nRespuesta: {getattr(e.response,'text',None)}")

# -------------------------------------------------------------------
# CONSTANTES Y ESTRUCTURAS
# -------------------------------------------------------------------
FILA_BASE = 170
FECHA_BASE = date(2025, 12, 2)
SHEET_FACUNDO = "F. Economía"
SHEET_IVAN = "I. Física"
SHEET_MARCAS = "marcas"

def get_time_row():
    hoy = _argentina_now_global().date()
    delta = (hoy - FECHA_BASE).days
    return FILA_BASE + delta

TIME_ROW = get_time_row()
MARCAS_ROW = 2

USERS = {
    "Facundo": {
        "Matemática para Economistas 1": {"time": f"'{SHEET_FACUNDO}'!B{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!B{MARCAS_ROW}"},
        "Matemática para Economistas 2": {"time": f"'{SHEET_FACUNDO}'!C{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!C{MARCAS_ROW}"},
        "Macroeconomía 1":               {"time": f"'{SHEET_FACUNDO}'!D{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!D{MARCAS_ROW}"},
        "Historia":                      {"time": f"'{SHEET_FACUNDO}'!E{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!E{MARCAS_ROW}"},
    },
    "Iván": {
        "Física":   {"time": f"'{SHEET_IVAN}'!B{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!F{MARCAS_ROW}"},
        "Análisis": {"time": f"'{SHEET_IVAN}'!C{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!G{MARCAS_ROW}"},
    }
}

# -------------------------------------------------------------------
# LÓGICA DATOS (usando REST)
# -------------------------------------------------------------------
def cargar_todo():
    # Leemos todos los rangos (estados y tiempos)
    ranges = []
    for user, materias in USERS.items():
        for m, info in materias.items():
            ranges.append(info["est"])
            ranges.append(info["time"])

    try:
        res = sheets_batch_get(st.secrets["sheet_id"], ranges)
    except Exception as e:
        st.error(f"Error leyendo Google Sheets (batchGet): {e}")
        st.stop()

    values = res.get("valueRanges", [])
    data = {u: {"estado": {}, "tiempos": {}} for u in USERS}
    idx = 0
    for user, materias in USERS.items():
        for materia, info in materias.items():
            # estado (marca de inicio)
            vr_est = values[idx] if idx < len(values) else {}
            est_val = ""
            try:
                est_values = vr_est.get("values", [[]])
                est_val = est_values[0][0] if est_values and est_values[0] else ""
            except:
                est_val = ""
            idx += 1

            # time (acumulado)
            vr_time = values[idx] if idx < len(values) else {}
            time_val_raw = ""
            try:
                time_values = vr_time.get("values", [[]])
                time_val_raw = time_values[0][0] if time_values and time_values[0] else ""
            except:
                time_val_raw = ""
            idx += 1

            secs = parse_time_cell_to_seconds(time_val_raw)
            time_hms = segundos_a_hms(secs)
            data[user]["estado"][materia] = est_val
            data[user]["tiempos"][materia] = time_hms
    return data

def cargar_resumen_marcas():
    ranges = [f"'{SHEET_MARCAS}'!C{TIME_ROW}", f"'{SHEET_MARCAS}'!B{TIME_ROW}"]
    try:
        res = sheets_batch_get(st.secrets["sheet_id"], ranges)
        vr = res.get("valueRanges", [])
        fac = vr[0].get("values",[[0]])[0][0] if len(vr) > 0 else 0
        iv = vr[1].get("values",[[0]])[0][0] if len(vr) > 1 else 0
        return {"Facundo": {"per_min": fac}, "Iván": {"per_min": iv}}
    except Exception as e:
        st.error(f"Error cargando resumen marcas: {e}")
        return {"Facundo": {"per_min": 0}, "Iván": {"per_min": 0}}

def batch_write(updates):
    """
    updates: list de (range, value)
    Escribe exactamente lo que se indica. Las celdas time ahora recibirán HH:MM:SS strings.
    """
    try:
        sheets_batch_update(st.secrets["sheet_id"], updates)
    except Exception as e:
        st.error(f"Error escribiendo Google Sheets (batchUpdate): {e}")
        st.stop()

def limpiar_estudiando(materias):
    batch_write([(datos["est"], "") for materia, datos in materias.items()])

def acumular_tiempo(usuario, materia, minutos_sumar):
    info = USERS[usuario][materia]
    # leer la celda time actual (usamos sheets_get_single para mayor robustez)
    try:
        # quitar las comillas al range para la URL si es necesario (Sheets acepta 'Hoja'!A1 pero en path las comillas molestan)
        target = info["time"]
        res = sheets_batch_get(st.secrets["sheet_id"], [target])
        vr = res.get("valueRanges", [{}])[0]
        prev_raw = vr.get("values", [[""]])[0][0] if vr.get("values") else ""
    except Exception:
        prev_raw = ""
    prev_secs = parse_time_cell_to_seconds(prev_raw)
    add_secs = int(round(minutos_sumar * 60))
    new_secs = prev_secs + add_secs
    batch_write([(info["time"], segundos_a_hms(new_secs))])

# -------------------------------------------------------------------
# SELECCIÓN USUARIO
# -------------------------------------------------------------------
if "usuario_seleccionado" not in st.session_state:
    st.markdown("<h1 style='text-align: center; margin-bottom: 30px;'>¿Quién sos?</h1>", unsafe_allow_html=True)
    
    if st.button("👤 Facundo", use_container_width=True):
        st.session_state["usuario_seleccionado"] = "Facundo"
        st.rerun()
    
    st.write("")
    
    if st.button("👤 Iván", use_container_width=True):
        st.session_state["usuario_seleccionado"] = "Iván"
        st.rerun()
    st.stop()

# -------------------------------------------------------------------
# INTERFAZ PRINCIPAL
# -------------------------------------------------------------------
USUARIO_ACTUAL = st.session_state["usuario_seleccionado"]
OTRO_USUARIO = "Iván" if USUARIO_ACTUAL == "Facundo" else "Facundo"

with st.sidebar:
    st.header(f"Hola, {USUARIO_ACTUAL}")
    if st.button("Cerrar Sesión", use_container_width=True):
        del st.session_state["usuario_seleccionado"]
        st.rerun()
    # Debug: mostrar variables de proxy (puedes comentar esto en producción)
    if st.checkbox("🔍 Mostrar variables de proxy (debug)", value=False):
        st.write({k: os.environ.get(k) for k in ["HTTP_PROXY","HTTPS_PROXY","ALL_PROXY","http_proxy","https_proxy","all_proxy"]})

st.title("⏳ Control Estudio")

datos = cargar_todo()
resumen_marcas = cargar_resumen_marcas()

# --- Banderas ---
usuario_estudiando = any(str(v).strip() != "" for v in datos[USUARIO_ACTUAL]["estado"].values())
otro_estudiando = any(str(v).strip() != "" for v in datos[OTRO_USUARIO]["estado"].values())

# --- Círculos ---
def circle(color):
    return f'<span style="display:inline-block; width:10px; height:10px; border-radius:50%; background:{color}; margin-right:6px; vertical-align:middle;"></span>'

circle_usuario  = circle("#00e676" if usuario_estudiando else "#ffffff")
circle_otro     = circle("#00e676" if otro_estudiando else "#ffffff")

# --- Materia actual del otro usuario ---
materia_otro = next((m for m, v in datos[OTRO_USUARIO]["estado"].items() if str(v).strip() != ""), "")

# Métricas
def calcular_metricas(usuario):
    per_min = parse_float_or_zero(resumen_marcas[usuario].get("per_min", ""))
    total_min = 0.0
    for materia, info in USERS[usuario].items():
        base = hms_a_minutos(datos[usuario]["tiempos"][materia])
        progreso = 0
        est_raw = datos[usuario]["estado"][materia]
        if str(est_raw).strip() != "":
            try:
                inicio = parse_datetime(est_raw)
                progreso = (_argentina_now_global() - inicio).total_seconds() / 60
            except:
                pass
        total_min += base + progreso
    
    col_obj = "O" if usuario == "Iván" else "P"
    objetivo = 0.0
    try:
        res = sheets_batch_get(st.secrets["sheet_id"], [f"'{SHEET_MARCAS}'!{col_obj}{TIME_ROW}"])
        vr = res.get("valueRanges", [{}])[0]
        objetivo = parse_float_or_zero(vr.get("values", [[0]])[0][0]) if vr.get("values") else 0.0
    except Exception:
        objetivo = 0.0
    
    return total_min * per_min, per_min, objetivo, total_min

# ---- MÉTRICAS PROPIAS ----
m_tot, m_rate, m_obj, total_min = calcular_metricas(USUARIO_ACTUAL)
pago_objetivo = m_rate * m_obj
progreso_pct = min(m_tot / max(1, pago_objetivo), 1.0) * 100
color_bar = "#00e676" if progreso_pct >= 90 else "#ffeb3b" if progreso_pct >= 50 else "#ff1744"

objetivo_hms = segundos_a_hms(int(m_obj * 60))
total_hms = segundos_a_hms(int(total_min * 60))

st.markdown(f"""
    <div style="background-color: #1e1e1e; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
        <div style="font-size: 1.2rem; color: #aaa; margin-bottom: 5px;">Hoy</div>
        <div style="width: 100%; text-align: center; font-size: 2.2rem; font-weight: bold; color: #fff; line-height: 1;">{total_hms}  |  ${m_tot:.2f}</div>
        <div style="width:100%; background-color:#333; border-radius:10px; height:12px; margin: 15px 0;">
            <div style="width:{progreso_pct}%; background-color:{color_bar}; height:100%; border-radius:10px; transition: width 0.5s;"></div>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center; color:#888;">
            <div>{circle_usuario}</div>
            <div>Meta: ${pago_objetivo:.2f} ({objetivo_hms} hs)</div>
        </div>
    </div>
""", unsafe_allow_html=True)

# ---- PROGRESO DEL OTRO USUARIO (ahora expandido=True) ----
with st.expander(f"Progreso de {OTRO_USUARIO}.", expanded=True):
    o_tot, o_rate, o_obj, total_min_otro = calcular_metricas(OTRO_USUARIO)
    o_pago_obj = o_rate * o_obj
    o_progreso_pct = min(o_tot / max(1, o_pago_obj), 1.0) * 100
    o_color_bar = "#00e676" if o_progreso_pct >= 90 else "#ffeb3b" if o_progreso_pct >= 50 else "#ff1744"
    o_obj_hms = segundos_a_hms(int(o_obj * 60))
    o_total_hms = segundos_a_hms(int(total_min_otro * 60))
    
    st.markdown(f"""
        <div style="margin-bottom: 10px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size: 1.1rem; color: #ddd;"><b>{o_total_hms}  |  ${o_tot:.2f}</b></span>
                <span style="font-size: 0.9rem; color: #888;">Meta: ${o_pago_obj:.2f}</span>
            </div>
            <div style="width:100%; background-color:#444; border-radius:8px; height:8px; margin-top: 8px;">
                <div style="width:{o_progreso_pct}%; background-color:{o_color_bar}; height:100%; border-radius:8px;"></div>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center; font-size:0.8rem; color:#aaa; margin-top:5px;">
                <div style="display:flex; align-items:center;">
                    {circle_otro}
                    <span style="color:#00e676; margin-left:6px;">
                        {materia_otro}
                    </span>
                </div>
                <div>Objetivo tiempo: {o_obj_hms} hs</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

# ---- MANIFIESTO ----
with st.expander("ℹ️ No pensar, actuar."):
    md_content = st.secrets["md"]["facundo"] if USUARIO_ACTUAL == "Facundo" else st.secrets["md"]["ivan"]
    st.markdown(md_content)

# -------------------------------------------------------------------
# LISTA DE MATERIAS
# -------------------------------------------------------------------
st.subheader("Tus Materias")

mis_materias = USERS[USUARIO_ACTUAL]
materia_en_curso = None
for m, info in mis_materias.items():
    if str(datos[USUARIO_ACTUAL]["estado"][m]).strip() != "":
        materia_en_curso = m
        break

for materia, info in mis_materias.items():
    est_raw = datos[USUARIO_ACTUAL]["estado"][materia]
    tiempo_acum = datos[USUARIO_ACTUAL]["tiempos"][materia]  # ya en HH:MM:SS
    
    tiempo_anadido_seg = 0
    en_curso = False
    if str(est_raw).strip() != "":
        try:
            inicio = parse_datetime(est_raw)
            tiempo_anadido_seg = int((_argentina_now_global() - inicio).total_seconds())
            en_curso = True
        except:
            pass

    tiempo_total_hms = segundos_a_hms(
        hms_a_segundos(tiempo_acum) + max(0, tiempo_anadido_seg)
    )
    
    badge_html = f'<div class="status-badge status-active">🟢 Estudiando...</div>' if en_curso else ''
    
    html_card = f"""<div class="materia-card">
<div class="materia-title">{materia}</div>
{badge_html}
<div class="materia-time">{tiempo_total_hms}</div>
</div>"""
    
    st.markdown(html_card, unsafe_allow_html=True)

    c_actions = st.container()
    
    with c_actions:
        # BOTÓN DETENER: ahora reparte en caso de cruzar medianoche
        if materia_en_curso == materia:
            if st.button(f"⛔ DETENER {materia[:10]}...", key=f"stop_{materia}", use_container_width=True, type="primary"):
                try:
                    inicio = parse_datetime(est_raw)  # marca de inicio (timezone aware)
                except Exception as e:
                    st.error("No se pudo parsear la marca de inicio.")
                    st.rerun()

                fin = _argentina_now_global()
                if fin <= inicio:
                    # caso raro: marca futura o igual
                    st.error("La marca de inicio es igual o posterior a ahora. Ignorado.")
                    # limpiar por seguridad
                    batch_write([(info["est"], "")])
                    st.rerun()

                # frontera de medianoche (primer segundo del día siguiente al inicio)
                midnight = datetime.combine(inicio.date() + timedelta(days=1), dt_time(0,0)).replace(tzinfo=inicio.tzinfo)

                partes = []
                if inicio.date() == fin.date():
                    # todo en un mismo día
                    partes.append((inicio, fin))
                else:
                    # parte 1: inicio -> midnight (día de inicio)
                    partes.append((inicio, midnight))
                    # parte 2: midnight -> fin (día de fin)
                    partes.append((midnight, fin))

                updates = []
                for (p_inicio, p_fin) in partes:
                    segs = int((p_fin - p_inicio).total_seconds())
                    # target row correspondiente a p_inicio.date()
                    target_row = FILA_BASE + (p_inicio.date() - FECHA_BASE).days
                    time_cell_for_row = replace_row_in_range(info["time"], target_row)
                    # leer valor previo
                    try:
                        res = sheets_batch_get(st.secrets["sheet_id"], [time_cell_for_row])
                        vr = res.get("valueRanges", [{}])[0]
                        prev_raw = vr.get("values", [[""]])[0][0] if vr.get("values") else ""
                    except Exception:
                        prev_raw = ""
                    prev_secs = parse_time_cell_to_seconds(prev_raw)
                    new_secs = prev_secs + segs
                    # escribir como HH:MM:SS
                    updates.append((time_cell_for_row, segundos_a_hms(new_secs)))

                # limpiar marca de inicio
                updates.append((info["est"], ""))

                # ejecutar escritura
                batch_write(updates)
                st.rerun()
        else:
            if materia_en_curso is None:
                if st.button(f"▶ INICIAR", key=f"start_{materia}", use_container_width=True):
                    # limpiar marcas y poner marca actual en esta materia
                    limpiar_estudiando(mis_materias)
                    batch_write([(info["est"], ahora_str())])
                    st.rerun()
            else:
                st.button("...", disabled=True, key=f"dis_{materia}", use_container_width=True)

    with st.expander("🛠️ Corregir tiempo manualmente"):
        new_val = st.text_input("Tiempo (HH:MM:SS)", value=tiempo_acum, key=f"input_{materia}")
        if st.button("Guardar Corrección", key=f"save_{materia}"):
            try:
                # validar formato HH:MM:SS simple
                if ":" not in new_val:
                    raise ValueError("Formato inválido, usar HH:MM:SS")
                # escribir como HH:MM:SS
                batch_write([(info["time"], new_val)])
                st.rerun()
            except Exception as e:
                st.error("Formato inválido")





