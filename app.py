import re
import json
import time
import requests
from datetime import datetime, date, timedelta, time as dt_time
import streamlit as st
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from requests.exceptions import RequestException

# ------------------ CONFIG ------------------
st.set_page_config(page_title="Tiempo de Estudio", page_icon="⏳", layout="centered")

# ------------------ STYLES ------------------
st.markdown("""
    <style>
    /* ... (Mismos estilos) ... */
    html, body, [class*="css"] { font-size: 18px !important; }
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
    .materia-title { font-size: 1.4rem; font-weight: bold; color: #ffffff; margin-bottom: 5px; }
    .materia-time { font-size: 1.6rem; font-weight: bold; color: #00e676; font-family: 'Courier New', monospace; margin-bottom: 15px; }

    .status-badge { display: inline-block; padding: 5px 10px; border-radius: 12px; font-size: 0.9rem; font-weight: bold; margin-bottom: 10px; }
    .status-active { background-color: rgba(0, 230, 118, 0.2); color: #00e676; border: 1px solid #00e676; }

    div.stButton > button { height: 3.5rem; font-size: 1.2rem !important; font-weight: bold !important; border-radius: 12px !important; }
    </style>
""", unsafe_allow_html=True)

# ------------------ TIMEZONE HELPERS ------------------
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
        try: return hms_a_segundos(s)
        except: return 0
    try:
        f = float(s.replace(",", "."))
        if 0 <= f <= 1:
            return int(f * 86400)
        return int(f)
    except:
        return 0

def replace_row_in_range(range_str, new_row):
    if not isinstance(range_str, str): return range_str
    return re.sub(r'(\d+)(\s*$)', str(new_row), range_str)

def sanitize_key(s):
    return re.sub(r'[^a-zA-Z0-9_]', '_', s)

# ------------------ RERUN HELPER (recomendado para callbacks) ------------------
def pedir_rerun():
    """Establece un flag en session_state para que el rerun se haga fuera del callback."""
    st.session_state["_do_rerun"] = True

# ------------------ GOOGLE SHEETS SESSION ------------------
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

# La sesión NO debe ser cache_data para que no se use durante los callbacks (fuera de Streamlit flow)
session = get_sheets_session()

def sheets_batch_get(spreadsheet_id, ranges):
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values:batchGet"
    unique_ranges = list(dict.fromkeys(ranges))
    params = []
    for r in unique_ranges:
        params.append(("ranges", r))
    params.append(("valueRenderOption", "FORMATTED_VALUE"))
    try:
        resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        ordered_results = data.get("valueRanges", [])
        result_map = {r: res for r, res in zip(unique_ranges, ordered_results)}
        final_list = []
        for r in ranges:
            if r in result_map:
                final_list.append(result_map[r])
            else:
                final_list.append({})
        return {"valueRanges": final_list}
    except RequestException as e:
        # Aquí puedes añadir un mensaje más claro para el usuario
        raise RuntimeError(f"Error HTTP en batchGet al leer la hoja: {e}")

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
        # Aquí puedes añadir un mensaje más claro para el usuario
        raise RuntimeError(f"Error HTTP en batchUpdate al escribir en la hoja: {e}")

# ------------------ ANKI HELPERS ------------------
@st.cache_data(ttl=300) # Cachear por 5 minutos para no saturar la API en el rerun loop
def fetch_anki_stats(USUARIO_ACTUAL):
    # Obtener el ID del archivo desde st.secrets
    try:
        DRIVE_JSON_ID = st.secrets["ID_DEL_JSON_FACUNDO"] if USUARIO_ACTUAL == "Facundo" else st.secrets["ID_DEL_JSON_IVAN"]
        URL = f"https://drive.google.com/uc?id={DRIVE_JSON_ID}"
    except KeyError:
        # Si no está la key, retornamos datos vacíos o None
        return None

    try:
        response = requests.get(URL)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        # Si falla, retornamos None para manejarlo silenciosamente en la UI
        return None

# ------------------ CONSTANTES Y ESTRUCTURAS ------------------
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
        "Física":    {"time": f"'{SHEET_IVAN}'!B{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!F{MARCAS_ROW}"},
        "Análisis": {"time": f"'{SHEET_IVAN}'!C{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!G{MARCAS_ROW}"},
    }
}

RANGO_RATE_FACU = f"'{SHEET_MARCAS}'!C{TIME_ROW}"
RANGO_RATE_IVAN = f"'{SHEET_MARCAS}'!B{TIME_ROW}"
RANGO_OBJ_FACU = f"'{SHEET_MARCAS}'!P{TIME_ROW}"
RANGO_OBJ_IVAN = f"'{SHEET_MARCAS}'!O{TIME_ROW}"

# ------------------ CARGA UNIFICADA (cacheada) ------------------
@st.cache_data()
def cargar_datos_unificados():
    all_ranges = []
    mapa_indices = {"materias": {}, "rates": {}, "objs": {}, "week": None}
    idx = 0
    for user, materias in USERS.items():
        for m, info in materias.items():
            all_ranges.append(info["est"]); mapa_indices["materias"][(user, m, "est")] = idx; idx += 1
            all_ranges.append(info["time"]); mapa_indices["materias"][(user, m, "time")] = idx; idx += 1
    all_ranges.append(RANGO_RATE_FACU); mapa_indices["rates"]["Facundo"] = idx; idx += 1
    all_ranges.append(RANGO_RATE_IVAN); mapa_indices["rates"]["Iván"] = idx; idx += 1
    all_ranges.append(RANGO_OBJ_FACU); mapa_indices["objs"]["Facundo"] = idx; idx += 1
    all_ranges.append(RANGO_OBJ_IVAN); mapa_indices["objs"]["Iván"] = idx; idx += 1
    all_ranges.append(WEEK_RANGE); mapa_indices["week"] = idx; idx += 1

    try:
        res = sheets_batch_get(st.secrets["sheet_id"], all_ranges)
    except Exception as e:
        st.error(f"Error API Google Sheets: {e}")
        st.stop()

    values = res.get("valueRanges", [])
    def get_val(i, default=""):
        if i >= len(values): return default
        vr = values[i]; rows = vr.get("values", [])
        if not rows: return default
        return rows[0][0] if rows[0] else default

    data_usuarios = {u: {"estado": {}, "tiempos": {}, "inicio_dt": None, "materia_activa": None} for u in USERS}
    materia_en_curso = None
    inicio_dt = None

    for user, materias in USERS.items():
        for m in materias:
            idx_est = mapa_indices["materias"][(user, m, "est")]
            raw_est = get_val(idx_est)
            data_usuarios[user]["estado"][m] = raw_est

            idx_time = mapa_indices["materias"][(user, m, "time")]
            raw_time = get_val(idx_time)
            secs = parse_time_cell_to_seconds(raw_time)
            data_usuarios[user]["tiempos"][m] = segundos_a_hms(secs)

            if user == st.session_state.get("usuario_seleccionado") and str(raw_est).strip() != "":
                try:
                    inicio_dt = parse_datetime(raw_est)
                    materia_en_curso = m
                except Exception:
                    pass

    resumen = {
        "Facundo": {"per_min": parse_float_or_zero(get_val(mapa_indices["rates"]["Facundo"])), "obj": parse_float_or_zero(get_val(mapa_indices["objs"]["Facundo"]))},
        "Iván": {"per_min": parse_float_or_zero(get_val(mapa_indices["rates"]["Iván"])), "obj": parse_float_or_zero(get_val(mapa_indices["objs"]["Iván"]))}
    }
    raw_week = get_val(mapa_indices["week"], "0")
    balance_val = parse_float_or_zero(raw_week)

    if "usuario_seleccionado" in st.session_state:
        st.session_state["materia_activa"] = materia_en_curso
        st.session_state["inicio_dt"] = inicio_dt

    return {"users_data": data_usuarios, "resumen": resumen, "balance": balance_val}

def batch_write(updates):
    try:
        sheets_batch_update(st.secrets["sheet_id"], updates)
        cargar_datos_unificados.clear()
    except Exception as e:
        st.error(f"Error escribiendo Google Sheets: {e}")
        st.stop()

def start_materia_callback(usuario, materia):
    try:
        info = USERS[usuario][materia]
        now_str = ahora_str()
        updates = [(info["est"], now_str)] + [
            (m_datos["est"], "")
            for m_datos in USERS[usuario].values()
            if m_datos is not None and m_datos is not info
        ]
        batch_write(updates)
        st.session_state["materia_activa"] = materia
        st.session_state["inicio_dt"] = parse_datetime(now_str)
    except Exception as e:
        st.error(f"start_materia error: {e}")
    finally:
        pedir_rerun()

def stop_materia_callback(usuario, materia):
    try:
        info = USERS[usuario][materia]
        inicio = st.session_state.get("inicio_dt")
        prev_est = ""
        if inicio is None or st.session_state.get("materia_activa") != materia:
            st.warning("Marca de inicio no encontrada en session_state, releyendo de la hoja...")
            try:
                res = sheets_batch_get(st.secrets["sheet_id"], [info["est"]])
                vr = res.get("valueRanges", [{}])[0]
                prev_est = vr.get("values", [[""]])[0][0] if vr.get("values") else ""
                if not prev_est:
                      st.error("No hay marca de inicio registrada (no se puede detener).")
                      pedir_rerun()
                      return
                inicio = parse_datetime(prev_est)
            except Exception as e:
                 st.error(f"Error leyendo marca de inicio de la hoja: {e}")
                 pedir_rerun()
                 return

        fin = _argentina_now_global()
        if fin <= inicio:
            st.error("Tiempo inválido. La hora de fin es anterior a la de inicio.")
            batch_write([(info["est"], "")])
            pedir_rerun()
            return

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
            try:
                res2 = sheets_batch_get(st.secrets["sheet_id"], [time_cell_for_row])
                vr2 = res2.get("valueRanges", [{}])[0]
                prev_raw = vr2.get("values", [[""]])[0][0] if vr2.get("values") else ""
            except:
                prev_raw = ""
            new_secs = parse_time_cell_to_seconds(prev_raw) + segs
            updates.append((time_cell_for_row, segundos_a_hms(new_secs)))

        updates.append((info["est"], ""))
        batch_write(updates)
        st.session_state["materia_activa"] = None
        st.session_state["inicio_dt"] = None
    except Exception as e:
        st.error(f"stop_materia error: {e}")
    finally:
        pedir_rerun()

def main():
    if st.session_state.get("_do_rerun", False):
        st.session_state["_do_rerun"] = False
        st.rerun()

    st.sidebar.header("🔧 Debug & Controls")
    st.sidebar.markdown("**session_state**")
    st.sidebar.write(dict(st.session_state))
    if st.sidebar.button("Test click (sidebar)"):
        st.sidebar.write("Click registrado:", ahora_str())

    try:
        params = st.query_params
    except Exception:
        params = st.experimental_get_query_params()

    if "usuario_seleccionado" not in st.session_state:
        def set_user_and_rerun(u):
            st.session_state["usuario_seleccionado"] = u
            st.rerun()

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

    datos_globales = cargar_datos_unificados()
    datos = datos_globales["users_data"]
    resumen_marcas = datos_globales["resumen"]
    balance_val_raw = datos_globales["balance"]

    USUARIO_ACTUAL = st.session_state["usuario_seleccionado"]
    OTRO_USUARIO = "Iván" if USUARIO_ACTUAL == "Facundo" else "Facundo"

    materia_en_curso = st.session_state.get("materia_activa")
    inicio_dt = st.session_state.get("inicio_dt")

    if materia_en_curso is None:
        for m, est_raw in datos[USUARIO_ACTUAL]["estado"].items():
            if str(est_raw).strip() != "":
                try:
                    inicio_dt_sheet = parse_datetime(est_raw)
                    st.session_state["materia_activa"] = m
                    st.session_state["inicio_dt"] = inicio_dt_sheet
                    materia_en_curso = m
                    inicio_dt = inicio_dt_sheet
                except Exception:
                    pass
                break

    usuario_estudiando = materia_en_curso is not None

    materia_otro = next((m for m, v in datos[OTRO_USUARIO]["estado"].items() if str(v).strip() != ""), "")
    otro_estudiando = materia_otro != ""

    def circle(color):
        return (f'<span style="display:inline-flex; align-items:center; justify-content:center; '
                f'width:10px; height:10px; border-radius:50%; background:{color}; '
                f'margin-right:6px; flex-shrink:0;"></span>')

    circle_usuario = circle("#00e676" if usuario_estudiando else "#ffffff")
    circle_otro = circle("#00e676" if otro_estudiando else "#ffffff")

    placeholder_total = st.empty()
    placeholder_materias = {m: st.empty() for m in USERS[USUARIO_ACTUAL]}

    while True:
        tiempo_anadido_seg = 0
        if usuario_estudiando and inicio_dt is not None:
            tiempo_anadido_seg = int((_argentina_now_global() - inicio_dt).total_seconds())

        def calcular_metricas(usuario, tiempo_activo_seg_local=0):
            per_min = resumen_marcas[usuario]["per_min"]
            objetivo = resumen_marcas[usuario]["obj"]
            total_min = 0.0
            progreso = 0.0

            for materia, info in USERS[usuario].items():
                base_seg = hms_a_segundos(datos[usuario]["tiempos"][materia])
                segs_materia = base_seg
                if usuario_estudiando and usuario == USUARIO_ACTUAL and materia == materia_en_curso:
                    segs_materia += tiempo_activo_seg_local
                total_min += segs_materia / 60

            progreso_en_dinero = (tiempo_activo_seg_local / 60) * per_min
            m_tot = total_min * per_min
            return m_tot, per_min, objetivo, total_min, progreso_en_dinero

        m_tot, m_rate, m_obj, total_min, progreso_en_dinero = calcular_metricas(USUARIO_ACTUAL, tiempo_anadido_seg)
        pago_objetivo = m_rate * m_obj
        progreso_pct = min(m_tot / max(1, pago_objetivo), 1.0) * 100
        color_bar = "#00e676" if progreso_pct >= 90 else "#ffeb3b" if progreso_pct >= 50 else "#ff1744"

        objetivo_hms = segundos_a_hms(int(m_obj * 60))
        total_hms = segundos_a_hms(int(total_min * 60))

        balance_val = balance_val_raw
        if USUARIO_ACTUAL == "Facundo":
            balance_val = -balance_val
        balance_val += progreso_en_dinero
        balance_color = "#00e676" if balance_val > 0 else "#ff1744" if balance_val < 0 else "#aaa"
        balance_str = f"+${balance_val:.2f}" if balance_val > 0 else (f"-${abs(balance_val):.2f}" if balance_val < 0 else "$0.00")

        # --- Actualizar Placeholder Global ---
        with placeholder_total.container():
            st.markdown(f"""
                <div style="background-color: #1e1e1e; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
                    <div style="font-size: 1.2rem; color: #aaa; margin-bottom: 5px;">Hoy</div>
                    <div style="width: 100%; font-size: 2.2rem; font-weight: bold; color: #fff; line-height: 1;">{total_hms} | ${m_tot:.2f}</div>
                    <div style="width:100%; background-color:#333; border-radius:10px; height:12px; margin: 15px 0;">
                        <div style="width:{progreso_pct}%; background-color:{color_bar}; height:100%; border-radius:10px; transition: width 0.5s;"></div>
                    </div>
                    <div style="display:flex; justify-content:space-between; color:#888;">
                        <div>Balance: <span style="color:{balance_color};">{balance_str}</span></div>
                        <div>{objetivo_hms} | ${pago_objetivo:.2f}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

            # --- PROGRESO DEL OTRO USUARIO ---
            o_tot, o_rate, o_obj, total_min_otro, _ = calcular_metricas(OTRO_USUARIO)
            o_pago_obj = o_rate * o_obj
            o_progreso_pct = min(o_tot / max(1, o_pago_obj), 1.0) * 100
            o_color_bar = "#00e676" if o_progreso_pct >= 90 else "#ffeb3b" if o_progreso_pct >= 50 else "#ff1744"
            o_obj_hms = segundos_a_hms(int(o_obj * 60))
            o_total_hms = segundos_a_hms(int(total_min_otro * 60))

            materia_visible = 'visible' if materia_otro else 'hidden'
            materia_nombre_html = f'<span style="color:#00e676; margin-left:6px; visibility:{materia_visible};">{materia_otro if materia_otro else ""}</span>'
            o_obj_color = "#00e676" if otro_estudiando else "#888"

            with st.expander(f"Progreso de {OTRO_USUARIO}.", expanded=True):
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
                                {materia_nombre_html}
                            </div>
                            <span style="font-size: 0.9rem; color: {o_obj_color};">{o_obj_hms} | ${o_pago_obj:.2f}</span>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

            # ------------------ ANKI STATS (NUEVO / SOPORTE MÚLTIPLES MAZOS) ---
            anki_data = fetch_anki_stats(USUARIO_ACTUAL)
            
            # Colores para las barras
            C_MATURE = "#31A354"
            C_YOUNG = "#74C476"
            C_OTHER = "#BDBDBD"
            
            if anki_data:
                with st.expander("Anki"):
                    # Iteramos sobre los mazos del JSON (ej: "🇩🇪 Alemán", "Matemáticas", etc)
                    for deck_name, stats in anki_data.items():
                        
                        # NUEVA LÓGICA: Determinar qué colección de estadísticas usar.
                        # 1. Si 'stats' es un dict y *contiene* las claves de stats ("total", "young", etc.),
                        #    entonces es un mazo simple. (Comportamiento original, pero lo manejaremos abajo si es un submazo).
                        # 2. Si 'stats' es un dict y *NO contiene* las claves de stats, asumimos que son submazos.
                        
                        # Verificamos si es un mazo contenedor (padre) de submazos
                        if isinstance(stats, dict) and 'total' not in stats:
                            
                            # Renderizamos solo el título del mazo principal/padre
                            st.markdown(f"## {deck_name}", unsafe_allow_html=True)
                            
                            # Iteramos sobre los submazos
                            for subdeck_name, sub_stats in stats.items():
                                if not isinstance(sub_stats, dict):
                                    continue
                                    
                                # Las estadísticas del submazo son 'sub_stats'
                                a_total = sub_stats.get("total", 0)
                                a_young = sub_stats.get("young", 0)
                                a_mature = sub_stats.get("mature", 0)
                                
                                # El resto de la lógica para submazos es la misma:
                                a_other = max(0, a_total - a_mature - a_young)
            
                                # Porcentajes para la barra
                                if a_total > 0:
                                    p_mat = (a_mature / a_total) * 100
                                    p_you = (a_young / a_total) * 100
                                    p_oth = (a_other / a_total) * 100
                                else:
                                    p_mat, p_you, p_oth = 0, 0, 0
                                    
                                # Renderizamos el Título del SUBmazo
                                # Usamos un tamaño más pequeño (h3 o simplemente negrita) para el submazo
                                st.markdown(f"**{subdeck_name}** <span style='color:#888; font-size:0.8em;'>({a_total} cartas)</span>", unsafe_allow_html=True)
            
                                # Renderizamos los detalles y la barra de progreso
                                st.markdown(f"""
                                    <div style="display: flex; justify-content: space-between; font-size: 0.8em; margin-bottom: 2px; color: #ccc;">
                                        <span style="color: {C_MATURE};">Maduras: {a_mature} ({p_mat:.0f}%)</span>
                                        <span style="color: {C_YOUNG};">Jóvenes: {a_young} ({p_you:.0f}%)</span>
                                        <span style="color: {C_OTHER};">Otros: {a_other}</span>
                                    </div>
                                    <div style="width: 100%; height: 15px; border-radius: 5px; overflow: hidden; display: flex; border: 1px solid #444; margin-bottom: 15px;">
                                        <div title="Mature" style="background-color: {C_MATURE}; width: {p_mat}%; height: 100%;"></div>
                                        <div title="Young" style="background-color: {C_YOUNG}; width: {p_you}%; height: 100%;"></div>
                                        <div title="Otros" style="background-color: {C_OTHER}; width: {p_oth}%; height: 100%;"></div>
                                    </div>
                                """, unsafe_allow_html=True)
                            
                        # Comportamiento para mazo simple (No es un mazo padre de submazos, sino un mazo con stats directas)
                        elif isinstance(stats, dict) and 'total' in stats: 
                            
                            # Comportamiento original si es un mazo simple
                            a_total = stats.get("total", 0)
                            a_young = stats.get("young", 0)
                            a_mature = stats.get("mature", 0)
                            a_other = max(0, a_total - a_mature - a_young)
            
                            if a_total > 0:
                                p_mat = (a_mature / a_total) * 100
                                p_you = (a_young / a_total) * 100
                                p_oth = (a_other / a_total) * 100
                            else:
                                p_mat, p_you, p_oth = 0, 0, 0
                            
                            st.markdown(f"**{deck_name}** <span style='color:#888; font-size:0.8em;'>({a_total} cartas)</span>", unsafe_allow_html=True)
            
                            # Renderizamos los detalles y la barra de progreso
                            st.markdown(f"""
                                <div style="display: flex; justify-content: space-between; font-size: 0.8em; margin-bottom: 2px; color: #ccc;">
                                    <span style="color: {C_MATURE};">Mat: {a_mature} ({p_mat:.0f}%)</span>
                                    <span style="color: {C_YOUNG};">Yng: {a_young} ({p_you:.0f}%)</span>
                                    <span style="color: {C_OTHER};">Oth: {a_other}</span>
                                </div>
                                <div style="width: 100%; height: 15px; border-radius: 5px; overflow: hidden; display: flex; border: 1px solid #444; margin-bottom: 15px;">
                                    <div title="Mature" style="background-color: {C_MATURE}; width: {p_mat}%; height: 100%;"></div>
                                    <div title="Young" style="background-color: {C_YOUNG}; width: {p_you}%; height: 100%;"></div>
                                    <div title="Otros" style="background-color: {C_OTHER}; width: {p_oth}%; height: 100%;"></div>
                                </div>
                            """, unsafe_allow_html=True)

            # --- MANIFIESTO ---
            with st.expander("ℹ️ No pensar, actuar."):
                md_content = st.secrets["md"]["facundo"] if USUARIO_ACTUAL == "Facundo" else st.secrets["md"]["ivan"]
                st.markdown(md_content)

            st.subheader("Materias")
        
        # --- Actualizar Placeholders de Materias y Botones ---
        mis_materias = USERS[USUARIO_ACTUAL]
        for materia, info in mis_materias.items():

            base_seg = hms_a_segundos(datos[USUARIO_ACTUAL]["tiempos"][materia])
            tiempo_total_seg = base_seg
            en_curso = materia_en_curso == materia

            if en_curso:
                tiempo_total_seg += max(0, tiempo_anadido_seg)

            tiempo_total_hms = segundos_a_hms(tiempo_total_seg)
            badge_html = f'<div class="status-badge status-active">🟢 Estudiando...</div>' if en_curso else ''
            html_card = f"""<div class="materia-card"><div class="materia-title">{materia}</div>{badge_html}<div class="materia-time">{tiempo_total_hms}</div></div>"""

            with placeholder_materias[materia].container():
                st.markdown(html_card, unsafe_allow_html=True)

                key_start = sanitize_key(f"start_{USUARIO_ACTUAL}_{materia}")
                key_stop = sanitize_key(f"stop_{USUARIO_ACTUAL}_{materia}")
                key_disabled = sanitize_key(f"dis_{USUARIO_ACTUAL}_{materia}")

                cols = st.columns([1,1,1])
                with cols[0]:
                    if en_curso:
                        st.button(f"⛔ DETENER {materia[:14]}", key=key_stop, use_container_width=True,
                                  on_click=stop_materia_callback, args=(USUARIO_ACTUAL, materia))
                    else:
                        if materia_en_curso is None:
                            st.button("▶ INICIAR", key=key_start, use_container_width=True,
                                      on_click=start_materia_callback, args=(USUARIO_ACTUAL, materia))
                        else:
                            st.button("...", disabled=True, key=key_disabled, use_container_width=True)

                with cols[1]:
                    with st.expander("🛠️ Corregir tiempo manualmente"):
                        input_key = f"input_{sanitize_key(materia)}"
                        new_val = st.text_input("Tiempo (HH:MM:SS)", value=datos[USUARIO_ACTUAL]["tiempos"][materia], key=input_key)

                        def save_correction_callback(materia_key):
                            if st.session_state.get("materia_activa") is not None:
                                st.error("⛔ No podés corregir el tiempo mientras estás estudiando.")
                                pedir_rerun()
                                return

                            val = st.session_state.get(f"input_{sanitize_key(materia_key)}", "").strip()
                            if ":" not in val:
                                st.error("Formato inválido (debe ser HH:MM:SS)")
                                pedir_rerun()
                                return

                            try:
                                segs = hms_a_segundos(val)
                                hhmmss = segundos_a_hms(segs)
                                target_row = get_time_row()  # recalculamos por si cambió
                                time_cell_for_row = replace_row_in_range(USERS[USUARIO_ACTUAL][materia_key]["time"], target_row)
                                batch_write([(time_cell_for_row, hhmmss)])
                                st.success("Tiempo corregido correctamente.")
                            except Exception as e:
                                st.error(f"Error al corregir el tiempo: {e}")
                            finally:
                                pedir_rerun()

                        if en_curso or usuario_estudiando:
                            st.info("⛔ No podés corregir el tiempo mientras estás estudiando.")
                        else:
                            if st.button("Guardar Corrección", key=f"save_{sanitize_key(materia)}", on_click=save_correction_callback, args=(materia,)):
                                pass

        if not usuario_estudiando:
            st.stop()

        time.sleep(10)
        st.rerun()

    st.write("")
    if st.sidebar.button("🔄 Forzar limpieza session_state"):
        st.session_state.clear()
        st.rerun()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        st.error(f"Error crítico en main(): {e}")
        st.sidebar.error(f"Error crítico: {e}")
        if st.sidebar.button("Reiniciar sesión (limpiar estado)"):
            st.session_state.clear()
            st.rerun()
