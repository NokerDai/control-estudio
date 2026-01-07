import re
import json
import time
import smtplib
from datetime import datetime, date, timedelta, time as dt_time
import streamlit as st
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from requests.exceptions import RequestException

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

def cargar_estilos():
    st.markdown("""
        <style>
        html, body, [class*="css"] { font-size: 18px !important; }
        h1 { font-size: 2.5rem !important; }
        h2 { font-size: 2rem !important; }
        h3 { font-size: 1.5rem !important; }

        /* Estilo de la tarjeta */
        .materia-card {
            background-color: #262730;
            border: 1px solid #464b5c;
            padding: 20px;
            border-radius: 15px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }
        .materia-title { font-size: 1.4rem; font-weight: bold; color: #ffffff; margin-bottom: 5px; }
        
        /* EL TIEMPO */
        .materia-time { 
            font-size: 1.6rem; 
            font-weight: bold; 
            color: #00e676; 
            font-family: 'Courier New', monospace; 
            margin-bottom: 15px; 
        }

        .status-badge { display: inline-block; padding: 5px 10px; border-radius: 12px; font-size: 0.9rem; font-weight: bold; margin-bottom: 10px; }
        .status-active { background-color: rgba(0, 230, 118, 0.2); color: #00e676; border: 1px solid #00e676; }

        div.stButton > button { height: 3.5rem; font-size: 1.2rem !important; font-weight: bold !important; border-radius: 12px !important; }
        </style>
    """, unsafe_allow_html=True)

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

# ------------------ RERUN HELPER ------------------
def pedir_rerun():
    st.session_state["_do_rerun"] = True

# ------------------ GOOGLE SHEETS SESSION ------------------
@st.cache_resource
def get_sheets_session():
    try:
        key_dict = json.loads(st.secrets["service_account"])
    except Exception as e:
        st.error(f"Error leyendo st.secrets['service_account']")
        st.stop()
    try:
        creds = service_account.Credentials.from_service_account_info(
            key_dict,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        return AuthorizedSession(creds)
    except Exception as e:
        st.error(f"Error creando credenciales")
        st.stop()

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
        raise RuntimeError(f"Error HTTP en batchUpdate al escribir en la hoja: {e}")

# ------------------ CONSTANTES ESTRUCTURALES (FIJAS) ------------------
FILA_BASE = 5
FECHA_BASE = date(2026, 1, 1)
SHEET_FACUNDO = "F. Economía"
SHEET_IVAN = "I. Física"
SHEET_MARCAS = "marcas"

RANGO_FECHA_MAIL = f"'{SHEET_MARCAS}'!Z1"
RANGO_LOCK_IVAN = f"'{SHEET_MARCAS}'!Z2"
RANGO_LOCK_FACUNDO = f"'{SHEET_MARCAS}'!Z3"
RANGO_FECHA_MAIL_VAGO = f"'{SHEET_MARCAS}'!Z12" 

# ------------------ CONFIGURACIÓN DINÁMICA DEL DÍA ------------------
# Esta función reemplaza las constantes globales que causaban el bug.
# Calcula los rangos basándose en el momento en que se llama.

def get_day_config(target_date=None):
    if target_date is None:
        target_date = _argentina_now_global().date()
    
    delta = (target_date - FECHA_BASE).days
    time_row = FILA_BASE + delta
    
    # Construimos los rangos dinámicamente usando time_row actual
    users_dict = {
        "Facundo": {
            "Matemática 2":    {"time": f"'{SHEET_FACUNDO}'!B{time_row}", "est": f"'{SHEET_MARCAS}'!Z4"},
            "Matemática 3":    {"time": f"'{SHEET_FACUNDO}'!C{time_row}", "est": f"'{SHEET_MARCAS}'!Z5"},
            "Macroeconomía 1": {"time": f"'{SHEET_FACUNDO}'!D{time_row}", "est": f"'{SHEET_MARCAS}'!Z6"},
            "Historia":        {"time": f"'{SHEET_FACUNDO}'!E{time_row}", "est": f"'{SHEET_MARCAS}'!Z7"},
        },
        "Iván": {
            "Física":   {"time": f"'{SHEET_IVAN}'!B{time_row}", "est": f"'{SHEET_MARCAS}'!Z8"},
            "Análisis": {"time": f"'{SHEET_IVAN}'!C{time_row}", "est": f"'{SHEET_MARCAS}'!Z9"},
        }
    }
    
    return {
        "TIME_ROW": time_row,
        "USERS": users_dict,
        "WEEK_RANGE": f"'{SHEET_MARCAS}'!R{time_row-2}",
        "RANGO_RATE_FACU": f"'{SHEET_MARCAS}'!C{time_row-2}",
        "RANGO_RATE_IVAN": f"'{SHEET_MARCAS}'!B{time_row-2}",
        "RANGO_OBJ_FACU": f"'{SHEET_MARCAS}'!P{time_row-2}",
        "RANGO_OBJ_IVAN": f"'{SHEET_MARCAS}'!O{time_row-2}",
        "RANGO_CHECK_IVAN": f"'{SHEET_MARCAS}'!H{time_row-2}",
        "RANGO_CHECK_FACU": f"'{SHEET_MARCAS}'!I{time_row-2}",
        "RANGO_POZO_IVAN": f"'{SHEET_MARCAS}'!W{time_row-2}",
        "RANGO_POZO_FACU": f"'{SHEET_MARCAS}'!X{time_row-2}",
    }

# ------------------ CARGA UNIFICADA (cacheada por fecha) ------------------
# Agregamos fecha_str como argumento para que el cache se invalide al cambiar el día
@st.cache_data()
def cargar_datos_unificados(fecha_str):
    # Obtenemos la config para el día actual
    cfg = get_day_config() # Usa la fecha actual por defecto (que coincide con fecha_str)
    USERS_LOCAL = cfg["USERS"]
    
    yesterday = _argentina_now_global().date() - timedelta(days=1)
    cfg_yesterday = get_day_config(yesterday)
    
    all_ranges = []
    mapa_indices = {"materias": {}, "rates": {}, "objs": {}, "checks": {}, "week": None, "week_ayer": None, "mail_date": None, "mail_vago": None}
    idx = 0
    
    for user, materias in USERS_LOCAL.items():
        for m, info in materias.items():
            all_ranges.append(info["est"]); mapa_indices["materias"][(user, m, "est")] = idx; idx += 1
            all_ranges.append(info["time"]); mapa_indices["materias"][(user, m, "time")] = idx; idx += 1
    
    all_ranges.append(cfg["RANGO_RATE_FACU"]); mapa_indices["rates"]["Facundo"] = idx; idx += 1
    all_ranges.append(cfg["RANGO_RATE_IVAN"]); mapa_indices["rates"]["Iván"] = idx; idx += 1
    all_ranges.append(cfg["RANGO_OBJ_FACU"]); mapa_indices["objs"]["Facundo"] = idx; idx += 1
    all_ranges.append(cfg["RANGO_OBJ_IVAN"]); mapa_indices["objs"]["Iván"] = idx; idx += 1
    all_ranges.append(cfg["WEEK_RANGE"]); mapa_indices["week"] = idx; idx += 1
    all_ranges.append(cfg_yesterday["WEEK_RANGE"]); mapa_indices["week_ayer"] = idx; idx += 1
    
    all_ranges.append(RANGO_FECHA_MAIL); mapa_indices["mail_date"] = idx; idx += 1
    all_ranges.append(RANGO_FECHA_MAIL_VAGO); mapa_indices["mail_vago"] = idx; idx += 1
    
    all_ranges.append(cfg["RANGO_CHECK_IVAN"]); mapa_indices["checks"]["Iván"] = idx; idx += 1
    all_ranges.append(cfg["RANGO_CHECK_FACU"]); mapa_indices["checks"]["Facundo"] = idx; idx += 1

    all_ranges.append(cfg["RANGO_POZO_IVAN"]); mapa_indices["pozo_ivan"] = idx; idx += 1
    all_ranges.append(cfg["RANGO_POZO_FACU"]); mapa_indices["pozo_facu"] = idx; idx += 1

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

    data_usuarios = {u: {"estado": {}, "tiempos": {}, "inicio_dt": None, "materia_activa": None} for u in USERS_LOCAL}
    materia_en_curso = None
    inicio_dt = None

    for user, materias in USERS_LOCAL.items():
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
    
    raw_week_ayer = get_val(mapa_indices["week_ayer"], "0")
    balance_val_ayer = parse_float_or_zero(raw_week_ayer)
    
    last_mail_date = get_val(mapa_indices["mail_date"], "")
    last_mail_vago = get_val(mapa_indices["mail_vago"], "")

    checks_data = {
        "Iván": get_val(mapa_indices["checks"]["Iván"], ""),
        "Facundo": get_val(mapa_indices["checks"]["Facundo"], "")
    }

    pozo_ivan_val = parse_float_or_zero(get_val(mapa_indices["pozo_ivan"]))
    pozo_facu_val = parse_float_or_zero(get_val(mapa_indices["pozo_facu"]))

    if "usuario_seleccionado" in st.session_state:
        st.session_state["materia_activa"] = materia_en_curso
        st.session_state["inicio_dt"] = inicio_dt

    return {
        "users_data": data_usuarios, 
        "resumen": resumen, 
        "balance": balance_val,
        "balance_ayer": balance_val_ayer,
        "last_mail_date": last_mail_date,
        "last_mail_vago": last_mail_vago,
        "checks": checks_data,
        "pozo_ivan": pozo_ivan_val,
        "pozo_facu": pozo_facu_val
    }

def batch_write(updates):
    try:
        sheets_batch_update(st.secrets["sheet_id"], updates)
        # Limpiamos el cache usando la fecha actual
        cargar_datos_unificados.clear()
    except Exception as e:
        st.error(f"Error escribiendo Google Sheets: {e}")
        st.stop()
        
# ------------------ FUNCIONES DE LOCKEO DE SESIÓN ------------------

def get_lock_range(user):
    if user == "Facundo":
        return RANGO_LOCK_FACUNDO
    elif user == "Iván":
        return RANGO_LOCK_IVAN
    return None

@st.cache_data(ttl=2)
def get_user_lock_status(user):
    range_str = get_lock_range(user)
    if not range_str: return ""
    try:
        res = sheets_batch_get(st.secrets["sheet_id"], [range_str])
        vr = res.get("valueRanges", [{}])[0]
        return str(vr.get("values", [[""]])[0][0] if vr.get("values") else "").strip()
    except Exception as e:
        st.error(f"Error leyendo estado de lock para {user}: {e}")
        return "ERROR_READING_LOCK"

def set_user_lock_status(user, lock_value):
    range_str = get_lock_range(user)
    if not range_str: return False
    try:
        sheets_batch_update(st.secrets["sheet_id"], [(range_str, lock_value)])
        get_user_lock_status.clear()
        return True
    except Exception as e:
        st.error(f"Error escribiendo estado de lock para {user}: {e}")
        return False

# ------------------ CALLBACKS ACTUALIZADOS ------------------
def start_materia_callback(usuario, materia):
    try:
        cfg = get_day_config() # Obtenemos configuración dinámica
        info = cfg["USERS"][usuario][materia]
        
        now_str = ahora_str()
        updates = [(info["est"], now_str)] + [
            (m_datos["est"], "")
            for m_datos in cfg["USERS"][usuario].values()
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
        cfg = get_day_config() # Config actual
        info = cfg["USERS"][usuario][materia]
        
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
            
            # --- Corrección dinámica de fila para cada fragmento de tiempo ---
            # Si cruza la medianoche, esto escribe en la fila correspondiente al día del fragmento
            target_row = FILA_BASE + (p_inicio.date() - FECHA_BASE).days
            
            # Reconstruimos el rango de tiempo usando la fila correcta
            # Usamos una instancia temporal de config para obtener la columna base
            # Como la columna B/C/D no cambia, usamos la config actual para obtener la letra
            # y reemplazamos el número de fila.
            current_time_range = cfg["USERS"][usuario][materia]["time"]
            time_cell_for_row = replace_row_in_range(current_time_range, target_row)
            
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
    st.set_page_config(
        page_title="Estudio",
        page_icon="📖"
    )
    cargar_estilos()

    if st.session_state.get("_do_rerun", False):
        st.session_state["_do_rerun"] = False
        st.rerun()
        
    if "usuario_seleccionado" not in st.session_state or st.session_state["usuario_seleccionado"] not in ["Facundo", "Iván"]:
        st.error("Error: Usuario no seleccionado en la sesión. Reinicia la aplicación.")
        st.stop()
        
    # --- Carga de datos ---
    hoy_str = _argentina_now_global().strftime("%Y-%m-%d")
    datos_globales = cargar_datos_unificados(hoy_str) # Pasamos la fecha string para cache key
    
    # Recargamos la config local para usar en la UI
    cfg = get_day_config()
    USERS_LOCAL = cfg["USERS"]
    
    datos = datos_globales["users_data"]
    resumen_marcas = datos_globales["resumen"]
    balance_val_raw = datos_globales["balance"]
    balance_val_ayer_raw = datos_globales["balance_ayer"]
    last_mail_date_str = datos_globales["last_mail_date"]
    last_mail_vago_str = datos_globales["last_mail_vago"]
    checks_data = datos_globales["checks"]

    pozo_ivan = datos_globales["pozo_ivan"]
    pozo_facu = datos_globales["pozo_facu"]

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
    placeholder_materias = {m: st.empty() for m in USERS_LOCAL[USUARIO_ACTUAL]}

    while True:
        tiempo_anadido_seg = 0
        if usuario_estudiando and inicio_dt is not None:
            tiempo_anadido_seg = int((_argentina_now_global() - inicio_dt).total_seconds())

        def calcular_metricas(usuario, tiempo_activo_seg_local=0):
            per_min = resumen_marcas[usuario]["per_min"]
            objetivo = resumen_marcas[usuario]["obj"]
            total_min = 0.0

            # Usamos USERS_LOCAL (dinámico)
            for materia, info in USERS_LOCAL[usuario].items():
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
        if progreso_pct >= 100 and "password_triggered" not in st.session_state:
            st.session_state.goal_completed = True
            st.session_state.password_triggered = True
            st.rerun()
        color_bar = "#00e676" if progreso_pct >= 90 else "#ffeb3b" if progreso_pct >= 50 else "#ff1744"

        objetivo_hms = segundos_a_hms(int(m_obj * 60))
        total_hms = segundos_a_hms(int(total_min * 60))

        pozo_valor = pozo_facu if USUARIO_ACTUAL == "Facundo" else pozo_ivan
        pozo_valor -= m_tot
        if pozo_valor < 0:
            m_tot += pozo_valor
            pozo_valor = 0.0
        pozo_color = "#00e676" if round(pozo_valor) != 0 else "#aaa"

        balance_val = balance_val_ayer_raw
        if USUARIO_ACTUAL == "Facundo":
            balance_val = -balance_val
        balance_val += m_tot
        balance_color = "#00e676" if balance_val > 0 else "#ff1744" if balance_val < 0 else "#aaa"
        balance_str = f"+${balance_val:.2f}" if balance_val > 0 else (f"-${abs(balance_val):.2f}" if balance_val < 0 else "$0.00")

        # --- Actualizar Placeholder Global ---
        with placeholder_total.container():
            st.markdown(f"""
                <div style="background-color: #1e1e1e; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div style="font-size: 1.2rem; color: #aaa;">Hoy</div>
                        <div style="display:flex; align-items:center; gap:6px; font-size:0.9rem;">
                            <span style="color:#aaa;">Pozo:</span>
                            <span style="color:{pozo_color};">${pozo_valor:.2f}</span>
                        </div>
                    </div>
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
            
            check_actual = checks_data.get(USUARIO_ACTUAL, "1")
            if str(check_actual).strip() == "":
                def marcar_dia_callback(u):
                    cfg_cb = get_day_config()
                    target_range = cfg_cb["RANGO_CHECK_IVAN"] if u == "Iván" else cfg_cb["RANGO_CHECK_FACU"]
                    batch_write([(target_range, 1)])
                    pedir_rerun()

                st.sidebar.button("Fui a clases", key="check_day_btn", on_click=marcar_dia_callback, args=(USUARIO_ACTUAL,), use_container_width=True)

            o_tot, o_rate, o_obj, total_min_otro, _ = calcular_metricas(OTRO_USUARIO)
            o_pago_obj = o_rate * o_obj
            o_progreso_pct = min(o_tot / max(1, o_pago_obj), 1.0) * 100
            o_color_bar = "#00e676" if o_progreso_pct >= 90 else "#ffeb3b" if o_progreso_pct >= 50 else "#ff1744"
            o_obj_hms = segundos_a_hms(int(o_obj * 60))
            o_total_hms = segundos_a_hms(int(total_min_otro * 60))

            materia_visible = 'visible' if materia_otro else 'hidden'
            materia_nombre_html = f'<span style="color:#00e676; margin-left:6px; visibility:{materia_visible};">{materia_otro if materia_otro else ""}</span>'

            with st.expander(f"Progreso de {OTRO_USUARIO}."):
                 st.markdown(f"""
                    <div style="margin-bottom: 10px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <span style="font-size: 1.1rem; color: #aaa;"><b>{o_total_hms} | ${o_tot:.2f}</b></span>
                        </div>
                        <div style="width:100%; background-color:#444; border-radius:8px; height:8px; margin-top: 8px;">
                            <div style="width:{o_progreso_pct}%; background-color:{o_color_bar}; height:100%; border-radius:8px;"></div>
                        </div>
                        <div style="display:flex; justify-content:space-between; align-items:center; font-size:0.8rem; color:#aaa; margin-top:5px;">
                            <div style="display:flex; align-items:center;">
                                {circle_otro}
                                {materia_nombre_html}
                            </div>
                            <span style="font-size: 0.9rem; color: #aaa;">{o_obj_hms} | ${o_pago_obj:.2f}</span>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

            with st.expander("ℹ️ No pensar, actuar."):
                md_content = st.secrets["facundo_md"] if USUARIO_ACTUAL == "Facundo" else st.secrets["ivan_md"]
                st.markdown(md_content)
        
        # --- Actualizar Placeholders de Materias y Botones ---
        mis_materias = USERS_LOCAL[USUARIO_ACTUAL]
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
                        # Usamos el tiempo actual de datos, que puede venir de cache pero es razonablemente reciente
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
                                # Usamos config dinámica para saber en qué celda escribir AHORA
                                cfg_corr = get_day_config()
                                time_cell_for_row = cfg_corr["USERS"][USUARIO_ACTUAL][materia_key]["time"]
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

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        st.error(f"Error crítico en main(): {e}")
        st.sidebar.error(f"Error crítico: {e}")
        if st.sidebar.button("Reiniciar sesión (limpiar estado)"):
            st.session_state.clear()
            st.rerun()
