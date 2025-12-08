import re
import json
from datetime import datetime, date, timedelta, time as dt_time
import os
import streamlit as st
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from requests.exceptions import RequestException
from streamlit_autorefresh import st_autorefresh

# Refresco automático cada 5 minutos (300000 ms)
st_autorefresh(interval=300000, key="auto_refresh")

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

# -------------------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA Y ESTILOS CSS (MOBILE FIRST)
# -------------------------------------------------------------------
st.set_page_config(
    page_title="Tiempo de Estudio",
    page_icon="⏳",
    layout="centered"
)

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
        font-size: 1.6rem;
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
    if val is None: return 0
    s = str(val).strip()
    if s == "": return 0
    if ":" in s:
        try:
            return hms_a_segundos(s)
        except:
            return 0
    try:
        f = float(s.replace(",", "."))
        if 0 <= f <= 1:
            return int(f * 86400)
        return int(f)
    except:
        return 0

def replace_row_in_range(range_str, new_row):
    if not isinstance(range_str, str):
        return range_str
    return re.sub(r'(\d+)(\s*$)', str(new_row), range_str)

# -------------------------------------------------------------------
# SESIÓN AUTORIZADA
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
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values:batchGet"
    # Filtrar rangos duplicados para ahorrar bytes en la query, manteniendo orden
    unique_ranges = list(dict.fromkeys(ranges))
    
    params = []
    for r in unique_ranges:
        params.append(("ranges", r))
    params.append(("valueRenderOption", "FORMATTED_VALUE"))
    
    try:
        resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        # Mapear respuesta a los rangos originales (por si había duplicados)
        value_ranges = {vr.get("range"): vr for vr in data.get("valueRanges", [])}
        
        # Google a veces devuelve el rango en formato absoluto 'Hoja'!A1, normalizamos si es necesario
        # Para simplificar, asumimos que la API devuelve en orden si no hay duplicados, 
        # pero con duplicados usamos un mapa. 
        # Estrategia simple: La API devuelve results en el mismo orden que 'unique_ranges'.
        
        ordered_results = data.get("valueRanges", [])
        result_map = {r: res for r, res in zip(unique_ranges, ordered_results)}
        
        # Reconstruir lista completa original
        final_list = []
        for r in ranges:
            # Intentar coincidencia exacta o buscar en el mapa
            if r in result_map:
                final_list.append(result_map[r])
            else:
                # Fallback por si la API cambia el formato del string del rango en la respuesta
                final_list.append({}) 
        
        return {"valueRanges": final_list}
        
    except RequestException as e:
        raise RuntimeError(f"Error HTTP en batchGet: {e}")

def sheets_batch_update(spreadsheet_id, updates):
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
        raise RuntimeError(f"Error HTTP en batchUpdate: {e}")

# -------------------------------------------------------------------
# CONSTANTES
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
WEEK_RANGE = f"'{SHEET_MARCAS}'!R{TIME_ROW}"

USERS = {
    "Facundo": {
        "Matemática 2": {"time": f"'{SHEET_FACUNDO}'!B{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!B{MARCAS_ROW}"},
        "Matemática 3": {"time": f"'{SHEET_FACUNDO}'!C{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!C{MARCAS_ROW}"},
        "Macroeconomía 1": {"time": f"'{SHEET_FACUNDO}'!D{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!D{MARCAS_ROW}"},
        "Historia":        {"time": f"'{SHEET_FACUNDO}'!E{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!E{MARCAS_ROW}"},
    },
    "Iván": {
        "Física":   {"time": f"'{SHEET_IVAN}'!B{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!F{MARCAS_ROW}"},
        "Análisis": {"time": f"'{SHEET_IVAN}'!C{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!G{MARCAS_ROW}"},
    }
}

# Rangos fijos para metricas
RANGO_RATE_FACU = f"'{SHEET_MARCAS}'!C{TIME_ROW}"
RANGO_RATE_IVAN = f"'{SHEET_MARCAS}'!B{TIME_ROW}"
RANGO_OBJ_FACU = f"'{SHEET_MARCAS}'!P{TIME_ROW}"
RANGO_OBJ_IVAN = f"'{SHEET_MARCAS}'!O{TIME_ROW}"

# -------------------------------------------------------------------
# LÓGICA DE DATOS OPTIMIZADA (1 LLAMADA)
# -------------------------------------------------------------------

@st.cache_data(ttl=60) 
def cargar_datos_unificados():
    """
    Lee TODO lo necesario en una sola llamada batchGet:
    1. Tiempos y estados de todas las materias.
    2. Rates ($/min) de ambos.
    3. Objetivos (min) de ambos.
    4. Valor semana actual.
    """
    
    # 1. Construir lista plana de rangos
    # Orden: [Materias Facu (Est, Time)..., Materias Ivan (Est, Time)..., Rate F, Rate I, Obj F, Obj I, Week]
    
    all_ranges = []
    
    # Estructura auxiliar para desempacar después
    mapa_indices = {
        "materias": {}, # (user, materia, tipo) -> indice
        "rates": {},
        "objs": {},
        "week": None
    }
    
    current_idx = 0
    
    # Agregar Materias
    for user, materias in USERS.items():
        for m, info in materias.items():
            all_ranges.append(info["est"])
            mapa_indices["materias"][(user, m, "est")] = current_idx
            current_idx += 1
            
            all_ranges.append(info["time"])
            mapa_indices["materias"][(user, m, "time")] = current_idx
            current_idx += 1
            
    # Agregar Rates
    all_ranges.append(RANGO_RATE_FACU)
    mapa_indices["rates"]["Facundo"] = current_idx
    current_idx += 1
    
    all_ranges.append(RANGO_RATE_IVAN)
    mapa_indices["rates"]["Iván"] = current_idx
    current_idx += 1
    
    # Agregar Objetivos
    all_ranges.append(RANGO_OBJ_FACU)
    mapa_indices["objs"]["Facundo"] = current_idx
    current_idx += 1
    
    all_ranges.append(RANGO_OBJ_IVAN)
    mapa_indices["objs"]["Iván"] = current_idx
    current_idx += 1
    
    # Agregar Semana
    all_ranges.append(WEEK_RANGE)
    mapa_indices["week"] = current_idx
    current_idx += 1
    
    # --- LLAMADA API ÚNICA ---
    try:
        res = sheets_batch_get(st.secrets["sheet_id"], all_ranges)
    except Exception as e:
        st.error(f"Error API Google Sheets: {e}")
        st.stop()
        
    values = res.get("valueRanges", [])
    
    # --- PARSING ---
    def get_val(idx, default=""):
        if idx >= len(values): return default
        vr = values[idx]
        rows = vr.get("values", [])
        if not rows: return default
        return rows[0][0] if rows[0] else default

    # 1. Datos Materias
    data_usuarios = {u: {"estado": {}, "tiempos": {}} for u in USERS}
    for user, materias in USERS.items():
        for m in materias:
            # Estado
            idx_est = mapa_indices["materias"][(user, m, "est")]
            raw_est = get_val(idx_est)
            data_usuarios[user]["estado"][m] = raw_est
            
            # Tiempo
            idx_time = mapa_indices["materias"][(user, m, "time")]
            raw_time = get_val(idx_time)
            secs = parse_time_cell_to_seconds(raw_time)
            data_usuarios[user]["tiempos"][m] = segundos_a_hms(secs)
            
    # 2. Resumen Marcas (Rates y Objetivos)
    # Nota: Antes 'cargar_resumen_marcas' devolvía per_min. Ahora agregamos objetivos aquí para eficiencia.
    resumen = {
        "Facundo": {
            "per_min": parse_float_or_zero(get_val(mapa_indices["rates"]["Facundo"])),
            "obj": parse_float_or_zero(get_val(mapa_indices["objs"]["Facundo"]))
        },
        "Iván": {
            "per_min": parse_float_or_zero(get_val(mapa_indices["rates"]["Iván"])),
            "obj": parse_float_or_zero(get_val(mapa_indices["objs"]["Iván"]))
        }
    }
    
    # 3. Semana
    raw_week = get_val(mapa_indices["week"], "0")
    semana_val = parse_float_or_zero(raw_week)
    
    return {
        "users_data": data_usuarios,
        "resumen": resumen,
        "semana": semana_val
    }

def batch_write(updates):
    try:
        sheets_batch_update(st.secrets["sheet_id"], updates)
        # CRÍTICO: Limpiar caché después de escribir para ver cambios
        cargar_datos_unificados.clear() 
    except Exception as e:
        st.error(f"Error escribiendo Google Sheets: {e}")
        st.stop()

def limpiar_estudiando(materias):
    batch_write([(datos["est"], "") for materia, datos in materias.items()])

def main():
    try:
        params = st.query_params
    except Exception:
        params = st.experimental_get_query_params()

    def set_user_and_rerun(u):
        st.session_state["usuario_seleccionado"] = u
        st.rerun()

    if "usuario_seleccionado" not in st.session_state:
        if "f" in params: set_user_and_rerun("Facundo")
        if "i" in params: set_user_and_rerun("Iván")
        if "user" in params:
            try:
                uval = params["user"][0].lower() if isinstance(params["user"], (list, tuple)) else str(params["user"]).lower()
            except:
                uval = str(params["user"]).lower()
            if uval in ["facu", "facundo"]: set_user_and_rerun("Facundo")
            if uval in ["ivan", "iván", "iva"]: set_user_and_rerun("Iván")

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

    # --- CARGA DE DATOS OPTIMIZADA ---
    # Esto reemplaza las 3 llamadas separadas anteriores
    datos_globales = cargar_datos_unificados()
    
    # Extraer estructuras para mantener compatibilidad con resto del código
    datos = datos_globales["users_data"]
    resumen_marcas = datos_globales["resumen"]
    semana_val_raw = datos_globales["semana"]

    USUARIO_ACTUAL = st.session_state["usuario_seleccionado"]
    OTRO_USUARIO = "Iván" if USUARIO_ACTUAL == "Facundo" else "Facundo"

    usuario_estudiando = any(str(v).strip() != "" for v in datos[USUARIO_ACTUAL]["estado"].values())
    otro_estudiando = any(str(v).strip() != "" for v in datos[OTRO_USUARIO]["estado"].values())

    def circle(color):
        return (
            f'<span style="display:inline-flex; align-items:center; justify-content:center; '
            f'width:10px; height:10px; border-radius:50%; background:{color}; '
            f'margin-right:6px; flex-shrink:0;"></span>'
        )

    circle_usuario  = circle("#00e676" if usuario_estudiando else "#ffffff")
    circle_otro     = circle("#00e676" if otro_estudiando else "#ffffff")

    materia_otro = next((m for m, v in datos[OTRO_USUARIO]["estado"].items() if str(v).strip() != ""), "")
    
    # Métricas
    def calcular_metricas(usuario):
        # Ahora leemos del dict 'resumen_marcas' que ya tiene todo
        per_min = resumen_marcas[usuario]["per_min"]
        objetivo = resumen_marcas[usuario]["obj"]
        
        total_min = 0.0
        progreso = 0.0
        
        for materia, info in USERS[usuario].items():
            base = hms_a_minutos(datos[usuario]["tiempos"][materia])
            p_local = 0
            est_raw = datos[usuario]["estado"][materia]
            if str(est_raw).strip() != "":
                try:
                    inicio = parse_datetime(est_raw)
                    p_local = (_argentina_now_global() - inicio).total_seconds() / 60
                except:
                    pass
            total_min += base + p_local
            progreso += p_local # Solo lo actual

        return total_min * per_min, per_min, objetivo, total_min, progreso * per_min

    # ---- MÉTRICAS PROPIAS ----
    m_tot, m_rate, m_obj, total_min, progreso_en_dinero = calcular_metricas(USUARIO_ACTUAL)
    pago_objetivo = m_rate * m_obj
    progreso_pct = min(m_tot / max(1, pago_objetivo), 1.0) * 100
    color_bar = "#00e676" if progreso_pct >= 90 else "#ffeb3b" if progreso_pct >= 50 else "#ff1744"

    objetivo_hms = segundos_a_hms(int(m_obj * 60))
    total_hms = segundos_a_hms(int(total_min * 60))

    # Logica semana
    semana_val = semana_val_raw
    if USUARIO_ACTUAL == "Facundo":
        semana_val = -semana_val
    semana_val += progreso_en_dinero

    if semana_val > 0: semana_color = "#00e676"
    elif semana_val < 0: semana_color = "#ff1744"
    else: semana_color = "#aaa"

    if semana_val < 0: semana_str = f"-${abs(semana_val):.2f}"
    elif semana_val > 0: semana_str = f"+${semana_val:.2f}"
    else: semana_str = "$0.00"

    st.markdown(f"""
        <div style="background-color: #1e1e1e; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
            <div style="font-size: 1.2rem; color: #aaa; margin-bottom: 5px;">Hoy</div>
            <div style="width: 100%; font-size: 2.2rem; font-weight: bold; color: #fff; line-height: 1;">{total_hms} | ${m_tot:.2f}</div>
            <div style="width:100%; background-color:#333; border-radius:10px; height:12px; margin: 15px 0;">
                <div style="width:{progreso_pct}%; background-color:{color_bar}; height:100%; border-radius:10px; transition: width 0.5s;"></div>
            </div>
            <div style="display:flex; justify-content:space-between; color:#888;">
                <div>Semana: <span style="color:{semana_color};">{semana_str}</span></div>
                <div>{objetivo_hms} | ${pago_objetivo:.2f}</div>
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    # --- WIDGET SYNC ---
    w_total_hms = total_hms
    w_money = m_tot
    w_progress = int(progreso_pct)
    w_week_value = semana_val
    w_goal = f"{objetivo_hms} | ${pago_objetivo:.2f}"
    
    w_other_user_total_hms = "00:00:00"
    w_other_user_money = 0.0
    w_other_user_progress = 0
    
    js_code = f"""
    <script>
        if (window.AndroidBridge) {{
            window.AndroidBridge.updateWidgetData(
                "{w_total_hms}", {w_money}, {w_progress}, {w_week_value}, "{w_goal}",
                "{w_other_user_total_hms}", {w_other_user_money}, {w_other_user_progress}
            );
        }}
    </script>
    """
    import streamlit.components.v1 as components
    components.html(js_code, height=0)
    
    # ---- PROGRESO DEL OTRO USUARIO ----
    with st.expander(f"Progreso de {OTRO_USUARIO}.", expanded=True):
        o_tot, o_rate, o_obj, total_min_otro, _ = calcular_metricas(OTRO_USUARIO)
        o_pago_obj = o_rate * o_obj
        o_progreso_pct = min(o_tot / max(1, o_pago_obj), 1.0) * 100
        o_color_bar = "#00e676" if o_progreso_pct >= 90 else "#ffeb3b" if o_progreso_pct >= 50 else "#ff1744"
        o_obj_hms = segundos_a_hms(int(o_obj * 60))
        o_total_hms = segundos_a_hms(int(total_min_otro * 60))

        st.markdown(f"""
            <div style="margin-bottom: 10px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-size: 1.1rem; color: #ddd;"><b>{o_total_hms} | ${o_tot:.2f}</b></span>
                </div>
                <div style="width:100%; background-color:#444; border-radius:8px; height:8px; margin-top: 8px;">
                    <div style="width:{o_progreso_pct}%; background-color:{o_color_bar}; height:100%; border-radius:8px;"></div>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center; font-size:0.8rem; color:#aaa; margin-top:5px;">
                    <div style="display:flex; align-items:center;">
                        {circle_otro}
                        <span style="color:#00e676; margin-left:6px; visibility:{ 'visible' if materia_otro else 'hidden' };">
                            {materia_otro if materia_otro else 'Placeholder'}
                        </span>
                    </div>
                    <span style="font-size: 0.9rem; color: #888;">{o_obj_hms} | ${o_pago_obj:.2f}</span>
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
    st.subheader("Materias")

    mis_materias = USERS[USUARIO_ACTUAL]
    materia_en_curso = None
    for m, info in mis_materias.items():
        if str(datos[USUARIO_ACTUAL]["estado"][m]).strip() != "":
            materia_en_curso = m
            break

    for materia, info in mis_materias.items():
        est_raw = datos[USUARIO_ACTUAL]["estado"][materia]
        tiempo_acum = datos[USUARIO_ACTUAL]["tiempos"][materia]

        tiempo_anadido_seg = 0
        en_curso = False
        if str(est_raw).strip() != "":
            try:
                inicio = parse_datetime(est_raw)
                tiempo_anadido_seg = int((_argentina_now_global() - inicio).total_seconds())
                en_curso = True
            except:
                pass

        tiempo_total_hms = segundos_a_hms(hms_a_segundos(tiempo_acum) + max(0, tiempo_anadido_seg))
        badge_html = f'<div class="status-badge status-active">🟢 Estudiando...</div>' if en_curso else ''

        html_card = f"""<div class="materia-card">
<div class="materia-title">{materia}</div>
{badge_html}
<div class="materia-time">{tiempo_total_hms}</div>
</div>"""
        st.markdown(html_card, unsafe_allow_html=True)
        c_actions = st.container()

        with c_actions:
            if materia_en_curso == materia:
                if st.button(f"⛔ DETENER {materia[:10]}...", key=f"stop_{materia}", use_container_width=True, type="primary"):
                    try:
                        inicio = parse_datetime(est_raw)
                    except Exception as e:
                        st.error("Error fecha inicio.")
                        st.rerun()

                    fin = _argentina_now_global()
                    if fin <= inicio:
                        st.error("Tiempo inválido.")
                        batch_write([(info["est"], "")])
                        st.rerun()

                    midnight = datetime.combine(inicio.date() + timedelta(days=1), dt_time(0,0)).replace(tzinfo=inicio.tzinfo)
                    partes = []
                    if inicio.date() == fin.date():
                        partes.append((inicio, fin))
                    else:
                        partes.append((inicio, midnight))
                        partes.append((midnight, fin))

                    updates = []
                    for (p_inicio, p_fin) in partes:
                        segs = int((p_fin - p_inicio).total_seconds())
                        target_row = FILA_BASE + (p_inicio.date() - FECHA_BASE).days
                        time_cell_for_row = replace_row_in_range(info["time"], target_row)
                        
                        # Leer valor previo (aquí sí hacemos un GET extra pero es raro, solo al detener)
                        try:
                            # Optimizacion: Usar batchGet solo para esta celda
                            res = sheets_batch_get(st.secrets["sheet_id"], [time_cell_for_row])
                            vr = res.get("valueRanges", [{}])[0]
                            prev_raw = vr.get("values", [[""]])[0][0] if vr.get("values") else ""
                        except:
                            prev_raw = ""
                        
                        new_secs = parse_time_cell_to_seconds(prev_raw) + segs
                        updates.append((time_cell_for_row, segundos_a_hms(new_secs)))

                    updates.append((info["est"], ""))
                    batch_write(updates)
                    st.rerun()
            else:
                if materia_en_curso is None:
                    if st.button(f"▶ INICIAR", key=f"start_{materia}", use_container_width=True):
                        batch_write([
                            (info["est"], ahora_str())
                        ] + [(m_datos["est"], "") for m_datos in mis_materias.values()]) # Limpieza preventiva
                        st.rerun()
                else:
                    st.button("...", disabled=True, key=f"dis_{materia}", use_container_width=True)

        with st.expander("🛠️ Corregir tiempo manualmente"):
            new_val = st.text_input("Tiempo (HH:MM:SS)", value=tiempo_acum, key=f"input_{materia}")
            if st.button("Guardar Corrección", key=f"save_{materia}"):
                if ":" in new_val:
                    batch_write([(info["time"], new_val)])
                    st.rerun()
                else:
                    st.error("Formato inválido")

try:
    main()
except Exception as e:
    st.error(f"Error crítico: {e}")
    st.session_state.clear()
    st.markdown('<meta http-equiv="refresh" content="0">', unsafe_allow_html=True)
    st.rerun()
