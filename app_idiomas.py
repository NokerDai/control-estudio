import re
import json # Necesario para parsear el JSON de credenciales
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

def _get_tzinfo(tz_str="America/Argentina/Buenos_Aires"):
    if _HAS_ZONEINFO:
        return ZoneInfo(tz_str)
    elif pytz:
        return pytz.timezone(tz_str)
    return None

def _argentina_now_global():
    """Retorna el datetime actual en la zona horaria de Buenos Aires."""
    tz = _get_tzinfo()
    if tz:
        return datetime.now(tz)
    return datetime.now()

def ahora_str():
    """Retorna la hora actual en formato de hoja de cálculo."""
    return _argentina_now_global().strftime("%Y-%m-%d %H:%M:%S")

def parse_datetime(dt_str):
    """Parsea un string de fecha/hora de la hoja a un objeto datetime con TZ."""
    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    tz = _get_tzinfo()
    if tz:
        return dt.replace(tzinfo=tz)
    return dt

# ------------------ GOOGLE SHEETS AUTH & HELPERS ------------------
def _get_credentials_dict():
    """Lee la clave 'service_account' como un string y lo parsea como JSON."""
    try:
        raw_credentials_json = st.secrets["service_account"] 
        # Cuidado con el formato que usa Streamlit para cadenas largas en secrets.toml
        # Si Streamlit lo lee como una cadena multilinea simple, json.loads funcionará.
        if isinstance(raw_credentials_json, str):
            # Intentar cargar el JSON
            return json.loads(raw_credentials_json)
        # Si por alguna razón lo lee como diccionario (e.g., si se usó la sintaxis TOML), lo retornamos.
        return dict(raw_credentials_json)
    except json.JSONDecodeError as e:
        st.error(f"Error: La clave 'service_account' en secrets.toml no es un JSON válido. {e}")
        st.stop()
    except KeyError:
        st.error("Error: Falta la clave 'service_account' o 'sheet_id' en secrets.toml.")
        st.stop()
    except Exception as e:
        st.error(f"Error inesperado al procesar credenciales: {e}")
        st.stop()


def sheets_batch_get(spreadsheet_id, ranges):
    """Llama a Sheets API para obtener múltiples rangos."""
    try:
        # 1. Obtiene las credenciales parseando el JSON
        credentials_dict = _get_credentials_dict()
        credentials = service_account.Credentials.from_service_account_info(credentials_dict)
        
        # 2. Crea la sesión autorizada
        authed_session = AuthorizedSession(credentials)
        
        # 3. URL de la API de Google Sheets para batchGet
        base_url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values:batchGet"
        ranges_query = "&ranges=".join(ranges)
        url = f"{base_url}?ranges={ranges_query}&valueRenderOption=UNFORMATTED_VALUE"
        
        # 4. Hace la solicitud
        response = authed_session.get(url)
        response.raise_for_status() 
        return response.json()
        
    except RequestException as e:
        st.error(f"Error de solicitud HTTP a Google Sheets: {e}")
        st.stop()
    except Exception as e:
        st.error(f"Error de autenticación o API: {e}")
        st.stop()

def batch_write(updates):
    """Escribe múltiples rangos en la hoja."""
    if not updates:
        return
        
    try:
        # 1. Obtiene las credenciales parseando el JSON
        credentials_dict = _get_credentials_dict()
        credentials = service_account.Credentials.from_service_account_info(credentials_dict)
        authed_session = AuthorizedSession(credentials)

        spreadsheet_id = st.secrets["sheet_id"]
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values:batchUpdate"
        
        data = {
            "valueInputOption": "USER_ENTERED",
            "data": [
                {"range": range_str, "values": [[value]]}
                for range_str, value in updates
            ]
        }

        response = authed_session.post(url, json=data)
        response.raise_for_status()
        return response.json()
        
    except RequestException as e:
        st.error(f"Error de escritura HTTP a Google Sheets: {e}")
        st.stop()
    except Exception as e:
        st.error(f"Error de autenticación o API al escribir: {e}")
        st.stop()

# ------------------ TIME FORMAT HELPERS ------------------
def parse_time_cell_to_seconds(raw_time_str):
    """Convierte un valor de celda de tiempo (HH:MM:SS) a segundos."""
    if not raw_time_str:
        return 0
    
    cleaned_str = str(raw_time_str).strip()
    
    match = re.search(r'(\d+):(\d+):(\d+)', cleaned_str)
    if match:
        hours, minutes, seconds = map(int, match.groups())
        return hours * 3600 + minutes * 60 + seconds
    
    return 0

def segundos_a_hms(segundos):
    """Convierte segundos a formato HH:MM:SS."""
    segundos = int(segundos)
    h = segundos // 3600
    m = (segundos % 3600) // 60
    s = segundos % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def hms_a_segundos(hms_str):
    """Convierte HH:MM:SS a segundos."""
    if not hms_str: return 0
    parts = list(map(int, hms_str.split(':')))
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return 0
    
def replace_row_in_range(range_str, new_row):
    """Reemplaza el número de fila en un rango A1 (ej: 'Hoja'!B170 -> 'Hoja'!B171)."""
    match = re.search(r'(![A-Z]+)(\d+)', range_str)
    if match:
        return f"{range_str.split('!')[0]}{match.group(1)}{new_row}"
    return range_str

# ------------------ UI HELPERS (sin cambios) ------------------
def sanitize_key(text):
    return re.sub(r'[^a-zA-Z0-9_]', '', text).lower()

def pedir_rerun():
    st.session_state["_do_rerun"] = True

def cargar_estilos():
    st.markdown("""
        <style>
        .materia-card {
            background-color: #262730;
            border: 1px solid #464b5c;
            padding: 15px;
            border-radius: 15px;
            margin-bottom: 10px;
        }
        .materia-title {
            font-size: 1.2rem;
            color: #ccc;
            margin-bottom: 5px;
        }
        .materia-time {
            font-size: 2rem;
            font-weight: bold;
            color: #00e676; 
        }
        .status-badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 8px;
            font-size: 0.8rem;
            font-weight: bold;
            margin-bottom: 5px;
        }
        .status-active {
            background-color: #00e676;
            color: #000;
        }
        .status-inactive {
            background-color: #464b5c;
            color: #fff;
        }
        </style>
    """, unsafe_allow_html=True)

def circle(color):
    return f'<span style="height: 10px; width: 10px; background-color: {color}; border-radius: 50%; display: inline-block;"></span>'


# ------------------ CONSTANTES Y ESTRUCTURAS DE IDIOMAS (sin cambios) ------------------
FILA_BASE = 170 
FECHA_BASE = date(2025, 12, 2) 
SHEET_FACUNDO = "F. Idiomas"
SHEET_IVAN = "I. Idiomas"
SHEET_MARCAS = "marcas"
MARCAS_ROW = 3 

def get_time_row():
    hoy = _argentina_now_global().date()
    delta = (hoy - FECHA_BASE).days
    return FILA_BASE + delta

TIME_ROW = get_time_row()

try:
    IDIOMAS_FACUNDO = st.secrets["facundo_idiomas"]
    IDIOMAS_IVAN = st.secrets["ivan_idiomas"]
except Exception:
    IDIOMAS_FACUNDO = ["Inglés", "Alemán"]
    IDIOMAS_IVAN = ["Japonés", "Francés"]
    st.warning("Usando idiomas de ejemplo. Asegúrate de configurar [idiomas] en secrets.toml")


def map_idiomas_to_ranges(idiomas, sheet, marcas_row, start_col_idx):
    mapping = {}
    col_idx = start_col_idx 
    for idioma in idiomas:
        col_letter = chr(ord('A') + col_idx)
        
        mapping[idioma] = {
            "time": f"'{sheet}'!{col_letter}{TIME_ROW}", 
            "est": f"'{SHEET_MARCAS}'!{col_letter}{marcas_row}"
        }
        col_idx += 1
    return mapping

USERS = {
    "Facundo": map_idiomas_to_ranges(IDIOMAS_FACUNDO, SHEET_FACUNDO, MARCAS_ROW, 1),
    "Iván": map_idiomas_to_ranges(IDIOMAS_IVAN, SHEET_IVAN, MARCAS_ROW, 1 + len(IDIOMAS_FACUNDO)),
}

# ------------------ CARGA UNIFICADA, START/STOP, MAIN (sin cambios en lógica) ------------------
@st.cache_data(ttl=5) 
def cargar_datos_unificados():
    all_ranges = []
    mapa_indices = {"idiomas": {}}
    idx = 0
    for user, idiomas in USERS.items():
        for i, info in idiomas.items():
            all_ranges.append(info["est"]); mapa_indices["idiomas"][(user, i, "est")] = idx; idx += 1
            all_ranges.append(info["time"]); mapa_indices["idiomas"][(user, i, "time")] = idx; idx += 1
    
    if not all_ranges:
        return {"users_data": {u: {"estado": {}, "tiempos": {}} for u in USERS}}

    try:
        res = sheets_batch_get(st.secrets["sheet_id"], all_ranges)
    except Exception as e:
        st.stop()

    values = res.get("valueRanges", [])
    
    def get_val(i, default=""):
        if i >= len(values): return default
        vr = values[i]; rows = vr.get("values", [])
        if not rows: return default
        return rows[0][0] if rows[0] else default

    data_usuarios = {u: {"estado": {}, "tiempos": {}, "inicio_dt": None, "idioma_activo": None} for u in USERS}
    idioma_en_curso = None
    inicio_dt = None

    for user, idiomas in USERS.items():
        for i in idiomas:
            idx_est = mapa_indices["idiomas"][(user, i, "est")]
            raw_est = get_val(idx_est)
            data_usuarios[user]["estado"][i] = raw_est

            idx_time = mapa_indices["idiomas"][(user, i, "time")]
            raw_time = get_val(idx_time)
            secs = parse_time_cell_to_seconds(raw_time)
            data_usuarios[user]["tiempos"][i] = segundos_a_hms(secs)

            if user == st.session_state.get("usuario_seleccionado") and str(raw_est).strip() != "":
                try:
                    inicio_dt = parse_datetime(raw_est)
                    idioma_en_curso = i
                except Exception:
                    pass

    if "usuario_seleccionado" in st.session_state:
        st.session_state["idioma_activo"] = idioma_en_curso
        st.session_state["inicio_dt_idioma"] = inicio_dt 

    return {
        "users_data": data_usuarios,
    }

def start_idioma_callback(usuario, idioma):
    try:
        info = USERS[usuario][idioma]
        now_str = ahora_str()
        
        updates = [
            (info["est"], now_str)
        ] + [
            (i_datos["est"], "")
            for i_datos in USERS[usuario].values()
            if i_datos is not None and i_datos is not info
        ]
        
        batch_write(updates)
        
        st.session_state["idioma_activo"] = idioma
        st.session_state["inicio_dt_idioma"] = parse_datetime(now_str)
        
    except Exception as e:
        st.error(f"start_idioma error: {e}")
    finally:
        pedir_rerun()
        
def stop_idioma_callback(usuario, idioma):
    try:
        info = USERS[usuario][idioma]
        inicio = st.session_state.get("inicio_dt_idioma")
        
        if inicio is None or st.session_state.get("idioma_activo") != idioma:
            try:
                res = sheets_batch_get(st.secrets["sheet_id"], [info["est"]])
                prev_est = res.get("valueRanges", [{}])[0].get("values", [[""]])[0][0] if res.get("valueRanges") else ""
                
                if not prev_est:
                      st.error("No hay marca de inicio registrada. Deteniendo sin guardar tiempo.")
                      pedir_rerun()
                      return
                      
                inicio = parse_datetime(prev_est)
            except Exception as e:
                 st.error(f"Error releyendo marca de inicio de la hoja: {e}")
                 batch_write([(info["est"], "")])
                 pedir_rerun()
                 return

        fin = _argentina_now_global()
        
        if fin <= inicio:
            st.error("Tiempo inválido. La hora de fin es anterior a la de inicio. Limpiando marca.")
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
                prev_raw = res2.get("valueRanges", [{}])[0].get("values", [[""]])[0][0] if res2.get("valueRanges") else ""
            except:
                prev_raw = ""

            new_secs = parse_time_cell_to_seconds(prev_raw) + segs
            updates.append((time_cell_for_row, segundos_a_hms(new_secs)))

        updates.append((info["est"], ""))
        batch_write(updates)
        
        st.session_state["idioma_activo"] = None
        st.session_state["inicio_dt_idioma"] = None
        
    except Exception as e:
        st.error(f"stop_idioma error: {e}")
    finally:
        pedir_rerun()

def main():
    cargar_estilos()

    if st.session_state.get("_do_rerun", False):
        st.session_state["_do_rerun"] = False
        st.rerun()

    if "usuario_seleccionado" not in st.session_state:
        def set_user_and_rerun(u):
            st.session_state["usuario_seleccionado"] = u
            st.rerun()
        
        try:
            params = st.query_params
        except Exception:
            params = st.experimental_get_query_params()

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

    USUARIO_ACTUAL = st.session_state["usuario_seleccionado"]
    OTRO_USUARIO = "Iván" if USUARIO_ACTUAL == "Facundo" else "Facundo"

    idioma_en_curso = st.session_state.get("idioma_activo")
    inicio_dt = st.session_state.get("inicio_dt_idioma")

    if idioma_en_curso is None:
        for i, est_raw in datos[USUARIO_ACTUAL]["estado"].items():
            if str(est_raw).strip() != "":
                try:
                    inicio_dt_sheet = parse_datetime(est_raw)
                    st.session_state["idioma_activo"] = i
                    st.session_state["inicio_dt_idioma"] = inicio_dt_sheet
                    idioma_en_curso = i
                    inicio_dt = inicio_dt_sheet
                except Exception:
                    pass
                break

    usuario_estudiando = idioma_en_curso is not None

    idioma_otro = next((i for i, v in datos[OTRO_USUARIO]["estado"].items() if str(v).strip() != ""), "")
    otro_estudiando = idioma_otro != ""

    circle_usuario = circle("#00e676" if usuario_estudiando else "#ffffff")
    circle_otro = circle("#00e676" if otro_estudiando else "#ffffff")

    placeholder_total = st.empty()
    placeholder_idiomas = {i: st.empty() for i in USERS[USUARIO_ACTUAL]}

    while True:
        tiempo_anadido_seg = 0
        if usuario_estudiando and inicio_dt is not None:
            tiempo_anadido_seg = int((_argentina_now_global() - inicio_dt).total_seconds())

        def calcular_total_tiempo(usuario, tiempo_activo_seg_local=0):
            total_min = 0.0
            for idioma, info in USERS[usuario].items():
                base_seg = hms_a_segundos(datos[usuario]["tiempos"][idioma])
                segs_idioma = base_seg
                if usuario_estudiando and usuario == USUARIO_ACTUAL and idioma == idioma_en_curso:
                    segs_idioma += tiempo_activo_seg_local
                total_min += segs_idioma / 60
            return total_min

        total_min = calcular_total_tiempo(USUARIO_ACTUAL, tiempo_anadido_seg)
        total_hms = segundos_a_hms(int(total_min * 60))

        with placeholder_total.container():
            st.markdown(f"""
                <div style="background-color: #1e1e1e; padding: 15px; border-radius: 10px; margin-bottom: 20px; text-align: center;">
                    <div style="font-size: 1.2rem; color: #aaa; margin-bottom: 5px;">Tiempo total de Idiomas hoy: {USUARIO_ACTUAL}</div>
                    <div style="width: 100%; font-size: 2.5rem; font-weight: bold; color: #fff; line-height: 1.2;">{total_hms}</div>
                </div>
            """, unsafe_allow_html=True)

            o_total_min = calcular_total_tiempo(OTRO_USUARIO)
            o_total_hms = segundos_a_hms(int(o_total_min * 60))

            idioma_visible = 'visible' if idioma_otro else 'hidden'
            idioma_nombre_html = f'<span style="color:#00e676; margin-left:6px; visibility:{idioma_visible};">{idioma_otro if idioma_otro else "Libre"}</span>'

            with st.expander(f"Progreso de {OTRO_USUARIO} en idiomas.", expanded=False):
                 st.markdown(f"""
                    <div style="margin-bottom: 10px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <span style="font-size: 1.1rem; color: #ddd;"><b>{o_total_hms}</b></span>
                        </div>
                        <div style="display:flex; justify-content:flex-start; align-items:center; font-size:0.9rem; color:#aaa; margin-top:5px;">
                            {circle_otro}
                            {idioma_nombre_html}
                        </div>
                    </div>
                """, unsafe_allow_html=True)
            
            st.subheader(f"Tus idiomas, {USUARIO_ACTUAL}")
        
        mis_idiomas = USERS[USUARIO_ACTUAL]
        for idioma in mis_idiomas:

            base_seg = hms_a_segundos(datos[USUARIO_ACTUAL]["tiempos"][idioma])
            tiempo_total_seg = base_seg
            en_curso = idioma_en_curso == idioma

            if en_curso:
                tiempo_total_seg += max(0, tiempo_anadido_seg)

            tiempo_total_hms = segundos_a_hms(tiempo_total_seg)
            badge_html = f'<div class="status-badge status-active">🟢 Estudiando...</div>' if en_curso else ''
            html_card = f"""<div class="materia-card"><div class="materia-title">{idioma}</div>{badge_html}<div class="materia-time">{tiempo_total_hms}</div></div>"""

            with placeholder_idiomas[idioma].container():
                st.markdown(html_card, unsafe_allow_html=True)

                key_start = sanitize_key(f"start_{USUARIO_ACTUAL}_{idioma}_idioma")
                key_stop = sanitize_key(f"stop_{USUARIO_ACTUAL}_{idioma}_idioma")
                key_disabled = sanitize_key(f"dis_{USUARIO_ACTUAL}_{idioma}_idioma")

                cols = st.columns([1,1,1])
                with cols[0]:
                    if en_curso:
                        st.button(f"⛔ DETENER {idioma[:10]}", key=key_stop, use_container_width=True,
                                  on_click=stop_idioma_callback, args=(USUARIO_ACTUAL, idioma))
                    else:
                        if idioma_en_curso is None:
                            st.button("▶ INICIAR", key=key_start, use_container_width=True,
                                      on_click=start_idioma_callback, args=(USUARIO_ACTUAL, idioma))
                        else:
                            st.button("...", disabled=True, key=key_disabled, use_container_width=True)

                with cols[1]:
                    with st.expander("🛠️ Corregir tiempo"):
                        input_key = f"input_{sanitize_key(idioma)}_idioma"
                        new_val = st.text_input("Tiempo (HH:MM:SS)", value=datos[USUARIO_ACTUAL]["tiempos"][idioma], key=input_key)

                        def save_correction_callback(idioma_key):
                            if st.session_state.get("idioma_activo") is not None:
                                st.error("⛔ No podés corregir el tiempo mientras estás estudiando.")
                                pedir_rerun()
                                return

                            val = st.session_state.get(f"input_{sanitize_key(idioma_key)}_idioma", "").strip()
                            if ":" not in val:
                                st.error("Formato inválido (debe ser HH:MM:SS)")
                                pedir_rerun()
                                return

                            try:
                                segs = hms_a_segundos(val)
                                hhmmss = segundos_a_hms(segs)
                                target_row = get_time_row()
                                time_cell_for_row = replace_row_in_range(USERS[USUARIO_ACTUAL][idioma_key]["time"], target_row)
                                batch_write([(time_cell_for_row, hhmmss)])
                                st.success("Tiempo corregido correctamente.")
                            except Exception as e:
                                st.error(f"Error al corregir el tiempo: {e}")
                            finally:
                                pedir_rerun()

                        if en_curso or usuario_estudiando:
                            st.info("⛔ No podés corregir.")
                        else:
                            if st.button("Guardar Corrección", key=f"save_{sanitize_key(idioma)}_idioma_btn", on_click=save_correction_callback, args=(idioma,)):
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