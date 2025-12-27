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
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        return dt
    except ValueError:
        try:
            dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
            return dt.replace(tzinfo=TZ)
        except:
            return datetime.combine(date.today(), dt_time(0,0)).replace(tzinfo=TZ)

# ------------------ HELPERS DE TIEMPO ------------------
def hms_a_segundos(hms_str):
    if not hms_str or ":" not in str(hms_str): return 0
    partes = hms_str.split(":")
    h = int(partes[0])
    m = int(partes[1])
    s = int(partes[2]) if len(partes)>2 else 0
    return h * 3600 + m * 60 + s

def segundos_a_hms(total_segundos):
    h = total_segundos // 3600
    m = (total_segundos % 3600) // 60
    s = total_segundos % 60
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"

def cargar_estilos_trabajo():
    st.markdown("""
        <style>
        .work-card {
            background-color: #262730;
            border: 1px solid #464b5c;
            padding: 20px;
            border-radius: 15px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
            text-align: center;
        }
        .work-title {
            font-size: 1.6rem;
            font-weight: bold;
            color: #ffffff;
            margin-bottom: 10px;
        }
        .work-time {
            font-size: 2.5rem;
            font-family: 'Courier New', Courier, monospace;
            color: #00ffcc;
            margin: 15px 0;
        }
        .status-badge {
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9rem;
            font-weight: bold;
            margin-bottom: 10px;
        }
        .status-active { background-color: #1e3d37; color: #00ffcc; border: 1px solid #00ffcc; }
        
        .progress-container {
            width: 100%;
            background-color: #1e1e1e;
            border-radius: 10px;
            margin: 10px 0;
            height: 12px;
            overflow: hidden;
        }
        .progress-bar {
            height: 100%;
            background: linear-gradient(90deg, #00ffcc, #0088ff);
            transition: width 0.5s ease-in-out;
        }
        .target-text {
            font-size: 0.85rem;
            color: #888;
            margin-top: 5px;
        }
        </style>
    """, unsafe_allow_html=True)

# ------------------ GOOGLE SHEETS CORE ------------------
def connect_to_google_sheets():
    try:
        # Verificamos si el secreto existe
        if "service_account" not in st.secrets:
            st.error("No se encontró 'gcp_service_account' en st.secrets.")
            return None
            
        info = st.secrets["service_account"]
        
        # Si Streamlit cargó el secreto como string (JSON), lo convertimos a dict
        if isinstance(info, str):
            info = json.loads(info)
        else:
            # Si es un objeto de Streamlit (Dict-like), intentamos convertirlo a dict real
            # Esto evita el error "'str' object has no attribute 'keys'" si el parser falla
            info = dict(info)
            
        creds = service_account.Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        return AuthorizedSession(creds)
    except Exception as e:
        st.error(f"Error de conexión con Google: {e}")
        return None

def batch_read(spreadsheet_id, ranges):
    session = connect_to_google_sheets()
    if not session: return []
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values:batchGet"
    try:
        resp = session.get(url, params={"ranges": ranges})
        resp.raise_for_status()
        value_ranges = resp.json().get("valueRanges", [])
        return [vr.get("values", [["00:00:00"]]) for vr in value_ranges]
    except Exception as e:
        st.error(f"Error leyendo celdas: {e}")
        return [([["00:00:00"]]) for _ in ranges]

def batch_write(spreadsheet_id, updates):
    session = connect_to_google_sheets()
    if not session: return
    data = [{"range": r, "values": [[v]]} for r, v in updates]
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values:batchUpdate"
    try:
        resp = session.post(url, json={"valueInputOption": "USER_ENTERED", "data": data})
        resp.raise_for_status()
    except Exception as e:
        st.error(f"Error escribiendo en la hoja: {e}")

# ------------------ CONFIGURACIÓN UNIFICADA ------------------
def get_config_usuario(username):
    # Intentar obtener el ID de la planilla principal usando el nombre de usuario
    sheet_id = st.secrets.get("sheet_id", "")
    
    return {
        "sheet_id": sheet_id,
        "proyecto": {
            "nombre": "Trabajo",
            "time": "'F. Trabajo'!B2",
            "start": "'F. Trabajo'!B3",
            "target_hours": 8 # Objetivo de tiempo diario
        }
    }

def start_work_callback(usuario):
    cfg = get_config_usuario(usuario)
    target_cell = cfg["proyecto"]["start"]
    batch_write(cfg["sheet_id"], [(target_cell, ahora_str())])
    st.session_state[f"working_status_{usuario}"] = True

def stop_work_callback(usuario):
    cfg = get_config_usuario(usuario)
    p_cfg = cfg["proyecto"]
    
    vals = batch_read(cfg["sheet_id"], [p_cfg["time"], p_cfg["start"]])
    base_hms = vals[0][0][0] if (vals and vals[0]) else "00:00:00"
    start_str = vals[1][0][0] if (vals and len(vals)>1 and vals[1]) else ""
    
    if not start_str or start_str == "---":
        return

    now = _argentina_now_global()
    start_dt = parse_datetime(start_str)
    diff_seg = int((now - start_dt).total_seconds())
    
    nuevo_total = hms_a_segundos(base_hms) + max(0, diff_seg)
    nuevo_hms = segundos_a_hms(nuevo_total)
    
    batch_write(cfg["sheet_id"], [
        (p_cfg["time"], nuevo_hms),
        (p_cfg["start"], "---")
    ])
    st.session_state[f"working_status_{usuario}"] = False

def main():
    cargar_estilos_trabajo()
    
    USUARIO_ACTUAL = st.session_state.get("username", "Facundo")
    cfg = get_config_usuario(USUARIO_ACTUAL)
    
    if not cfg["sheet_id"]:
        st.error(f"No se encontró spreadsheet_id para {USUARIO_ACTUAL} en secrets.")
        return

    st.title(f"💼 Gestión de Trabajo")
    
    p_cfg = cfg["proyecto"]
    
    # Leer datos actuales de la hoja "F. Trabajo"
    raw_data = batch_read(cfg["sheet_id"], [p_cfg["time"], p_cfg["start"]])
    
    base_hms = raw_data[0][0][0] if (raw_data and raw_data[0]) else "00:00:00"
    start_str = raw_data[1][0][0] if (raw_data and len(raw_data)>1 and raw_data[1]) else "---"
    
    en_curso = (start_str != "---")
    total_seg = hms_a_segundos(base_hms)
    
    if en_curso:
        try:
            start_dt = parse_datetime(start_str)
            tiempo_anadido = int((_argentina_now_global() - start_dt).total_seconds())
            total_seg += max(0, tiempo_anadido)
        except:
            pass
            
    total_hms = segundos_a_hms(total_seg)
    
    # Progreso
    target_seconds = p_cfg["target_hours"] * 3600
    progress = min(100, (total_seg / target_seconds) * 100)
    
    # Renderizado UI
    badge_html = f'<div class="status-badge status-active">🟢 TRABAJANDO...</div>' if en_curso else ''
    
    html_card = f"""
        <div class="work-card">
            <div class="work-title">{p_cfg['nombre']}</div>
            {badge_html}
            <div class="work-time">{total_hms}</div>
            <div class="progress-container">
                <div class="progress-bar" style="width: {progress}%"></div>
            </div>
            <div class="target-text">Objetivo: {p_cfg['target_hours']}h ({int(progress)}%)</div>
        </div>
    """
    st.markdown(html_card, unsafe_allow_html=True)
    
    cols = st.columns([1, 2, 1])
    with cols[1]:
        if en_curso:
            st.button("⛔ DETENER", key="stop_work", 
                      on_click=stop_work_callback, args=(USUARIO_ACTUAL,), 
                      use_container_width=True)
        else:
            st.button("▶ INICIAR TRABAJO", key="start_work", 
                      on_click=start_work_callback, args=(USUARIO_ACTUAL,), 
                      use_container_width=True)

    if en_curso:
        time.sleep(10)
        st.rerun()

if __name__ == "__main__":
    main()