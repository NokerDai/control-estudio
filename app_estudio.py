import re
import json
import time
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

        /* Botones de acción principales (GRANDES como antes) */
        div.stButton > button { 
            height: 3.5rem; 
            font-size: 1.2rem !important; 
            font-weight: bold !important; 
            border-radius: 12px !important; 
        }

        /* Clase especial para botones finos (Actualizar y Guardar) */
        div.fino-button div.stButton > button {
            height: auto !important;
            padding: 4px 10px !important;
            font-size: 0.9rem !important;
            font-weight: normal !important;
        }
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

def pedir_rerun():
    st.session_state["_do_rerun"] = True

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

# --- CONSTANTES ---
FILA_BASE = 5
FILA_BASE2 = 10
FECHA_BASE = date(2026, 1, 1)
SHEET_FACUNDO = "F. Economía"
SHEET_IVAN = "I. Física"
SHEET_MARCAS = "marcas"

RANGO_FECHA_MAIL = f"'{SHEET_MARCAS}'!Z1"
RANGO_LOCK_IVAN = f"'{SHEET_MARCAS}'!Z2"
RANGO_LOCK_FACUNDO = f"'{SHEET_MARCAS}'!Z3"
RANGO_FECHA_MAIL_VAGO = f"'{SHEET_MARCAS}'!Z12" 

def get_day_config(target_date=None):
    if target_date is None:
        target_date = _argentina_now_global().date()
    delta = (target_date - FECHA_BASE).days
    time_row = FILA_BASE + delta
    time_row2 = FILA_BASE2 + delta
    users_dict = {
        "Facundo": {
            "Trabajo": {"time": f"'{SHEET_FACUNDO}'!B{time_row2}", "est": f"'{SHEET_MARCAS}'!Z10"},
            "Cursado": {"time": f"'{SHEET_FACUNDO}'!C{time_row2}", "est": f"'{SHEET_MARCAS}'!Z14"},
            "Estadística I": {"time": f"'{SHEET_FACUNDO}'!D{time_row2}", "est": f"'{SHEET_MARCAS}'!Z4"},
            "Int. Contabilidad": {"time": f"'{SHEET_FACUNDO}'!E{time_row2}", "est": f"'{SHEET_MARCAS}'!Z5"},
            "Sociología": {"time": f"'{SHEET_FACUNDO}'!F{time_row2}", "est": f"'{SHEET_MARCAS}'!Z6"},
            "Derecho Público": {"time": f"'{SHEET_FACUNDO}'!G{time_row2}", "est": f"'{SHEET_MARCAS}'!Z7"},
            "Social": {"time": f"'{SHEET_FACUNDO}'!Q{time_row2}", "est": f"'{SHEET_MARCAS}'!Z15", "excluir": True},
        },
        "Iván": {
            "Física": {"time": f"'{SHEET_IVAN}'!B{time_row}", "est": f"'{SHEET_MARCAS}'!Z8"},
            "Análisis": {"time": f"'{SHEET_IVAN}'!C{time_row}", "est": f"'{SHEET_MARCAS}'!Z9"},
            "Álgebra": {"time": f"'{SHEET_IVAN}'!D{time_row}", "est": f"'{SHEET_MARCAS}'!Z13"},
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

@st.cache_data()
def cargar_datos_unificados(fecha_str):
    cfg = get_day_config() 
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
                except: pass
    resumen = {
        "Facundo": {"per_min": parse_float_or_zero(get_val(mapa_indices["rates"]["Facundo"])), "obj": parse_float_or_zero(get_val(mapa_indices["objs"]["Facundo"]))},
        "Iván": {"per_min": parse_float_or_zero(get_val(mapa_indices["rates"]["Iván"])), "obj": parse_float_or_zero(get_val(mapa_indices["objs"]["Iván"]))}
    }
    balance_val = parse_float_or_zero(get_val(mapa_indices["week"], "0"))
    balance_val_ayer = parse_float_or_zero(get_val(mapa_indices["week_ayer"], "0"))
    checks_data = {
        "Iván": get_val(mapa_indices["checks"]["Iván"], ""),
        "Facundo": get_val(mapa_indices["checks"]["Facundo"], "")
    }
    if "usuario_seleccionado" in st.session_state:
        st.session_state["materia_activa"] = materia_en_curso
        st.session_state["inicio_dt"] = inicio_dt
    return {
        "users_data": data_usuarios, "resumen": resumen, "balance": balance_val,
        "balance_ayer": balance_val_ayer, "last_mail_date": get_val(mapa_indices["mail_date"], ""),
        "last_mail_vago": get_val(mapa_indices["mail_vago"], ""), "checks": checks_data,
        "pozo_ivan": parse_float_or_zero(get_val(mapa_indices["pozo_ivan"])),
        "pozo_facu": parse_float_or_zero(get_val(mapa_indices["pozo_facu"]))
    }

def batch_write(updates):
    try:
        sheets_batch_update(st.secrets["sheet_id"], updates)
        cargar_datos_unificados.clear()
    except Exception as e:
        st.error(f"Error escribiendo Google Sheets: {e}")
        st.stop()

# --- CALLBACKS ---
def start_materia_callback(usuario, materia):
    try:
        cfg = get_day_config() 
        info = cfg["USERS"][usuario][materia]
        now_str = ahora_str()
        updates = [(info["est"], now_str)] + [(m_datos["est"], "") for m_datos in cfg["USERS"][usuario].values() if m_datos is not info]
        batch_write(updates)
        st.session_state["materia_activa"] = materia
        st.session_state["inicio_dt"] = parse_datetime(now_str)
    except Exception as e: st.error(f"start_materia error: {e}")
    finally: pedir_rerun()

def stop_materia_callback(usuario, materia):
    try:
        cfg = get_day_config(); info = cfg["USERS"][usuario][materia]
        inicio = st.session_state.get("inicio_dt")
        if inicio is None or st.session_state.get("materia_activa") != materia:
            res = sheets_batch_get(st.secrets["sheet_id"], [info["est"]])
            prev_est = res.get("valueRanges", [{}])[0].get("values", [[""]])[0][0]
            if not prev_est: return
            inicio = parse_datetime(prev_est)
        fin = _argentina_now_global()
        if fin <= inicio:
            batch_write([(info["est"], "")]); pedir_rerun(); return
        midnight = datetime.combine(inicio.date() + timedelta(days=1), dt_time(0,0)).replace(tzinfo=inicio.tzinfo)
        partes = [(inicio, fin)] if inicio.date() == fin.date() else [(inicio, midnight), (midnight, fin)]
        updates = []
        for (p_inicio, p_fin) in partes:
            segs = int((p_fin - p_inicio).total_seconds())
            target_row = (FILA_BASE2 if usuario == "Facundo" else FILA_BASE) + (p_inicio.date() - FECHA_BASE).days
            time_cell = replace_row_in_range(info["time"], target_row)
            try:
                res2 = sheets_batch_get(st.secrets["sheet_id"], [time_cell])
                prev_raw = res2.get("valueRanges", [{}])[0].get("values", [[""]])[0][0]
            except: prev_raw = ""
            new_secs = parse_time_cell_to_seconds(prev_raw) + segs
            updates.append((time_cell, segundos_a_hms(new_secs)))
        updates.append((info["est"], ""))
        batch_write(updates)
        st.session_state["materia_activa"] = None
        st.session_state["inicio_dt"] = None
    except Exception as e: st.error(f"stop_materia error: {e}")
    finally: pedir_rerun()

def main():
    cargar_estilos()
    if st.session_state.get("_do_rerun", False):
        st.session_state["_do_rerun"] = False
        st.rerun()
    if "usuario_seleccionado" not in st.session_state:
        st.error("Inicia sesión en la página principal."); st.stop()
        
    hoy_str = _argentina_now_global().strftime("%Y-%m-%d")
    datos_globales = cargar_datos_unificados(hoy_str) 
    USUARIO_ACTUAL = st.session_state["usuario_seleccionado"]
    OTRO_USUARIO = "Iván" if USUARIO_ACTUAL == "Facundo" else "Facundo"

    materia_en_curso = st.session_state.get("materia_activa")
    inicio_dt = st.session_state.get("inicio_dt")
    tiempo_anadido_seg = int((_argentina_now_global() - inicio_dt).total_seconds()) if materia_en_curso and inicio_dt else 0

    def calcular_metricas(usuario, tiempo_activo_seg=0):
        per_min = datos_globales["resumen"][usuario]["per_min"]
        obj = datos_globales["resumen"][usuario]["obj"]
        total_min = 0.0
        for m, info in get_day_config()["USERS"][usuario].items():
            if info.get("excluir"): continue
            base_seg = hms_a_segundos(datos_globales["users_data"][usuario]["tiempos"][m])
            if materia_en_curso == m and usuario == USUARIO_ACTUAL: base_seg += tiempo_activo_seg
            total_min += base_seg / 60
        return total_min * per_min, per_min, obj, total_min

    m_tot, m_rate, m_obj, total_min = calcular_metricas(USUARIO_ACTUAL, tiempo_anadido_seg)
    progreso_pct = min(m_tot / max(1, m_rate * m_obj), 1.0) * 100
    color_bar = "#00e676" if progreso_pct >= 90 else "#ffeb3b" if progreso_pct >= 50 else "#ff1744"

    # --- Header Metrics ---
    with st.container():
        st.markdown(f"""
            <div style="background-color: #1e1e1e; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div style="font-size: 1.2rem; color: #aaa;">Hoy</div>
                </div>
                <div style="width: 100%; font-size: 2.2rem; font-weight: bold; color: #fff; line-height: 1;">{segundos_a_hms(int(total_min * 60))} | ${m_tot:.2f}</div>
                <div style="width:100%; background-color:#333; border-radius:10px; height:12px; margin: 15px 0;">
                    <div style="width:{progreso_pct}%; background-color:{color_bar}; height:100%; border-radius:10px;"></div>
                </div>
            </div>
        """, unsafe_allow_html=True)

        # Texto "No pensar, actuar" (si no está vacío)
        md_key = "facundo_md" if USUARIO_ACTUAL == "Facundo" else "ivan_md"
        md_content = st.secrets.get(md_key, "").strip()
        if md_content:
            with st.expander("ℹ️ No pensar, actuar."):
                st.markdown(md_content)
        
        # BOTÓN ACTUALIZAR (Fino y debajo del expander)
        st.markdown('<div class="fino-button">', unsafe_allow_html=True)
        if st.button("🔄 Actualizar"):
            cargar_datos_unificados.clear()
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    # --- Materias ---
    for materia, info in get_day_config()["USERS"][USUARIO_ACTUAL].items():
        base_seg = hms_a_segundos(datos_globales["users_data"][USUARIO_ACTUAL]["tiempos"][materia])
        if materia_en_curso == materia: base_seg += tiempo_anadido_seg
        
        badge = '<div class="status-badge status-active">🟢 Estudiando...</div>' if materia_en_curso == materia else ''
        st.markdown(f'<div class="materia-card"><div class="materia-title">{materia}</div>{badge}<div class="materia-time">{segundos_a_hms(base_seg)}</div></div>', unsafe_allow_html=True)

        cols = st.columns([1,1,1])
        with cols[0]:
            if materia_en_curso == materia:
                st.button(f"⛔ DETENER", key=f"stop_{materia}", on_click=stop_materia_callback, args=(USUARIO_ACTUAL, materia))
            elif not materia_en_curso:
                st.button(f"▶ INICIAR", key=f"start_{materia}", on_click=start_materia_callback, args=(USUARIO_ACTUAL, materia))
            else:
                st.button("...", disabled=True, key=f"dis_{materia}")
        
        with cols[1]:
            with st.expander("🛠️ Corregir"):
                new_val = st.text_input("HH:MM:SS", value=datos_globales["users_data"][USUARIO_ACTUAL]["tiempos"][materia], key=f"in_{materia}")
                st.markdown('<div class="fino-button">', unsafe_allow_html=True)
                if st.button("Guardar", key=f"save_{materia}"):
                    if materia_en_curso: st.error("No podés corregir estudiando.")
                    else:
                        batch_write([(info["time"], new_val)])
                        st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
