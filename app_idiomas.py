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

        .materia-card {
            background-color: #262730;
            border: 1px solid #464b5c;
            padding: 20px;
            border-radius: 15px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }
        .materia-title { font-size: 1.4rem; font-weight: bold; color: #ffffff; margin-bottom: 5px; }
        .indicacion-estudio { 
            font-size: 0.9rem; 
            color: #ffaa00; 
            font-style: italic; 
            margin-left: 10px;
            font-weight: normal;
        }
        
        .timer-display {
            font-family: 'Courier New', Courier, monospace;
            font-size: 3.5rem;
            font-weight: bold;
            color: #00ff00;
            text-align: center;
            margin: 10px 0;
            text-shadow: 0 0 10px rgba(0,255,0,0.5);
        }
        </style>
    """, unsafe_allow_html=True)

# ------------------ CONFIGURACIÓN DE GOOGLE SHEETS ------------------
try:
    creds_dict = json.loads(st.secrets["service_account"])
except Exception:
    creds_dict = st.secrets["service_account"]

creds = service_account.Credentials.from_service_account_info(
    creds_dict, 
    scopes=['https://www.googleapis.com/auth/spreadsheets']
)
session = AuthorizedSession(creds)

SPREADSHEET_ID = st.secrets["sheet_id"]
RANGE_NAME = 'F. Idiomas!A2:F100' # Extendemos el rango hasta la columna F

USUARIOS_DISPONIBLES = ["Facundo", "Iván"]
USUARIO_ACTUAL = st.session_state.get("usuario_seleccionado", "Facundo")

# Mapeo de columnas para cada usuario
# "time" es donde se lee/escribe el tiempo acumulado
# "indicacion" es la columna donde está lo que hay que estudiar hoy
USERS = {
    "Facundo": {
        "Alemán": {"time": "F. Idiomas!B", "indicacion_col": 4}, # Columna E (index 4)
        "Chino":  {"time": "F. Idiomas!C", "indicacion_col": 5}  # Columna F (index 5)
    },
    "Iván": {
        # Iván usa las mismas columnas de indicación por ahora, 
        # pero podrías ajustarlo si tuviera columnas distintas
        "Alemán": {"time": "F. Idiomas!D", "indicacion_col": 4},
        "Chino":  {"time": "F. Idiomas!E", "indicacion_col": 5}
    }
}

# ------------------ FUNCIONES DE AYUDA ------------------
def hms_a_segundos(hms_str):
    if not hms_str or hms_str == "0": return 0
    partes = list(map(int, hms_str.split(':')))
    if len(partes) == 3:
        return partes[0]*3600 + partes[1]*60 + partes[2]
    elif len(partes) == 2:
        return partes[0]*60 + partes[1]
    return partes[0]

def segundos_a_hms(segs):
    h = segs // 3600
    m = (segs % 3600) // 60
    s = segs % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def get_argentina_time():
    if _HAS_ZONEINFO:
        return datetime.now(ZoneInfo("America/Argentina/Cordoba"))
    elif pytz:
        return datetime.now(pytz.timezone("America/Argentina/Cordoba"))
    return datetime.now()

def get_time_row():
    base_date = date(2024, 12, 30)
    today = get_argentina_time().date()
    delta = (today - base_date).days
    return delta + 2

def replace_row_in_range(range_str, row_num):
    return re.sub(r'\d+', str(row_num), range_str)

def read_sheet():
    url = f'https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}/values/{RANGE_NAME}'
    try:
        resp = session.get(url)
        resp.raise_for_status()
        return resp.json().get('values', [])
    except Exception as e:
        st.error(f"Error al leer Sheets: {e}")
        return []

def batch_write(values_list):
    url = f'https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}/values:batchUpdate'
    data = {
        "valueInputOption": "USER_ENTERED",
        "data": [{"range": r, "values": [[v]]} for r, v in values_list]
    }
    try:
        resp = session.post(url, json=data)
        resp.raise_for_status()
    except Exception as e:
        st.error(f"Error al escribir en Sheets: {e}")

def sanitize_key(name):
    return name.lower().replace(" ", "_").replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u")

def pedir_rerun():
    time.sleep(1)
    st.rerun()

# ------------------ MAIN APP ------------------
def main():
    cargar_estilos()
    st.title("⏳ Control de Idiomas")

    if "usuario_seleccionado" not in st.session_state:
        st.warning("Por favor, selecciona un usuario en el inicio.")
        st.stop()

    # Cargar datos una sola vez por ciclo
    rows = read_sheet()
    target_row = get_time_row()
    row_idx = target_row - 2
    
    current_row_data = rows[row_idx] if row_idx < len(rows) else []

    # Inicializar estado de estudios
    if "estudios_idiomas" not in st.session_state:
        st.session_state.estudios_idiomas = {}

    materias = ["Alemán", "Chino"]
    
    for materia in materias:
        m_key = sanitize_key(materia)
        if m_key not in st.session_state.estudios_idiomas:
            st.session_state.estudios_idiomas[m_key] = {"inicio": None, "acumulado_previo": 0}

        # Obtener tiempo actual de la celda
        materia_config = USERS[USUARIO_ACTUAL][materia]
        time_col_letter = materia_config["time"].split('!')[1][0]
        # Mapeo letra -> indice (A=0, B=1, C=2, D=3, E=4, F=5)
        col_map = {'A':0, 'B':1, 'C':2, 'D':3, 'E':4, 'F':5}
        val_idx = col_map.get(time_col_letter, 1)
        
        celda_valor = current_row_data[val_idx] if val_idx < len(current_row_data) else "00:00:00"
        segundos_total = hms_a_segundos(celda_valor)

        # Obtener indicación de estudio (Columnas E o F)
        ind_idx = materia_config["indicacion_col"]
        indicacion_texto = current_row_data[ind_idx] if ind_idx < len(current_row_data) else ""

        # UI Tarjeta
        with st.container():
            st.markdown(f"""
                <div class="materia-card">
                    <div class="materia-title">
                        {materia}
                        <span class="indicacion-estudio">{indicacion_texto}</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            estado = st.session_state.estudios_idiomas[m_key]
            en_curso = estado["inicio"] is not None

            col_timer, col_btns = st.columns([2, 1])

            with col_timer:
                if en_curso:
                    transcurrido = int(time.time() - estado["inicio"])
                    display_segs = segundos_total + transcurrido
                else:
                    display_segs = segundos_total
                
                st.markdown(f'<div class="timer-display">{segundos_a_hms(display_segs)}</div>', unsafe_allow_html=True)

            with col_btns:
                if not en_curso:
                    if st.button(f"▶️ Iniciar", key=f"start_{m_key}", use_container_width=True):
                        # Detener otros idiomas primero
                        for k in st.session_state.estudios_idiomas:
                            st.session_state.estudios_idiomas[k]["inicio"] = None
                        
                        st.session_state.estudios_idiomas[m_key]["inicio"] = time.time()
                        st.rerun()
                else:
                    if st.button(f"⏹️ Detener", key=f"stop_{m_key}", use_container_width=True):
                        final_segs = segundos_total + int(time.time() - estado["inicio"])
                        time_cell = replace_row_in_range(materia_config["time"], target_row)
                        batch_write([(time_cell, segundos_a_hms(final_segs))])
                        st.session_state.estudios_idiomas[m_key]["inicio"] = None
                        st.success("¡Tiempo guardado!")
                        pedir_rerun()

            with st.expander("Corregir tiempo manual"):
                val = st.text_input("Formato HH:MM:SS", value=segundos_a_hms(segundos_total), key=f"input_{m_key}")
                if st.button("Guardar Corrección", key=f"corr_{m_key}"):
                    try:
                        new_segs = hms_a_segundos(val)
                        time_cell = replace_row_in_range(materia_config["time"], target_row)
                        batch_write([(time_cell, segundos_a_hms(new_segs))])
                        st.success("Corregido.")
                        pedir_rerun()
                    except:
                        st.error("Formato inválido.")

        st.divider()

    # Refresco automático si hay algo corriendo
    if any(s["inicio"] is not None for s in st.session_state.estudios_idiomas.values()):
        time.sleep(5)
        st.rerun()

if __name__ == "__main__":
    main()