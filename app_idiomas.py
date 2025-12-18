import re
import json
import time
import requests
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
        .materia-extra { font-size: 0.9rem; color: #aab0c6; font-weight: normal; margin-left: 10px; }
        
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
        parts = list(map(int, hms.split(":")))
        if len(parts) == 3:
            h, m, s = parts
            return h*3600 + m*60 + s
        elif len(parts) == 2:
            m, s = parts
            return m*60 + s
        return 0
    except:
        return 0

def segundos_a_hms(seg):
    h = seg // 3600
    m = (seg % 3600) // 60
    s = seg % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

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

# ------------------ GOOGLE SHEETS SESSION ------------------
@st.cache_resource
def get_sheets_session():
    try:
        key_dict = json.loads(st.secrets["service_account"])
        creds = service_account.Credentials.from_service_account_info(
            key_dict,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        return AuthorizedSession(creds)
    except Exception as e:
        st.error(f"Error configurando Google Sheets: {e}")
        st.stop()

session = get_sheets_session()

def sheets_batch_get(spreadsheet_id, ranges):
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values:batchGet"
    params = [("ranges", r) for r in list(dict.fromkeys(ranges))]
    params.append(("valueRenderOption", "FORMATTED_VALUE"))
    try:
        resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        result_map = {r: res for r, res in zip(list(dict.fromkeys(ranges)), data.get("valueRanges", []))}
        return {"valueRanges": [result_map.get(r, {}) for r in ranges]}
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

# ------------------ ANKI HELPERS ------------------
@st.cache_data(ttl=300) 
def fetch_anki_stats(USUARIO_ACTUAL):
    try:
        DRIVE_JSON_ID = st.secrets["ID_DEL_JSON_FACUNDO"] if USUARIO_ACTUAL == "Facundo" else st.secrets["ID_DEL_JSON_IVAN"]
        URL = f"https://drive.google.com/uc?id={DRIVE_JSON_ID}"
        response = requests.get(URL)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None

# ------------------ CONSTANTES Y ESTRUCTURAS ------------------
FILA_BASE = 170
FECHA_BASE = date(2025, 12, 2)
SHEET_FACUNDO = "F. Idiomas"
SHEET_IVAN = "I. Idiomas"
SHEET_MARCAS = "marcas"

def get_time_row():
    hoy = _argentina_now_global().date()
    delta = (hoy - FECHA_BASE).days
    return FILA_BASE + delta

TIME_ROW = get_time_row()
MARCAS_ROW = 3

USERS = {
    "Facundo": {
        "🇩🇪 Deutsch": {
            "time": f"'{SHEET_FACUNDO}'!B{TIME_ROW}", 
            "est": f"'{SHEET_MARCAS}'!B{MARCAS_ROW}",
            "extra": f"'{SHEET_FACUNDO}'!E{TIME_ROW}" # Información extra al lado de Deutsch
        },
        "🇨🇳 普通话": {
            "time": f"'{SHEET_FACUNDO}'!C{TIME_ROW}", 
            "est": f"'{SHEET_MARCAS}'!C{MARCAS_ROW}",
            "extra": f"'{SHEET_FACUNDO}'!F{TIME_ROW}" # Información extra al lado de Chino
        },
        "🇬🇧 English": {
            "time": f"'{SHEET_FACUNDO}'!D{TIME_ROW}", 
            "est": f"'{SHEET_MARCAS}'!D{MARCAS_ROW}"
        },
    },
    "Iván": {
        "🇬🇧 English":    {"time": f"'{SHEET_IVAN}'!B{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!F{MARCAS_ROW}"},
        "🇩🇪 Deutsch": {"time": f"'{SHEET_IVAN}'!C{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!G{MARCAS_ROW}"},
        "🇧🇷 Português": {"time": f"'{SHEET_IVAN}'!D{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!H{MARCAS_ROW}"},
    }
}

# ------------------ CARGA UNIFICADA ------------------
@st.cache_data()
def cargar_datos_unificados():
    all_ranges = []
    mapa_indices = {"materias": {}}
    idx = 0
    for user, materias in USERS.items():
        for m, info in materias.items():
            all_ranges.append(info["est"]); mapa_indices[(user, m, "est")] = idx; idx += 1
            all_ranges.append(info["time"]); mapa_indices[(user, m, "time")] = idx; idx += 1
            if "extra" in info:
                all_ranges.append(info["extra"]); mapa_indices[(user, m, "extra")] = idx; idx += 1

    try:
        res = sheets_batch_get(st.secrets["sheet_id"], all_ranges)
    except Exception as e:
        st.error(f"Error API Google Sheets: {e}")
        st.stop()

    values = res.get("valueRanges", [])
    def get_val(i, default=""):
        if i >= len(values): return default
        rows = values[i].get("values", [])
        return rows[0][0] if rows and rows[0] else default

    data_usuarios = {u: {"estado": {}, "tiempos": {}, "extra": {}} for u in USERS}
    materia_en_curso = None
    inicio_dt = None

    for user, materias in USERS.items():
        for m in materias:
            data_usuarios[user]["estado"][m] = get_val(mapa_indices[(user, m, "est")])
            raw_time = get_val(mapa_indices[(user, m, "time")])
            data_usuarios[user]["tiempos"][m] = segundos_a_hms(parse_time_cell_to_seconds(raw_time))
            
            if (user, m, "extra") in mapa_indices:
                data_usuarios[user]["extra"][m] = get_val(mapa_indices[(user, m, "extra")])

            if user == st.session_state.get("usuario_seleccionado") and str(data_usuarios[user]["estado"][m]).strip() != "":
                try:
                    inicio_dt = parse_datetime(data_usuarios[user]["estado"][m])
                    materia_en_curso = m
                except: pass

    if "usuario_seleccionado" in st.session_state:
        st.session_state["materia_activa"] = materia_en_curso
        st.session_state["inicio_dt"] = inicio_dt

    return {"users_data": data_usuarios}

def batch_write(updates):
    try:
        sheets_batch_update(st.secrets["sheet_id"], updates)
        cargar_datos_unificados.clear()
    except Exception as e:
        st.error(f"Error escribiendo Google Sheets: {e}")

def start_materia_callback(usuario, materia):
    try:
        info = USERS[usuario][materia]
        now_str = ahora_str()
        updates = [(info["est"], now_str)] + [
            (m_datos["est"], "") for m_datos in USERS[usuario].values() if m_datos is not info
        ]
        batch_write(updates)
        st.session_state["materia_activa"] = materia
        st.session_state["inicio_dt"] = parse_datetime(now_str)
    except Exception as e: st.error(f"Error al iniciar: {e}")
    finally: pedir_rerun()

def stop_materia_callback(usuario, materia):
    try:
        info = USERS[usuario][materia]
        inicio = st.session_state.get("inicio_dt")
        if not inicio:
            res = sheets_batch_get(st.secrets["sheet_id"], [info["est"]])
            prev_est = res["valueRanges"][0].get("values", [[""]])[0][0]
            if not prev_est: return
            inicio = parse_datetime(prev_est)

        fin = _argentina_now_global()
        segs = int((fin - inicio).total_seconds())
        if segs < 0: segs = 0

        # Obtener tiempo actual de la celda
        res_time = sheets_batch_get(st.secrets["sheet_id"], [info["time"]])
        prev_raw = res_time["valueRanges"][0].get("values", [[""]])[0][0]
        new_secs = parse_time_cell_to_seconds(prev_raw) + segs
        
        batch_write([(info["time"], segundos_a_hms(new_secs)), (info["est"], "")])
        st.session_state["materia_activa"] = None
        st.session_state["inicio_dt"] = None
    except Exception as e: st.error(f"Error al detener: {e}")
    finally: pedir_rerun()

def main():
    cargar_estilos()
    if st.session_state.get("_do_rerun", False):
        st.session_state["_do_rerun"] = False
        st.rerun()

    if "usuario_seleccionado" not in st.session_state:
        st.markdown("<h1 style='text-align: center;'>¿Quién sos?</h1>", unsafe_allow_html=True)
        if st.button("👤 Facundo", use_container_width=True):
            st.session_state["usuario_seleccionado"] = "Facundo"
            st.rerun()
        if st.button("👤 Iván", use_container_width=True):
            st.session_state["usuario_seleccionado"] = "Iván"
            st.rerun()
        st.stop()

    USUARIO_ACTUAL = st.session_state["usuario_seleccionado"]
    datos = cargar_datos_unificados()["users_data"]
    
    materia_en_curso = st.session_state.get("materia_activa")
    inicio_dt = st.session_state.get("inicio_dt")
    usuario_estudiando = materia_en_curso is not None

    # ANKI SECTION
    anki_data = fetch_anki_stats(USUARIO_ACTUAL)
    if anki_data:
        with st.expander("📊 Estadísticas Anki"):
            for deck, stats in anki_data.items():
                if not isinstance(stats, dict): continue
                total = stats.get("total", 0)
                if total == 0: continue
                mat = stats.get("mature", 0)
                yng = stats.get("young", 0)
                oth = max(0, total - mat - yng)
                p_mat, p_yng = (mat/total)*100, (yng/total)*100
                st.markdown(f"**{deck}** <small>({total} cartas)</small>", unsafe_allow_html=True)
                st.markdown(f"""
                    <div style="width: 100%; height: 12px; border-radius: 6px; overflow: hidden; display: flex; background: #444; margin-bottom: 10px;">
                        <div style="background: #31A354; width: {p_mat}%;"></div>
                        <div style="background: #74C476; width: {p_yng}%;"></div>
                    </div>
                """, unsafe_allow_html=True)

    # MATERIAS SECTION
    for materia, info in USERS[USUARIO_ACTUAL].items():
        base_seg = hms_a_segundos(datos[USUARIO_ACTUAL]["tiempos"][materia])
        en_curso = (materia_en_curso == materia)
        
        if en_curso and inicio_dt:
            base_seg += int((_argentina_now_global() - inicio_dt).total_seconds())

        # Info extra (Columnas E y F de Facundo)
        extra_info = datos[USUARIO_ACTUAL]["extra"].get(materia, "")
        extra_html = f'<span class="materia-extra">{extra_info}</span>' if extra_info else ""
        
        badge_html = f'<div class="status-badge status-active">🟢 Estudiando...</div>' if en_curso else ''
        
        st.markdown(f"""
            <div class="materia-card">
                <div class="materia-title">{materia}{extra_html}</div>
                {badge_html}
                <div class="materia-time">{segundos_a_hms(base_seg)}</div>
            </div>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns([1, 1])
        with col1:
            if en_curso:
                st.button(f"⛔ DETENER", key=f"stop_{materia}", on_click=stop_materia_callback, args=(USUARIO_ACTUAL, materia), use_container_width=True)
            elif not usuario_estudiando:
                st.button(f"▶ INICIAR", key=f"start_{materia}", on_click=start_materia_callback, args=(USUARIO_ACTUAL, materia), use_container_width=True)
        
        with col2:
            with st.expander("🛠️"):
                new_t = st.text_input("HH:MM:SS", value=datos[USUARIO_ACTUAL]["tiempos"][materia], key=f"in_{materia}")
                if st.button("Guardar", key=f"save_{materia}"):
                    if not usuario_estudiando:
                        batch_write([(info["time"], new_t)])
                        pedir_rerun()
                    else: st.error("No podés editar mientras estudias")

    if usuario_estudiando:
        time.sleep(10)
        st.rerun()

if __name__ == "__main__":
    main()