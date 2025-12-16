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
    # Intentar parsear el formato con el que lo guardamos
    try:
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        # Intentar parsear el formato de fecha/hora corta de Google Sheets (no debería pasar)
        try:
            dt = datetime.strptime(dt_str, "%d/%m/%Y %H:%M:%S")
        except ValueError:
            st.warning(f"No se pudo parsear la fecha: {dt_str}")
            return None
    
    # Si logramos parsear, añadimos la zona horaria (Buenos Aires)
    tz = _get_tzinfo()
    if tz:
        return tz.localize(dt)
    return dt # Retornar sin TZ si no se pudo obtener

# ------------------ GOOGLE SHEETS API CONFIG ------------------
# 1. CORRECCIÓN: Usar SCOPES en lugar de SCOPES_IDIOMAS.
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
]
SPREADSHEET_ID = st.secrets["spreadsheet_id_idiomas"] 

# ------------------ CONSTANTES Y UTILS ------------------
HOJA_ESTUDIO = "Estudio"
USUARIO_ACTUAL = None # Se usa como variable global para la sesión

def sanitize_key(text):
    return re.sub(r'[^a-zA-Z0-9_]', '', text)

def replace_row_in_range(cell_range, new_row):
    """Reemplaza el número de fila en un rango A1 (ej: 'B2') con el nuevo número."""
    # El rango debe ser solo una celda, ej: 'Hoja!B2'
    if '!' in cell_range:
        sheet, cell = cell_range.split('!')
    else:
        sheet, cell = None, cell_range
    
    # Busca la parte de la columna (letras) y el número de fila
    match = re.match(r"([A-Za-z]+)(\d+)", cell)
    if match:
        col = match.group(1)
        new_cell = f"{col}{new_row}"
        return f"{sheet}!{new_cell}" if sheet else new_cell
    return cell_range # Retorna el original si no pudo parsear

# ------------------ CONEXIÓN GOOGLE SHEETS ------------------
@st.cache_resource(ttl=timedelta(hours=6))
def get_service_account_credentials():
    try:
        # Load from streamlit secrets
        # 2. CORRECCIÓN: Usar la clave correcta 'service_account'
        info = st.secrets["service_account"] 

        # Create credentials object
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES
        )
        return creds
    except Exception as e:
        st.error(f"Error al cargar credenciales de GCP: {e}")
        st.stop()
        
@st.cache_resource(ttl=timedelta(hours=6))
def get_authorized_session():
    """Retorna una sesión HTTP autorizada para interactuar con la API."""
    try:
        creds = get_service_account_credentials()
        authed_session = AuthorizedSession(creds)
        return authed_session
    except Exception as e:
        # Este error es el que estabas viendo. Con las correcciones, debería solucionarse.
        st.error(f"Error al obtener sesión autorizada (revisa SCOPES o credenciales): {e}")
        st.stop()

# Funciones auxiliares de la API
def google_sheets_api_call(method, api_path, params=None, body=None):
    # ... (contenido de esta función)
    # [Mantener el cuerpo original de esta función]
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

        response.raise_for_status() # Lanza una excepción para errores HTTP (4xx o 5xx)
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
    # Helper para forzar la actualización después de una acción
    # Necesario para que Streamlit refresque la interfaz y las variables de sesión
    time.sleep(0.1) # Pequeña pausa
    st.rerun()

# ------------------ DATOS ------------------
@st.cache_data(ttl=3600, show_spinner="Cargando configuración de usuarios...")
def cargar_configuracion_de_usuarios():
    # Obtiene la hoja de configuración de usuarios (asumiendo que es la misma que estudio)
    response = google_sheets_api_call(
        'get',
        'values/Config!A1:Z100',
        params={'majorDimension': 'ROWS'}
    )
    if not response or 'values' not in response:
        st.error("No se pudo cargar la configuración de usuarios de la hoja de cálculo.")
        return {}

    values = response['values']
    if not values:
        return {}
    
    # Asume que la primera fila es el encabezado y las subsiguientes son usuarios
    header = [h.strip() for h in values[0]]
    USERS_CONFIG = {}
    
    for row in values[1:]:
        if not row or not row[0]: # Si la fila está vacía o el nombre de usuario falta
            continue

        user_name = row[0].strip()
        user_key = sanitize_key(user_name)
        USERS_CONFIG[user_key] = {}
        
        # Procesar las materias o idiomas para el usuario
        for i, col_name in enumerate(header):
            if i >= 1: # Ignorar la columna de nombre de usuario
                if len(row) > i and row[i].strip():
                    item_name = col_name.strip()
                    item_key = sanitize_key(item_name)
                    cell_range = row[i].strip() # Espera un rango de celda (ej: 'C2')

                    # Las columnas de idiomas se asumen con nombres de idiomas (ej: 'Inglés')
                    # y contienen la celda de tiempo de ese idioma (ej: 'C2')
                    USERS_CONFIG[user_key][item_key] = {
                        "name": item_name,
                        "time": cell_range # Celda donde se guarda el tiempo acumulado
                    }

    return USERS_CONFIG

# ------------------ FUNCIONES DE LA APP ------------------
def get_user_options():
    # ... (contenido de esta función)
    USERS = cargar_configuracion_de_usuarios()
    return {user_key: USERS[user_key]['name'] for user_key in USERS}

# ------------------ LÓGICA DE ESTADO ------------------
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

# ------------------ LÓGICA DE LA HOJA DE TIEMPO ------------------
@st.cache_data(ttl=timedelta(minutes=5), show_spinner=False)
def get_time_sheet():
    """Obtiene los valores de la hoja de 'Estudio' para leer el tiempo actual."""
    response = google_sheets_api_call(
        'get',
        f'values/{HOJA_ESTUDIO}!A1:Z100', # Rango amplio, ajusta si es necesario
        params={'majorDimension': 'ROWS'}
    )
    if not response or 'values' not in response:
        st.error("Error al obtener la hoja de tiempo.")
        return []
    return response['values']

def get_time_row():
    """Busca la fila que corresponde al día de hoy para registro de tiempo."""
    now_date_str = ahora_str().split(' ')[0] # YYYY-MM-DD
    time_sheet = get_time_sheet()
    
    if not time_sheet:
        return None
        
    # Asume que la columna A tiene la fecha
    for i, row in enumerate(time_sheet):
        if row and row[0] == now_date_str:
            return i + 1 # Retorna el número de fila (base 1)

    # Si no existe, encuentra la primera fila vacía para registrar la nueva fecha
    for i, row in enumerate(time_sheet):
        if not row or not row[0]:
            # Inserta la fecha en la primera columna vacía y retorna el número de fila
            fila_vacia = i + 1
            fecha_celda = f'{HOJA_ESTUDIO}!A{fila_vacia}'
            batch_write([(fecha_celda, now_date_str)])
            # Forzar una invalidación del caché de la hoja para que la próxima
            # vez que se pida, ya tenga la fecha de hoy
            get_time_sheet.clear() 
            return fila_vacia
            
    # Si la hoja está llena (100 filas)
    st.warning("La hoja de tiempo está llena o el rango de búsqueda es insuficiente.")
    return None

def batch_write(updates):
    """Escribe múltiples valores en la hoja en una sola solicitud."""
    if not updates:
        return True
        
    value_input_option = 'USER_ENTERED' # Para que interprete HH:MM:SS correctamente
    
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
    Lee el tiempo acumulado de la hoja de cálculo para el usuario y sus idiomas.
    Retorna un diccionario de {idioma_key: current_time_seconds}.
    """
    time_sheet = get_time_sheet()
    USERS = cargar_configuracion_de_usuarios()
    
    if not time_sheet:
        return {}
        
    current_times = {}
    
    # La configuración de usuario tiene la celda (ej: 'C2', 'E2', etc.)
    user_config = USERS.get(usuario_key, {})
    
    # Recorrer los idiomas del usuario
    for idioma_key, config in user_config.items():
        if idioma_key == 'name':
            continue
            
        cell_range = config["time"] # Ej: 'C2'
        
        # Obtenemos la coordenada de la celda (ej: C, 2)
        match = re.match(r"([A-Za-z]+)(\d+)", cell_range)
        if match:
            col_letter = match.group(1).upper()
            row_num = int(match.group(2))
            
            # Convertir la letra de columna a índice (A=0, B=1, etc.)
            col_index = 0
            for char in col_letter:
                col_index = col_index * 26 + (ord(char) - ord('A')) + 1
            col_index -= 1

            # Intentar leer el valor de la celda
            try:
                # La fila 'row_num' es base 1, por lo que el índice de la lista es 'row_num - 1'
                time_value = time_sheet[row_num - 1][col_index] 
                current_times[idioma_key] = hms_a_segundos(time_value)
            except IndexError:
                # Si la celda está fuera del rango de datos leídos, o está vacía
                current_times[idioma_key] = 0
            except ValueError:
                # Si el formato no es válido (ej: texto que no es tiempo)
                current_times[idioma_key] = 0

    return current_times

def start_study_session(idioma):
    """Inicia la sesión de estudio para un idioma."""
    st.session_state.idioma_en_curso = idioma
    st.session_state.tiempo_inicio_idiomas = ahora_str() # Guardar como string
    
    # El tiempo acumulado actual del idioma
    USERS = cargar_configuracion_de_usuarios()
    idioma_key = sanitize_key(idioma)
    
    # Obtener el tiempo de la hoja para inicializar el contador
    current_times = get_user_current_status(st.session_state.usuario_seleccionado)
    st.session_state.tiempo_actual_idiomas = current_times.get(idioma_key, 0)
    
    # Registrar el inicio en la fila del día
    target_row = get_time_row()
    if target_row:
        # Se asume que en USERS la celda 'time' es la celda de la suma total (ej: C2)
        # Queremos escribir en la celda de tiempo del día de hoy.
        # En la hoja de estudio, hay una columna 'Inglés (Hora Inicio)', 'Inglés (Duración)', etc.
        # Esto requiere una lógica de mapeo más compleja. Por simplicidad, 
        # y asumiendo que solo se registra la duración diaria en la celda de tiempo, 
        # actualizamos el tiempo total al finalizar.
        pass

def stop_study_session(idioma):
    """Finaliza la sesión de estudio, calcula el tiempo y lo registra."""
    if st.session_state.idioma_en_curso != idioma:
        st.warning(f"No hay una sesión activa para {idioma}.")
        return

    tiempo_fin = _argentina_now_global()
    
    # Parsear el tiempo de inicio guardado como string y añadirle la zona horaria
    tiempo_inicio = parse_datetime(st.session_state.tiempo_inicio_idiomas)
    
    if not tiempo_inicio:
        st.error("Error al obtener el tiempo de inicio.")
        return
        
    # Asegurar que ambos tengan zona horaria para la resta
    if tiempo_fin.tzinfo is None:
        tz = _get_tzinfo()
        if tz:
            tiempo_fin = tiempo_fin.astimezone(tz)

    tiempo_transcurrido = tiempo_fin - tiempo_inicio
    
    # Sumar el tiempo nuevo al acumulado que teníamos al inicio de la sesión
    tiempo_total_segundos = st.session_state.tiempo_actual_idiomas + int(tiempo_transcurrido.total_seconds())
    tiempo_total_hms = segundos_a_hms(tiempo_total_segundos)

    # 1. ACTUALIZAR LA CELDA DE TIEMPO TOTAL
    USERS = cargar_configuracion_de_usuarios()
    usuario_key = st.session_state.usuario_seleccionado
    idioma_key = sanitize_key(idioma)
    
    if usuario_key not in USERS or idioma_key not in USERS[usuario_key]:
        st.error(f"Configuración de usuario/idioma no encontrada para {idioma}.")
        return
        
    time_cell = USERS[usuario_key][idioma_key]["time"] # Ej: 'C2'
    
    # Escribir el nuevo total en la celda de tiempo (ej: C2)
    updates = [(time_cell, tiempo_total_hms)]
    
    # 2. LIMPIAR ESTADO DE SESIÓN
    st.session_state.idioma_en_curso = None
    st.session_state.tiempo_inicio_idiomas = None
    st.session_state.tiempo_actual_idiomas = 0
    
    # 3. REALIZAR LA ESCRITURA
    if batch_write(updates):
        st.success(f"Sesión de {idioma} finalizada y tiempo registrado.")
    else:
        st.error(f"Error al guardar el tiempo total de {idioma}.")
        
    get_time_sheet.clear() # Limpiar el caché de la hoja para que se recargue

def main():
    init_session_state()
    USERS = cargar_configuracion_de_usuarios()
    global USUARIO_ACTUAL # Para usarlo en la corrección
    
    st.title("🌎 Seguimiento de Idiomas")
    
    # Selección de Usuario (Igual que app_estudio)
    if not st.session_state.usuario_seleccionado:
        user_selection = st.selectbox(
            "Selecciona tu usuario:",
            options=[""] + list(st.session_state.user_options.keys()),
            format_func=lambda x: st.session_state.user_options.get(x, "Seleccionar..."),
            key="idiomas_user_select"
        )
        if user_selection:
            st.session_state.usuario_seleccionado = user_selection
            st.rerun()
        else:
            st.stop()
            
    USUARIO_ACTUAL = st.session_state.usuario_seleccionado
    user_name = st.session_state.user_options[USUARIO_ACTUAL]
    st.sidebar.markdown(f"**Usuario:** {user_name}")
    
    # Lógica del cronómetro
    usuario_estudiando = st.session_state.idioma_en_curso is not None
    
    # Cada 10 segundos actualizamos el tiempo si hay una sesión activa
    if usuario_estudiando:
        tiempo_inicio_dt = parse_datetime(st.session_state.tiempo_inicio_idiomas)
        if tiempo_inicio_dt:
            tiempo_transcurrido = _argentina_now_global() - tiempo_inicio_dt
            tiempo_actual_sesion = int(tiempo_transcurrido.total_seconds())
            
            # El tiempo total es el acumulado inicial + el tiempo transcurrido en esta sesión
            tiempo_mostrar = st.session_state.tiempo_actual_idiomas + tiempo_actual_sesion
            
            st.header(f"Estudiando {st.session_state.idioma_en_curso}...")
            st.subheader(f"⏱️ {segundos_a_hms(tiempo_mostrar)}")
        
    
    # Obtener el tiempo actual de todos los idiomas del usuario
    current_times = get_user_current_status(USUARIO_ACTUAL)
    
    # Mostrar la interfaz para cada idioma
    for idioma_key, config in USERS[USUARIO_ACTUAL].items():
        if idioma_key == 'name':
            continue
            
        idioma = config["name"]
        tiempo_acumulado_seg = current_times.get(idioma_key, 0)
        tiempo_acumulado_hms = segundos_a_hms(tiempo_acumulado_seg)
        
        col1, col2 = st.columns([1, 4])
        
        with col1:
            st.subheader(idioma)
            st.markdown(f"**Total:** {tiempo_acumulado_hms}")
            
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
                
            # Formulario de corrección (igual que app_estudio)
            with st.expander(f"Corregir tiempo de {idioma}"):
                
                # Función para manejar la corrección
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
                        
                        # Escribir el nuevo total en la celda de tiempo (ej: C2)
                        time_cell_for_row = USERS[USUARIO_ACTUAL][idioma_key_param]["time"]
                        batch_write([(time_cell_for_row, hhmmss)])
                        st.success("Tiempo corregido correctamente.")
                    except Exception as e:
                        st.error(f"Error al corregir el tiempo: {e}")
                    finally:
                        # Forzamos la recarga de los datos
                        get_time_sheet.clear() 
                        pedir_rerun()
                
                # Input de corrección
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

    # Si está estudiando, forzar un re-run cada 10 segundos para actualizar el cronómetro
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