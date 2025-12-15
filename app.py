import re
import json
import time
import requests
import streamlit as st
import gspread
from datetime import datetime, date, timedelta, time as dt_time
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from requests.exceptions import RequestException

# ------------------ CONFIGURACIÓN GLOBAL ------------------
# El título es "Tiempo de Estudio" para mantener la apariencia principal
st.set_page_config(page_title="Tiempo de Estudio", page_icon="⚡", layout="centered")

# ------------------ ESTILOS CSS (GLOBAL) ------------------
st.markdown("""
    <style>
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

# ------------------ TIMEZONE HELPERS COMPARTIDOS ------------------
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
    tz_name = 'America/Argentina/Cordoba'
    if ZoneInfo is not None:
        return datetime.now(ZoneInfo(tz_name))
    if 'pytz' in globals() and pytz is not None:
        return datetime.now(pytz.timezone(tz_name))
    return datetime.now()

def ahora_str():
    dt = _argentina_now_global()
    try:
        return dt.isoformat(sep=" ", timespec="seconds")
    except:
        return dt.strftime("%Y-%m-%d %H:%M:%S")

# ==============================================================================
#                               MODULO: ESTUDIO (Principal)
# ==============================================================================

def run_estudio_app():
    # --- HELPER FUNCTIONS ---
    def parse_datetime(s):
        if not s or str(s).strip() == "":
            raise ValueError("Marca vacía")
        s = str(s).strip()
        TZ = _argentina_now_global().tzinfo
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None: return dt.replace(tzinfo=TZ)
            return dt.astimezone(TZ)
        except:
            pass
        fmts = ["%Y-%m-%d %H:%M:%S%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"]
        for fmt in fmts:
            try:
                dt = datetime.strptime(s, fmt)
                if dt.tzinfo is None: return dt.replace(tzinfo=TZ)
                return dt.astimezone(TZ)
            except: continue
        raise ValueError(f"Formato inválido: {s}")

    def hms_a_segundos(hms):
        if not hms: return 0
        try:
            h, m, s = map(int, hms.split(":"))
            return h*3600 + m*60 + s
        except: return 0

    def segundos_a_hms(seg):
        h = seg // 3600; m = (seg % 3600) // 60; s = seg % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

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
            if 0 <= f <= 1: return int(f * 86400)
            return int(f)
        except: return 0

    def replace_row_in_range(range_str, new_row):
        if not isinstance(range_str, str): return range_str
        return re.sub(r'(\d+)(\s*$)', str(new_row), range_str)

    def sanitize_key(s): return re.sub(r'[^a-zA-Z0-9_]', '_', s)
    def pedir_rerun(): st.session_state["_do_rerun"] = True

    # --- SESSION & API ---
    @st.cache_resource
    def get_sheets_session():
        try:
            key_dict = json.loads(st.secrets["textkey"])
            creds = service_account.Credentials.from_service_account_info(
                key_dict, scopes=["https://www.googleapis.com/auth/spreadsheets"]
            )
            return AuthorizedSession(creds)
        except Exception as e:
            st.error(f"Error auth: {e}")
            st.stop()

    session = get_sheets_session()

    def sheets_batch_get(spreadsheet_id, ranges):
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values:batchGet"
        unique_ranges = list(dict.fromkeys(ranges))
        params = [("ranges", r) for r in unique_ranges]
        params.append(("valueRenderOption", "FORMATTED_VALUE"))
        try:
            resp = session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            ordered_results = data.get("valueRanges", [])
            result_map = {r: res for r, res in zip(unique_ranges, ordered_results)}
            return {"valueRanges": [result_map.get(r, {}) for r in ranges]}
        except RequestException as e:
            raise RuntimeError(f"Error HTTP batchGet: {e}")

    def sheets_batch_update(spreadsheet_id, updates):
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values:batchUpdate"
        data = {"valueInputOption": "USER_ENTERED", "data": [{"range": r, "values": [[v]]} for r, v in updates]}
        try:
            resp = session.post(url, json=data, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except RequestException as e:
            raise RuntimeError(f"Error HTTP batchUpdate: {e}")

    # --- ANKI ---
    @st.cache_data(ttl=300)
    def fetch_anki_stats(USUARIO_ACTUAL):
        try:
            DRIVE_JSON_ID = st.secrets["ID_DEL_JSON_FACUNDO"] if USUARIO_ACTUAL == "Facundo" else st.secrets["ID_DEL_JSON_IVAN"]
            URL = f"https://drive.google.com/uc?id={DRIVE_JSON_ID}"
            response = requests.get(URL)
            response.raise_for_status()
            return response.json()
        except Exception: return None

    # --- DATOS HOJA ---
    FILA_BASE = 170
    FECHA_BASE = date(2025, 12, 2)
    SHEET_FACUNDO = "F. Economía"
    SHEET_IVAN = "I. Física"
    SHEET_MARCAS = "marcas"

    def get_time_row():
        hoy = _argentina_now_global().date()
        return FILA_BASE + (hoy - FECHA_BASE).days

    TIME_ROW = get_time_row()
    MARCAS_ROW = 2
    
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
    WEEK_RANGE = f"'{SHEET_MARCAS}'!R{TIME_ROW}"

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

        try: res = sheets_batch_get(st.secrets["sheet_id"], all_ranges)
        except Exception as e: st.error(f"Error API: {e}"); st.stop()

        values = res.get("valueRanges", [])
        def get_val(i, default=""):
            if i >= len(values): return default
            vr = values[i]; rows = vr.get("values", [])
            return rows[0][0] if rows and rows[0] else default

        data_usuarios = {u: {"estado": {}, "tiempos": {}, "inicio_dt": None, "materia_activa": None} for u in USERS}
        materia_en_curso = None; inicio_dt = None

        for user, materias in USERS.items():
            for m in materias:
                idx_est = mapa_indices["materias"][(user, m, "est")]
                raw_est = get_val(idx_est)
                data_usuarios[user]["estado"][m] = raw_est
                idx_time = mapa_indices["materias"][(user, m, "time")]
                secs = parse_time_cell_to_seconds(get_val(idx_time))
                data_usuarios[user]["tiempos"][m] = segundos_a_hms(secs)
                if user == st.session_state.get("usuario_seleccionado") and str(raw_est).strip() != "":
                    try: inicio_dt = parse_datetime(raw_est); materia_en_curso = m
                    except: pass

        resumen = {
            "Facundo": {"per_min": parse_float_or_zero(get_val(mapa_indices["rates"]["Facundo"])), "obj": parse_float_or_zero(get_val(mapa_indices["objs"]["Facundo"]))},
            "Iván": {"per_min": parse_float_or_zero(get_val(mapa_indices["rates"]["Iván"])), "obj": parse_float_or_zero(get_val(mapa_indices["objs"]["Iván"]))}
        }
        balance_val = parse_float_or_zero(get_val(mapa_indices["week"], "0"))

        if "usuario_seleccionado" in st.session_state:
            st.session_state["materia_activa"] = materia_en_curso
            st.session_state["inicio_dt"] = inicio_dt
        return {"users_data": data_usuarios, "resumen": resumen, "balance": balance_val}

    def batch_write(updates):
        try: sheets_batch_update(st.secrets["sheet_id"], updates); cargar_datos_unificados.clear()
        except Exception as e: st.error(f"Error escribiendo: {e}"); st.stop()

    def start_materia_callback(usuario, materia):
        try:
            info = USERS[usuario][materia]
            now_str = ahora_str()
            updates = [(info["est"], now_str)] + [(USERS[usuario][m]["est"], "") for m in USERS[usuario] if m != materia]
            batch_write(updates)
            st.session_state["materia_activa"] = materia
            st.session_state["inicio_dt"] = parse_datetime(now_str)
        except Exception as e: st.error(f"Error start: {e}")
        finally: pedir_rerun()

    def stop_materia_callback(usuario, materia):
        try:
            info = USERS[usuario][materia]
            inicio = st.session_state.get("inicio_dt")
            if inicio is None: # Fallback lectura hoja
                res = sheets_batch_get(st.secrets["sheet_id"], [info["est"]])
                val = res.get("valueRanges", [{}])[0].get("values", [[""]])[0][0]
                if not val: st.error("No hay marca inicio."); pedir_rerun(); return
                inicio = parse_datetime(val)
            
            fin = _argentina_now_global()
            if fin <= inicio: st.error("Fin < Inicio"); batch_write([(info["est"], "")]); pedir_rerun(); return

            # Calcular tiempos (split midnight)
            midnight = datetime.combine(inicio.date() + timedelta(days=1), dt_time(0,0)).replace(tzinfo=inicio.tzinfo)
            partes = [(inicio, fin)] if inicio.date() == fin.date() else [(inicio, midnight), (midnight, fin)]
            
            updates = []
            for (p_ini, p_fin) in partes:
                segs = int((p_fin - p_ini).total_seconds())
                target_row = FILA_BASE + (p_ini.date() - FECHA_BASE).days
                time_cell = replace_row_in_range(info["time"], target_row)
                # Leer previo
                try: prev = sheets_batch_get(st.secrets["sheet_id"], [time_cell])["valueRanges"][0]["values"][0][0]
                except: prev = ""
                new_secs = parse_time_cell_to_seconds(prev) + segs
                updates.append((time_cell, segundos_a_hms(new_secs)))
            
            updates.append((info["est"], ""))
            batch_write(updates)
            st.session_state["materia_activa"] = None; st.session_state["inicio_dt"] = None
        except Exception as e: st.error(f"Error stop: {e}")
        finally: pedir_rerun()

    # --- UI ESTUDIO ---
    if st.session_state.get("_do_rerun", False):
        st.session_state["_do_rerun"] = False
        st.rerun()

    # Login Usuario (f=Facu, i=Ivan)
    try: params = st.query_params
    except: params = st.experimental_get_query_params()
    
    if "usuario_seleccionado" not in st.session_state:
        if "f" in params: st.session_state["usuario_seleccionado"] = "Facundo"; st.rerun()
        if "i" in params: st.session_state["usuario_seleccionado"] = "Iván"; st.rerun()
        st.markdown("<h1 style='text-align:center;'>¿Quién sos?</h1>", unsafe_allow_html=True)
        if st.button("👤 Facundo", use_container_width=True): st.session_state["usuario_seleccionado"] = "Facundo"; st.rerun()
        st.write("")
        if st.button("👤 Iván", use_container_width=True): st.session_state["usuario_seleccionado"] = "Iván"; st.rerun()
        return

    # Data Loading
    datos_globales = cargar_datos_unificados()
    datos = datos_globales["users_data"]
    resumen_marcas = datos_globales["resumen"]
    USUARIO_ACTUAL = st.session_state["usuario_seleccionado"]
    OTRO_USUARIO = "Iván" if USUARIO_ACTUAL == "Facundo" else "Facundo"

    # Sync Active State
    if st.session_state.get("materia_activa") is None:
        for m, est_raw in datos[USUARIO_ACTUAL]["estado"].items():
            if str(est_raw).strip():
                st.session_state["materia_activa"] = m
                st.session_state["inicio_dt"] = parse_datetime(est_raw)
                break

    materia_en_curso = st.session_state.get("materia_activa")
    usuario_estudiando = materia_en_curso is not None
    materia_otro = next((m for m, v in datos[OTRO_USUARIO]["estado"].items() if str(v).strip()), "")
    
    # Cálculos
    tiempo_anadido = 0
    if usuario_estudiando and st.session_state.get("inicio_dt"):
        tiempo_anadido = int((_argentina_now_global() - st.session_state["inicio_dt"]).total_seconds())

    def calcular_metricas(u, extra_seg=0):
        total_min = 0.0
        for m in USERS[u]:
            seg = hms_a_segundos(datos[u]["tiempos"][m])
            if u == USUARIO_ACTUAL and usuario_estudiando and m == materia_en_curso: seg += extra_seg
            total_min += seg / 60
        dinero = (extra_seg/60) * resumen_marcas[u]["per_min"] if u == USUARIO_ACTUAL else 0
        return total_min * resumen_marcas[u]["per_min"], total_min, dinero

    m_tot, m_mins, m_prog_dinero = calcular_metricas(USUARIO_ACTUAL, tiempo_anadido)
    m_obj_money = resumen_marcas[USUARIO_ACTUAL]["obj"] * resumen_marcas[USUARIO_ACTUAL]["per_min"]
    progreso_pct = min(m_tot / max(1, m_obj_money), 1.0) * 100
    color_bar = "#00e676" if progreso_pct >= 90 else "#ffeb3b" if progreso_pct >= 50 else "#ff1744"
    
    # Balance
    bal = datos_globales["balance"]
    if USUARIO_ACTUAL == "Facundo": bal = -bal
    bal += m_prog_dinero
    bal_str = f"+${bal:.2f}" if bal > 0 else (f"-${abs(bal):.2f}" if bal < 0 else "$0.00")
    bal_col = "#00e676" if bal > 0 else "#ff1744" if bal < 0 else "#aaa"

    # --- RENDER PRINCIPAL ---
    st.markdown(f"""
        <div style="background-color: #1e1e1e; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
            <div style="color: #aaa;">Hoy ({USUARIO_ACTUAL})</div>
            <div style="font-size: 2.2rem; font-weight: bold;">{segundos_a_hms(int(m_mins*60))} | ${m_tot:.2f}</div>
            <div style="width:100%; background:#333; border-radius:10px; height:12px; margin: 15px 0;">
                <div style="width:{progreso_pct}%; background:{color_bar}; height:100%; border-radius:10px; transition: width 0.5s;"></div>
            </div>
            <div style="display:flex; justify-content:space-between; color:#888;">
                <div>Balance: <span style="color:{bal_col};">{bal_str}</span></div>
                <div>${m_obj_money:.2f}</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Otro Usuario
    o_tot, o_mins, _ = calcular_metricas(OTRO_USUARIO)
    o_obj_money = resumen_marcas[OTRO_USUARIO]["obj"] * resumen_marcas[OTRO_USUARIO]["per_min"]
    o_pct = min(o_tot / max(1, o_obj_money), 1.0) * 100
    o_col = "#00e676" if o_pct >= 90 else "#ffeb3b" if o_pct >= 50 else "#ff1744"
    
    with st.expander(f"Progreso de {OTRO_USUARIO}", expanded=True):
         st.markdown(f"""
            <div>
                <div style="display:flex; justify-content:space-between;"><b>{segundos_a_hms(int(o_mins*60))} | ${o_tot:.2f}</b></div>
                <div style="width:100%; background:#444; border-radius:8px; height:8px; margin-top: 8px;">
                    <div style="width:{o_pct}%; background:{o_col}; height:100%; border-radius:8px;"></div>
                </div>
                <div style="font-size:0.8rem; color:#aaa; margin-top:5px; display:flex; justify-content:space-between;">
                    <div>{f'🟢 {materia_otro}' if materia_otro else '⚪ Inactivo'}</div>
                    <div>Meta: ${o_obj_money:.2f}</div>
                </div>
            </div>
        """, unsafe_allow_html=True)

    # Anki & Markdown
    anki = fetch_anki_stats(USUARIO_ACTUAL)
    if anki:
        with st.expander("Anki"):
            st.json(anki, expanded=False) # Simplificado para brevedad, expandir si se desea la visualización completa anterior
    
    with st.expander("ℹ️ No pensar, actuar."):
        st.markdown(st.secrets["md"]["facundo"] if USUARIO_ACTUAL == "Facundo" else st.secrets["md"]["ivan"])

    # Listado Materias
    st.subheader("Materias")
    for materia, info in USERS[USUARIO_ACTUAL].items():
        base_seg = hms_a_segundos(datos[USUARIO_ACTUAL]["tiempos"][materia])
        if usuario_estudiando and materia == materia_en_curso: base_seg += max(0, tiempo_anadido)
        
        badge = '<div class="status-badge status-active">🟢 Estudiando...</div>' if materia == materia_en_curso else ''
        st.markdown(f"""<div class="materia-card"><div class="materia-title">{materia}</div>{badge}<div class="materia-time">{segundos_a_hms(base_seg)}</div></div>""", unsafe_allow_html=True)
        
        c1, c2 = st.columns(2)
        key_s = f"s_{USUARIO_ACTUAL}_{materia}"
        if materia == materia_en_curso:
            c1.button("⛔ DETENER", key=key_s, use_container_width=True, on_click=stop_materia_callback, args=(USUARIO_ACTUAL, materia))
        elif not usuario_estudiando:
            c1.button("▶ INICIAR", key=key_s, use_container_width=True, on_click=start_materia_callback, args=(USUARIO_ACTUAL, materia))
        else:
            c1.button("...", disabled=True, key=key_s, use_container_width=True)
            
        with c2.expander("Corregir"):
            val_c = st.text_input("HH:MM:SS", value=datos[USUARIO_ACTUAL]["tiempos"][materia], key=f"fix_{materia}")
            if st.button("Guardar", key=f"btn_{materia}"):
                if usuario_estudiando: st.error("Stop primero."); pedir_rerun()
                else:
                    target = replace_row_in_range(info["time"], TIME_ROW)
                    batch_write([(target, val_c)])
                    st.success("ok"); pedir_rerun()

    if usuario_estudiando:
        time.sleep(10)
        st.rerun()

# ==============================================================================
#                               MODULO: HÁBITOS (Oculto)
# ==============================================================================

def run_habitos_app():
    # --- CONFIG Y SECRETS ---
    _gcp_secrets = st.secrets.get("gcp", {})
    GOOGLE_SHEET_NAME = _gcp_secrets.get("google_sheet_name", "Tiempo de Estudio")
    WORKSHEET_NAME = _gcp_secrets.get("worksheet_name", "F. Extra")
    BOUNDARY_COLUMN = _gcp_secrets.get("boundary_column", "Extracurricular")

    # --- PASSWORD CHECK (Local para este módulo) ---
    def check_password():
        if "pw_correct" in st.session_state and st.session_state.pw_correct: return True
        st.title("🔒 Acceso Oculto")
        password = st.text_input("Contraseña:", type="password")
        if st.button("Entrar"):
            if password == st.secrets["auth"]["password"]:
                st.session_state.pw_correct = True
                st.rerun()
            else: st.error("Incorrecta.")
        return False

    if not check_password(): return

    # --- HELPERS ---
    def get_argentina_str(fmt): return _argentina_now_global().strftime(fmt)
    
    @st.cache_resource
    def connect_habits():
        try:
            sa = _gcp_secrets.get("service_account")
            if sa:
                creds = json.loads(sa) if isinstance(sa, str) else sa
                gc = gspread.service_account_from_dict(creds)
                return gc.open(GOOGLE_SHEET_NAME).worksheet(WORKSHEET_NAME)
        except Exception as e: st.error(f"Error Sheets: {e}")
        return None

    def load_habits(): return _gcp_secrets.get("habits", [])

    def setup_daily_state(ws):
        today = get_argentina_str('%d/%m')
        if 'active_habits_date' not in st.session_state or st.session_state.active_habits_date != today:
            st.session_state.active_habits_date = today
            pending = []
            if ws:
                try:
                    vals = ws.get_all_values()
                    headers = vals[0]
                    col_fechas = [r[0] for r in vals]
                    try: row_idx = col_fechas.index(today)
                    except: row_idx = -1
                    
                    for h in st.session_state.habits:
                        name = h["name"]
                        done = False
                        if row_idx != -1 and name in headers:
                            col_idx = headers.index(name)
                            if len(vals[row_idx]) > col_idx and vals[row_idx][col_idx].strip(): done = True
                        if not done: pending.append(name)
                    st.session_state.todays_pending_habits = pending
                except: st.session_state.todays_pending_habits = [h["name"] for h in st.session_state.habits]
            else: st.session_state.todays_pending_habits = [h["name"] for h in st.session_state.habits]

    def log_habit(name, ws):
        try:
            if ws:
                today = get_argentina_str('%d/%m')
                time_s = get_argentina_str('%H:%M:%S')
                cell = ws.find(today, in_column=1)
                row = cell.row
                try: col = ws.find(name, in_row=1).col
                except: 
                    # Buscar espacio libre
                    headers = ws.row_values(1)
                    try: b_col = headers.index(BOUNDARY_COLUMN) + 1
                    except: b_col = len(headers) + 1
                    col = b_col # Simplificado: escribe en boundary o final
                    ws.update_cell(1, col, name)
                ws.update_cell(row, col, time_s)
            
            if name in st.session_state.todays_pending_habits:
                st.session_state.todays_pending_habits.remove(name)
            st.session_state.needs_rerun = True
        except Exception as e: st.error(str(e))

    # --- UI ---
    st.title("📅 Hábitos")
    sheet = connect_habits()
    if 'habits' not in st.session_state: st.session_state.habits = load_habits()
    setup_daily_state(sheet)

    pending = st.session_state.get("todays_pending_habits", [])
    grouped = {1: [], 2: [], 3: []}
    for h in st.session_state.habits:
        if h["name"] in pending: grouped[h["group"]].append(h["name"])

    for grp, names in grouped.items():
        if not names: continue
        with st.expander(["Mañana", "Tarde", "Noche"][grp-1], expanded=True):
            cols = st.columns(3)
            for i, habit in enumerate(names):
                cols[i%3].button(habit, key=f"h_{habit}", on_click=log_habit, args=(habit, sheet), use_container_width=True)

    if st.session_state.get("needs_rerun"):
        st.session_state.needs_rerun = False
        st.rerun()
    
    # Botón discreto para volver
    if st.button("Volver al estudio", type="secondary"):
        st.query_params.clear()
        st.rerun()

# ==============================================================================
#                               MAIN DISPATCHER
# ==============================================================================

def main():
    try:
        # Intenta usar la nueva API de Streamlit
        query_params = st.query_params
    except:
        # Fallback para versiones anteriores
        query_params = st.experimental_get_query_params()

    # Verifica si el parámetro oculto existe (ignorando mayúsculas/tildes por seguridad)
    # Permite ?hábitos, ?habitos, ?Habitos, etc.
    keys = [k.lower() for k in query_params.keys()]
    
    if "habitos" in keys or "hábitos" in keys:
        run_habitos_app()
    else:
        run_estudio_app()

if __name__ == "__main__":
    main()
