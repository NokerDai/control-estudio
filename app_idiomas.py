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
    try:
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            dt = datetime.strptime(dt_str, "%d/%m/%Y %H:%M:%S")
        except ValueError:
            st.warning(f"No se pudo parsear la fecha: {dt_str}")
            return None
    
    tz = _get_tzinfo()
    if tz:
        if hasattr(tz, 'localize'):
             return tz.localize(dt)
        return dt.replace(tzinfo=tz)
    return dt 

# ------------------ GOOGLE SHEETS API CONFIG ------------------
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
]
SPREADSHEET_ID = st.secrets["sheet_id"] 

# ------------------ CONSTANTES Y UTILS ------------------
USUARIO_ACTUAL = None # Se usa como variable global para la sesión

def sanitize_key(text):
    """Sanitiza el texto y lo convierte a minúsculas para usarlo como clave."""
    return re.sub(r'[^a-zA-Z0-9_]', '', text).lower()

# **NUEVO** Mapeo para determinar qué hoja usar por usuario
# Debe coincidir con los nombres de usuario y las claves sanitizadas.
IDIOMA_SHEETS = {
    sanitize_key("Facundo"): "F. Idiomas",
    sanitize_key("Ivan"): "I. Idiomas",
    # Añade aquí otros usuarios si es necesario
}

def get_user_time_sheet_name(usuario_key):
    """Retorna el nombre de la hoja de idiomas del usuario actual."""
    return IDIOMA_SHEETS.get(usuario_key, None) 

def replace_row_in_range(cell_range, new_row):
    """Reemplaza el número de fila en un rango A1 (ej: 'Hoja!B2') con el nuevo número."""
    # El rango debe ser solo una celda, ej: 'Hoja!B2'
    if '!' in cell_range:
        sheet, cell = cell_range.split('!')
    else:
        sheet, cell = None, cell_range
    
    match = re.match(r"([A-Za-z]+)(\d+)", cell)
    if match:
        col = match.group(1)
        new_cell = f"{col}{new_row}"
        # Si la hoja ya estaba en el rango (ej: F. Idiomas!B2), la mantiene.
        return f"{sheet}!{new_cell}" if sheet else new_cell
    return cell_range 

# ------------------ CONEXIÓN GOOGLE SHEETS ------------------
@st.cache_resource(ttl=timedelta(hours=6))
def get_service_account_credentials():
    try:
        info = st.secrets["service_account"] 
        if isinstance(info, str):
            info = json.loads(info)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES
        )
        return creds
    except Exception as e:
        st.error(f"Error al cargar credenciales de GCP: {e}")
        st.stop()
        
@st.cache_resource(ttl=timedelta(hours=6))
def get_authorized_session():
    """Retorna una sesión HTTP autorizada."""
    try:
        creds = get_service_account_credentials()
        authed_session = AuthorizedSession(creds)
        return authed_session
    except Exception as e:
        st.error(f"Error al obtener sesión autorizada: {e}")
        st.stop()

def google_sheets_api_call(method, api_path, params=None, body=None):
    authed_session = get_authorized_session()
    base_url = "https://sheets.googleapis.com/v4/spreadsheets/"
    url = f"{base_url}{SPREADSHEET_ID}/{api_path}"

    try:
        if method == 'get':
            response = authed_session.get(url, params=params)
        elif method == 'post':
            response = authed_session.post(url, params=params, json=body)
        elif method == 'put':
            response = authed_session.put(url, params=params, json=body)
        else:
            raise ValueError(f"Método HTTP no soportado: {method}")

        response.raise_for_status()
        return response.json()

    except RequestException as e:
        st.error(f"Error de solicitud HTTP a Google Sheets: {e}")
        st.error(f"URL: {url}")
        st.error(f"Respuesta: {response.text if 'response' in locals() else 'N/A'}")
        return None
    except Exception as e:
        st.error(f"Error inesperado en la llamada a la API: {e}")
        return None

def pedir_rerun():
    time.sleep(0.1) 
    st.rerun()

# ------------------ DATOS y CONFIGURACIÓN ------------------
@st.cache_data(ttl=3600, show_spinner="Cargando configuración de usuarios...")
def cargar_configuracion_de_usuarios():
    # CORRECCIÓN DEL ERROR 400: Encerrar el nombre de la hoja en comillas simples 
    SHEET_RANGE = "'Config'!A1:Z100" 
    
    response = google_sheets_api_call(
        'get',
        f"values/{SHEET_RANGE}",
        params={'majorDimension': 'ROWS'}
    )
    if not response or 'values' not in response:
        st.error("No se pudo cargar la configuración de usuarios de la hoja de cálculo.")
        return {}

    values = response['values']
    if not values:
        return {}
    
    header = [h.strip() for h in values[0]]
    USERS_CONFIG = {}
    
    for row in values[1:]:
        if not row or not row[0]: 
            continue

        user_name = row[0].strip()
        user_key = sanitize_key(user_name)
        USERS_CONFIG[user_key] = {"name": user_name} # Guardar el nombre visible
        
        # Procesar los idiomas para el usuario
        for i, col_name in enumerate(header):
            if i >= 1: # Ignorar la columna de nombre de usuario
                if len(row) > i and row[i].strip():
                    item_name = col_name.strip()
                    item_key = sanitize_key(item_name)
                    # El valor de la celda es solo el rango (ej: 'C2'), que indica la columna y la fila base
                    cell_range = row[i].strip() 

                    USERS_CONFIG[user_key][item_key] = {
                        "name": item_name,
                        "time": cell_range # Celda base (ej: 'C2')
                    }

    return USERS_CONFIG

# ------------------ FUNCIONES DE LA APP ------------------
def get_user_options():
    USERS = cargar_configuracion_de_usuarios()
    return {user_key: USERS[user_key]['name'] for user_key in USERS}

# ------------------ LÓGICA DE TIEMPO Y HOJAS ------------------

@st.cache_data(ttl=timedelta(minutes=5), show_spinner=False)
def get_sheet_content(sheet_name):
    """Obtiene los valores de una hoja específica."""
    # NOTA: No es necesario usar comillas aquí porque el nombre de la hoja se pasa
    # como parte de un rango A1 (ej: F. Idiomas!A1:Z100)
    response = google_sheets_api_call(
        'get',
        f'values/{sheet_name}!A1:Z100', 
        params={'majorDimension': 'ROWS'}
    )
    if not response or 'values' not in response:
        st.error(f"Error al obtener la hoja de tiempo: {sheet_name}.")
        return []
    return response['values']

def get_time_row(sheet_name):
    """Encuentra la fila del día actual o crea una nueva, usando la hoja dada."""
    now_date_str = ahora_str().split(' ')[0] # YYYY-MM-DD
    time_sheet = get_sheet_content(sheet_name)
    
    if not time_sheet:
        return None
        
    # Asume que la columna A tiene la fecha
    for i, row in enumerate(time_sheet):
        if row and row[0] == now_date_str:
            return i + 1 # Retorna el número de fila (base 1)

    # Si no existe, encuentra la primera fila vacía para registrar la nueva fecha
    for i, row in enumerate(time_sheet):
        if not row or not row[0]:
            fila_vacia = i + 1
            fecha_celda = f'{sheet_name}!A{fila_vacia}' # Usa el nombre de la hoja correcto
            batch_write([(fecha_celda, now_date_str)])
            get_sheet_content.clear() # Limpiar el caché de esta hoja
            return fila_vacia
            
    st.warning(f"La hoja de tiempo ({sheet_name}) está llena o el rango es insuficiente.")
    return None

def batch_write(updates):
    """Escribe múltiples valores en la hoja en una sola solicitud."""
    if not updates:
        return True
        
    value_input_option = 'USER_ENTERED' 
    
    data = []
    for cell_range, value in updates:
        data.append({
            'range': cell_range,
            'values': [[value]]
        })

    body = {
        'valueInputOption': value_input_option,
        'data': data
    }
    
    response = google_sheets_api_call(
        'post',
        'values:batchUpdate',
        params={'alt': 'json'},
        body=body
    )
    
    if response and 'responses' in response:
        return True
    return False

def get_user_current_status(usuario_key):
    """
    Lee el tiempo acumulado de la hoja de cálculo del día actual para el usuario y sus idiomas.
    Retorna un diccionario de {idioma_key: current_time_seconds}.
    """
    sheet_name = get_user_time_sheet_name(usuario_key)
    if not sheet_name:
        st.error(f"Hoja de idioma no encontrada para el usuario: {usuario_key}")
        return {}
        
    # 1. Obtener la fila dinámica del día
    row_num = get_time_row(sheet_name)
    if not row_num:
        return {}
        
    time_sheet_content = get_sheet_content(sheet_name)
    USERS = cargar_configuracion_de_usuarios()
    current_times = {}
    user_config = USERS.get(usuario_key, {})
    
    for idioma_key, config in user_config.items():
        if idioma_key == 'name':
            continue
            
        # El rango base (ej: 'C2')
        cell_range_base = config["time"] 
        
        # El rango A1 final (ej: F. Idiomas!C170)
        full_cell_range = replace_row_in_range(f"{sheet_name}!{cell_range_base}", row_num)
        
        # Obtenemos la coordenada de la celda (ej: C, 170)
        match = re.match(r"[A-Za-z]+!([A-Za-z]+)(\d+)", full_cell_range)
        if match:
            col_letter = match.group(1).upper()
            
            # Convertir la letra de columna a índice (A=0, B=1, etc.)
            col_index = 0
            for char in col_letter:
                col_index = col_index * 26 + (ord(char) - ord('A')) + 1
            col_index -= 1

            # Intentar leer el valor de la celda en la fila dinámica
            try:
                time_value = time_sheet_content[row_num - 1][col_index] 
                current_times[idioma_key] = hms_a_segundos(time_value)
            except (IndexError, ValueError):
                current_times[idioma_key] = 0

    return current_times

def hms_a_segundos(hms_str):
    """Convierte HH:MM:SS o MM:SS a segundos."""
    parts = list(map(int, hms_str.split(':')))
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, m, s = 0, parts[0], parts[1]
    else:
        return 0
    return h * 3600 + m * 60 + s

def segundos_a_hms(total_segundos):
    """Convierte segundos a formato HH:MM:SS."""
    h = total_segundos // 3600
    m = (total_segundos % 3600) // 60
    s = total_segundos % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def init_session_state():
    """Inicializa variables de sesión si no existen."""
    if "user_options" not in st.session_state:
        st.session_state.user_options = get_user_options()
        
    if "usuario_seleccionado" not in st.session_state:
        st.session_state.usuario_seleccionado = None
    
    if "idioma_en_curso" not in st.session_state:
        st.session_state.idioma_en_curso = None
        
    if "tiempo_inicio_idiomas" not in st.session_state:
        st.session_state.tiempo_inicio_idiomas = None
        
    if "tiempo_actual_idiomas" not in st.session_state:
        st.session_state.tiempo_actual_idiomas = 0 # En segundos


def start_study_session(idioma):
    """Inicia la sesión de estudio para un idioma."""
    st.session_state.idioma_en_curso = idioma
    st.session_state.tiempo_inicio_idiomas = ahora_str() 
    
    idioma_key = sanitize_key(idioma)
    
    # Obtener el tiempo de la hoja para inicializar el contador
    current_times = get_user_current_status(st.session_state.usuario_seleccionado)
    st.session_state.tiempo_actual_idiomas = current_times.get(idioma_key, 0)
    
    pass

def stop_study_session(idioma):
    """Finaliza la sesión de estudio, calcula el tiempo y lo registra."""
    if st.session_state.idioma_en_curso != idioma:
        st.warning(f"No hay una sesión activa para {idioma}.")
        return

    tiempo_fin = _argentina_now_global()
    tiempo_inicio = parse_datetime(st.session_state.tiempo_inicio_idiomas)
    
    if not tiempo_inicio:
        st.error("Error al obtener el tiempo de inicio.")
        return
        
    if tiempo_fin.tzinfo is None:
        tz = _get_tzinfo()
        if tz:
            tiempo_fin = tiempo_fin.astimezone(tz)

    tiempo_transcurrido = tiempo_fin - tiempo_inicio
    tiempo_total_segundos = st.session_state.tiempo_actual_idiomas + int(tiempo_transcurrido.total_seconds())
    tiempo_total_hms = segundos_a_hms(tiempo_total_segundos)

    # 1. OBTENER RANGO DINÁMICO
    USERS = cargar_configuracion_de_usuarios()
    usuario_key = st.session_state.usuario_seleccionado
    idioma_key = sanitize_key(idioma)
    sheet_name = get_user_time_sheet_name(usuario_key)
    
    if not sheet_name or usuario_key not in USERS or idioma_key not in USERS[usuario_key]:
        st.error(f"Configuración de usuario/idioma/hoja no encontrada para {idioma}.")
        return
    
    target_row = get_time_row(sheet_name) # Obtener la fila del día
    if not target_row:
         st.error(f"No se pudo encontrar o crear la fila del día en la hoja {sheet_name}.")
         return

    time_cell_base = USERS[usuario_key][idioma_key]["time"] # Ej: 'C2'
    time_cell_for_row = replace_row_in_range(f"{sheet_name}!{time_cell_base}", target_row)
    
    # 2. ESCRIBIR
    updates = [(time_cell_for_row, tiempo_total_hms)]
    
    # 3. LIMPIAR ESTADO DE SESIÓN
    st.session_state.idioma_en_curso = None
    st.session_state.tiempo_inicio_idiomas = None
    st.session_state.tiempo_actual_idiomas = 0
    
    # 4. REALIZAR LA ESCRITURA
    if batch_write(updates):
        st.success(f"Sesión de {idioma} finalizada y tiempo registrado en {time_cell_for_row}.")
    else:
        st.error(f"Error al guardar el tiempo total de {idioma}.")
        
    get_sheet_content.clear() # Limpiar el caché de la hoja para que se recargue

def main():
    init_session_state()
    USERS = cargar_configuracion_de_usuarios()
    global USUARIO_ACTUAL
    
    st.title("🌎 Seguimiento de Idiomas")
    
    # Normalización y Selección de Usuario (Mantiene la corrección del KeyError)
    if "usuario_seleccionado" in st.session_state and st.session_state.usuario_seleccionado:
        current_user_val = st.session_state.usuario_seleccionado 
        if current_user_val not in st.session_state.user_options:
            found_key = next((
                key for key in st.session_state.user_options.keys() 
                if key == sanitize_key(current_user_val) 
            ), None)
            
            if found_key:
                st.session_state.usuario_seleccionado = found_key
            else:
                st.session_state.usuario_seleccionado = None
    
    if not st.session_state.usuario_seleccionado:
        visible_options = [""] + list(st.session_state.user_options.values())
        
        user_name_selected = st.selectbox(
            "Selecciona tu usuario:",
            options=visible_options,
            key="idiomas_user_select_name"
        )
        
        if user_name_selected:
            user_key = next((
                key for key, name in st.session_state.user_options.items() 
                if name == user_name_selected
            ), None)
            
            if user_key:
                st.session_state.usuario_seleccionado = user_key
                st.rerun()
            else:
                 st.error("No se encontró la clave de usuario. Algo salió mal.")
                 st.stop()
        else:
            st.stop()
            
    USUARIO_ACTUAL = st.session_state.usuario_seleccionado
    user_name = st.session_state.user_options[USUARIO_ACTUAL] 
    st.sidebar.markdown(f"**Usuario:** {user_name}")
    
    usuario_estudiando = st.session_state.idioma_en_curso is not None
    
    if usuario_estudiando:
        tiempo_inicio_dt = parse_datetime(st.session_state.tiempo_inicio_idiomas)
        if tiempo_inicio_dt:
            tiempo_transcurrido = _argentina_now_global() - tiempo_inicio_dt
            tiempo_actual_sesion = int(tiempo_transcurrido.total_seconds())
            tiempo_mostrar = st.session_state.tiempo_actual_idiomas + tiempo_actual_sesion
            
            st.header(f"Estudiando {st.session_state.idioma_en_curso}...")
            st.subheader(f"⏱️ {segundos_a_hms(tiempo_mostrar)}")
        
    
    current_times = get_user_current_status(USUARIO_ACTUAL)
    
    for idioma_key, config in USERS[USUARIO_ACTUAL].items():
        if idioma_key == 'name':
            continue
            
        idioma = config["name"]
        tiempo_acumulado_seg = current_times.get(idioma_key, 0)
        tiempo_acumulado_hms = segundos_a_hms(tiempo_acumulado_seg)
        
        col1, col2 = st.columns([1, 4])
        
        with col1:
            st.subheader(idioma)
            st.markdown(f"**Total (Hoy):** {tiempo_acumulado_hms}") # Aclaración que es el tiempo de HOY
            
        with col2:
            en_curso = st.session_state.idioma_en_curso == idioma
            
            if en_curso:
                st.button(
                    f"🛑 Detener {idioma}", 
                    key=f"stop_{idioma_key}", 
                    on_click=stop_study_session, 
                    args=(idioma,), 
                    type="danger",
                    use_container_width=True
                )
            elif usuario_estudiando:
                st.button(
                    f"⏳ Estudiando otra cosa...", 
                    key=f"disabled_{idioma_key}", 
                    disabled=True,
                    use_container_width=True
                )
            else:
                st.button(
                    f"▶️ Iniciar {idioma}", 
                    key=f"start_{idioma_key}", 
                    on_click=start_study_session, 
                    args=(idioma,),
                    type="primary",
                    use_container_width=True
                )
                
            with st.expander(f"Corregir tiempo de {idioma} (Hoy)"):
                
                def save_correction_callback(idioma_param):
                    idioma_key_param = sanitize_key(idioma_param)
                    input_key = f"input_{idioma_key_param}_idioma_txt"
                    
                    val = st.session_state.get(input_key)
                    if not val:
                        st.warning("El campo no puede estar vacío.")
                        return

                    try:
                        segs = hms_a_segundos(val)
                        hhmmss = segundos_a_hms(segs)
                        
                        # Obtener rango dinámico para escribir
                        sheet_name = get_user_time_sheet_name(USUARIO_ACTUAL)
                        target_row = get_time_row(sheet_name)
                        time_cell_base = USERS[USUARIO_ACTUAL][idioma_key_param]["time"]
                        time_cell_for_row = replace_row_in_range(f"{sheet_name}!{time_cell_base}", target_row)
                        
                        batch_write([(time_cell_for_row, hhmmss)])
                        st.success("Tiempo corregido correctamente.")
                    except Exception as e:
                        st.error(f"Error al corregir el tiempo: {e}")
                    finally:
                        get_sheet_content.clear() 
                        pedir_rerun()
                
                st.text_input(
                    "Nuevo Tiempo (HH:MM:SS):", 
                    value=tiempo_acumulado_hms, 
                    key=f"input_{idioma_key}_idioma_txt"
                )

                if en_curso or usuario_estudiando:
                    st.info("⛔ No podés corregir mientras haya una sesión activa.")
                else:
                    if st.button("Guardar Corrección", key=f"save_{idioma_key}_idioma_btn", on_click=save_correction_callback, args=(idioma,)):
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