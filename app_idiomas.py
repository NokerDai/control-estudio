import re
import time
from datetime import datetime, date
import streamlit as st
from google.oauth2 import service_account
from requests.exceptions import RequestException

# Librerías de Google Sheets
import gspread

# ------------------ TIMEZONE HELPERS ------------------
# Importación condicional de zoneinfo (Python >= 3.9) o pytz (fallback)
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

TIMEZONE = "America/Argentina/Buenos_Aires" # Zona horaria a usar

def cargar_estilos():
    # Estilos CSS para mejorar la apariencia en Streamlit
    st.markdown("""
        <style>
        html, body, [class*="css"] { font-size: 18px !important; }
        h1 { font-size: 2.5rem !important; }
        h2 { font-size: 2rem !important; }
        h3 { font-size: 1.5rem !important; }

        /* Estilo de la tarjeta (uso de border=True en container) */
        
        /* Estilo para el botón de empezar/terminar */
        .stButton>button {
            border-radius: 10px;
            font-size: 1.2em;
            font-weight: bold;
            transition: all 0.3s ease;
        }

        /* Colores de los botones */
        .btn-start button { background-color: #4CAF50 !important; color: white !important; border-color: #4CAF50 !important; }
        .btn-stop button { background-color: #F44366 !important; color: white !important; border-color: #F44366 !important; }
        .btn-pause button { background-color: #FFC107 !important; color: black !important; border-color: #FFC107 !important; }

        .stAlert { border-radius: 10px; }
        </style>
    """, unsafe_allow_html=True)

# ------------------ TIMEZONE HELPERS ------------------

def get_today_argentina():
    """Obtiene la fecha de hoy en la zona horaria de Argentina."""
    now = datetime.now()
    if _HAS_ZONEINFO:
        try:
            return now.astimezone(ZoneInfo(TIMEZONE)).date()
        except Exception:
            pass # Fallback
    
    # Fallback con pytz si está disponible
    if pytz:
        try:
            tz = pytz.timezone(TIMEZONE)
            return tz.localize(now).date()
        except Exception:
            pass
            
    # Último fallback (hora local sin garantizar zona horaria)
    return now.date()


# ------------------ CONSTANTES ------------------

# Google Sheets Configuración (de secrets)
SHEET_ID = st.secrets.get("SHEET_ID")
CREDS_JSON = st.secrets.get("gcp_service_account")

# Usuario actual (Se obtiene dinámicamente)
def get_current_user():
    """Obtiene el usuario actual de la sesión, por defecto 'Agustin'."""
    # Si la app principal (app.py) establece un 'current_user' lo usamos, sino 'Agustin'.
    if 'current_user' not in st.session_state:
        st.session_state.current_user = "Agustin"
    return st.session_state.current_user
    

# Materias anidadas por categoría
# "Nombre_Categoria": {
#   "Nombre_Idioma": {
#     "time": "'Hoja1'!<columna>", # Rango de la columna para tiempo diario (Ej: C, E, G, I...)
#     "total": "'Hoja1'!<celda>"    # Celda del tiempo total (Ej: D3, F3, H3, J3...)
#   }
# }
MATERIAS_IDIOMAS = {
    "F. Idiomas": {
        "Inglés": {
            "time": "'Hoja1'!C",  # Columna C para tiempo diario
            "total": "'Hoja1'!D3" # Celda D3 para total acumulado
        },
        "Alemán": {
            "time": "'Hoja1'!E",  # Columna E para tiempo diario
            "total": "'Hoja1'!F3" # Celda F3 para total acumulado
        }
        # Agregar más idiomas en Fundamentos según sea necesario
    },
    "I. Idiomas": {
        "Japonés": {
            "time": "'Hoja1'!G",  # Columna G para tiempo diario
            "total": "'Hoja1'!H3" # Celda H3 para total acumulado
        },
        "Chino": {
            "time": "'Hoja1'!I",  # Columna I para tiempo diario
            "total": "'Hoja1'!J3" # Celda J3 para total acumulado
        }
        # Agregar más idiomas en Inmersión según sea necesario
    }
}

# La lógica simplifica el acceso a las celdas usando solo el nombre del idioma
# Esta función combina la configuración de usuario y la de idiomas para facilitar el acceso
def get_user_language_config():
    """Combina todas las configuraciones de idiomas en un diccionario plano 'Idioma': {time: ..., total: ...}
       para el usuario actual. Asume que MATERIAS_IDIOMAS es para el usuario 'Agustin'."""
    config = {}
    current_user = get_current_user()

    # Actualmente, MATERIAS_IDIOMAS solo tiene configuración para 'Agustin' de forma implícita.
    if current_user == "Agustin": 
        for category, languages in MATERIAS_IDIOMAS.items():
            for lang, ranges in languages.items():
                # La clave única para el estado de sesión será "Categoría: Idioma"
                full_name = f"{category}: {lang}"
                config[full_name] = ranges
    return config

# FILA DE INICIO PARA EL REGISTRO DIARIO
TIME_RANGE_START_ROW = 170 
START_DATE = date(2024, 1, 1) # Fecha que corresponde a la fila 170 (Día 0 delta)

# ------------------ HELPERS DE GOOGLE SHEETS ------------------

@st.cache_resource(show_spinner="Conectando a Google Sheets...")
def get_client():
    """Inicializa y devuelve el cliente de gspread."""
    if not SHEET_ID or not CREDS_JSON:
        st.error("Error de configuración: SHEET_ID o gcp_service_account no encontrados en secrets.")
        return None
        
    try:
        creds = service_account.Credentials.from_service_account_info(
            CREDS_JSON,
            scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        )
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Error al inicializar Google Sheets: {e}")
        return None

@st.cache_resource(ttl=3600)
def get_worksheet(client):
    """Obtiene la hoja de cálculo por ID."""
    if not client: return None
    try:
        spreadsheet = client.open_by_key(SHEET_ID)
        worksheet = spreadsheet.worksheet("Hoja1") # Asumiendo que usamos "Hoja1"
        return worksheet
    except Exception as e:
        st.error(f"Error al abrir la hoja de cálculo (ID: {SHEET_ID}): {e}")
        return None

def batch_read(ranges):
    """Lee un conjunto de rangos."""
    client = get_client()
    if not client: return []
    
    try:
        # Usamos el método get_range de gspread que usa la API v4
        result = client.open_by_key(SHEET_ID).sheet1.get_values(ranges)
        # El resultado es una lista de listas, tomamos el primer elemento de cada sublista (el valor)
        return [item[0] if item else '' for item in result]
    except Exception as e:
        st.error(f"Error al leer rangos {ranges}: {e}")
        return [''] * len(ranges) # Devolvemos vacíos para evitar rotura

def batch_write(updates):
    """Escribe un conjunto de valores en pares (rango, valor)."""
    client = get_client()
    if not client: return

    updates_list = [
        {
            'range': range_str,
            'values': [[value]]
        } for range_str, value in updates
    ]
    
    try:
        worksheet = client.open_by_key(SHEET_ID).worksheet("Hoja1")
        # Usa el método spreadheets().values().batchUpdate de la API v4
        worksheet.batch_update(updates_list, value_input_option='USER_ENTERED')
    except Exception as e:
        st.error(f"Error al escribir en Google Sheets: {e}")
        # No propagamos, solo mostramos el error

def replace_row_in_range(range_template, row_number):
    """Reemplaza el marcador de rango con el número de fila."""
    # range_template es algo como "'Hoja1'!C"
    return range_template + str(row_number)


def get_time_row():
    """Calcula la fila objetivo para el día de hoy, a partir de TIME_RANGE_START_ROW."""
    today_arg = get_today_argentina()
    delta = today_arg - START_DATE
    # La fila 170 corresponde al día 0 de la delta (delta.days = 0)
    target_row = delta.days + TIME_RANGE_START_ROW
    return target_row

# ------------------ HELPERS DE TIEMPO ------------------

def hms_a_segundos(hms_str):
    """Convierte HH:MM:SS a segundos."""
    if not hms_str:
        return 0
    
    # Intenta encontrar HH:MM:SS (o H:MM:SS)
    match = re.match(r'(\d+):(\d{2}):(\d{2})', hms_str)
    if match:
        h, m, s = map(int, match.groups())
        return h * 3600 + m * 60 + s
    
    # Intenta encontrar MM:SS (si no hay HH, asume 00:MM:SS)
    match_ms = re.match(r'(\d{1,2}):(\d{2})', hms_str)
    if match_ms:
        m, s = map(int, match_ms.groups())
        return m * 60 + s

    # Si es solo un número (segs)
    try:
        return int(hms_str)
    except ValueError:
        return 0


def segundos_a_hms(total_segundos):
    """Convierte segundos a HH:MM:SS."""
    if total_segundos < 0:
        total_segundos = 0
        
    horas = int(total_segundos // 3600)
    minutos = int((total_segundos % 3600) // 60)
    segundos = int(total_segundos % 60)
    
    return f"{horas:02d}:{minutos:02d}:{segundos:02d}"

# ------------------ LÓGICA DE ESTADO Y CALLBACKS ------------------

def pedir_rerun():
    """Limpia el estado de sesión si se debe recargar la app."""
    # NO borramos los estados de tiempo/total, solo el estado del temporizador
    if 'rerun_pending' not in st.session_state:
        st.session_state.rerun_pending = True
        st.rerun()

def sanitize_key(text):
    """Sanea un string para usar como key de Streamlit."""
    return re.sub(r'[^a-zA-Z0-9_]', '_', text)

def start_study(full_materia_name):
    """Inicia el estudio para la materia dada (Ej: 'F. Idiomas: Inglés')."""
    st.session_state.materia_estudiando = full_materia_name
    st.session_state.start_time = time.time()
    st.session_state.is_paused = False
    st.session_state.pause_time = 0
    pedir_rerun()

def pause_study():
    """Pausa el estudio."""
    if not st.session_state.is_paused:
        st.session_state.is_paused = True
        st.session_state.pause_start = time.time()
    pedir_rerun()

def resume_study():
    """Reanuda el estudio (calcula el tiempo de pausa y lo agrega a pause_time)."""
    if st.session_state.is_paused:
        pause_duration = time.time() - st.session_state.pause_start
        st.session_state.pause_time += pause_duration
        st.session_state.is_paused = False
    pedir_rerun()

def stop_study():
    """Detiene el estudio y guarda el tiempo en Google Sheets."""
    full_materia_name = st.session_state.materia_estudiando
    start_time = st.session_state.start_time
    pause_time = st.session_state.pause_time
    
    # Limpieza inicial de estado para evitar re-entradas
    st.session_state.materia_estudiando = None
    st.session_state.start_time = None
    st.session_state.is_paused = False
    st.session_state.pause_time = 0

    if not full_materia_name:
        st.error("Error: No hay materia en curso para detener.")
        pedir_rerun()
        return

    # Calcula el tiempo total neto
    study_duration = time.time() - start_time - pause_time
    study_duration = max(0, int(study_duration)) # Aseguramos que no sea negativo
    
    # Obtener configuración del idioma (usando la función sin argumentos)
    lang_config = get_user_language_config()
    if full_materia_name not in lang_config:
        st.error(f"Error: Configuración de idioma '{full_materia_name}' no encontrada para el usuario {get_current_user()}.")
        pedir_rerun()
        return

    config = lang_config[full_materia_name]
    daily_range_template = config["time"]
    total_cell = config["total"]

    # 1. Obtener la celda objetivo (diaria)
    target_row = get_time_row()
    daily_cell = replace_row_in_range(daily_range_template, target_row)

    # 2. Leer el tiempo actual (diario y total)
    try:
        ranges = [daily_cell, total_cell]
        daily_hms, total_hms = batch_read(ranges)
    except Exception as e:
        st.error(f"Error de lectura en Sheets antes de guardar: {e}")
        pedir_rerun()
        return

    # 3. Sumar el tiempo de estudio
    daily_segs = hms_a_segundos(daily_hms)
    total_segs = hms_a_segundos(total_hms)
    
    new_daily_segs = daily_segs + study_duration
    new_total_segs = total_segs + study_duration
    
    new_daily_hms = segundos_a_hms(new_daily_segs)
    new_total_hms = segundos_a_hms(new_total_segs)

    # 4. Escribir los nuevos tiempos
    try:
        batch_write([
            (daily_cell, new_daily_hms), # Tiempo diario
            (total_cell, new_total_hms)  # Tiempo total
        ])
        
        st.success(f"Tiempo de **{segundos_a_hms(study_duration)}** guardado para **{full_materia_name}**.")
    except Exception as e:
        st.error(f"Error de escritura en Sheets: {e}")
        
    pedir_rerun()


# ------------------ VISTAS DE PÁGINA ------------------

def display_timer(full_materia_name):
    """Muestra el cronómetro y los botones de control."""
    elapsed_time = time.time() - st.session_state.start_time
    
    is_paused = st.session_state.get("is_paused", False)
    
    if is_paused:
        current_duration = elapsed_time - st.session_state.pause_time
        status_text = "⏸️ PAUSADO"
        control_label = "▶️ Reanudar"
        on_click_action = resume_study
    else:
        current_duration = elapsed_time - st.session_state.pause_time
        status_text = "🔴 EN CURSO"
        control_label = "⏸️ Pausar"
        on_click_action = pause_study

    # Convertir a formato HH:MM:SS
    display_time = segundos_a_hms(int(current_duration))
    
    st.title(full_materia_name)
    st.markdown(f"### {status_text}")
    st.markdown(f"<h1 style='font-size: 5rem; text-align: center; color: #1E90FF;'>{display_time}</h1>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        # Botón de Stop
        st.markdown('<div class="btn-stop">', unsafe_allow_html=True)
        st.button("🛑 Terminar y Guardar", key="stop_btn", on_click=stop_study, use_container_width=True, help="Detiene el estudio y registra el tiempo en la hoja de cálculo.")
        st.markdown('</div>', unsafe_allow_html=True)
    with col2:
        # Botón de control (Pausar/Reanudar)
        st.markdown('<div class="btn-pause">', unsafe_allow_html=True)
        st.button(control_label, key="control_btn", on_click=on_click_action, use_container_width=True, help="Controla el estado del cronómetro.")
        st.markdown('</div>', unsafe_allow_html=True)

# ------------------ PÁGINA PRINCIPAL ------------------

def main():
    """Función principal de la aplicación de idiomas."""
    cargar_estilos()

    # Si hay un estudio en curso, mostrar el temporizador y detener la ejecución
    if st.session_state.get("materia_estudiando"):
        display_timer(st.session_state.materia_estudiando)
        
        # Si no está pausado, recargar cada 10 segundos
        if not st.session_state.get("is_paused", False):
            time.sleep(10)
            st.rerun()
        
        # Si está pausado, no hacemos rerun automático, esperamos acción del usuario
        return

    # Reiniciar estado de rerun_pending si existe
    if 'rerun_pending' in st.session_state:
        del st.session_state.rerun_pending

    st.title("🗣️ Sistema de Registro de Idiomas")
    st.markdown("---")

    # 1. Obtener la configuración plana de los idiomas
    # Ahora llamamos sin argumentos, el usuario se obtiene internamente
    language_config = get_user_language_config()
    
    # 2. Inicializar o cargar datos
    if "data_loaded" not in st.session_state:
        st.session_state.data_loaded = False
        st.session_state.time_data = {} # Almacena {full_materia_name: {daily_hms, total_hms, daily_range, total_range}}
        
    # 3. Si los datos no están cargados, cargarlos de Sheets
    if not st.session_state.data_loaded:
        with st.spinner("Cargando datos de Google Sheets..."):
            
            target_row = get_time_row()
            all_ranges_to_read = []
            
            # Construir la lista de rangos a leer
            for full_name, config in language_config.items():
                daily_range = replace_row_in_range(config["time"], target_row)
                total_range = config["total"]
                
                # Guardamos los rangos para la lectura en lote
                all_ranges_to_read.append(daily_range)
                all_ranges_to_read.append(total_range)
                
                # También pre-inicializamos el estado con los rangos
                st.session_state.time_data[full_name] = {
                    "daily_range": daily_range,
                    "total_range": total_range,
                    "daily_hms": "00:00:00",
                    "total_hms": "00:00:00"
                }

            # Lectura en lote
            try:
                values = batch_read(all_ranges_to_read)
                
                # Asignar los valores leídos al estado
                idx = 0
                for full_name in st.session_state.time_data.keys():
                    st.session_state.time_data[full_name]["daily_hms"] = values[idx] or "00:00:00"
                    st.session_state.time_data[full_name]["total_hms"] = values[idx + 1] or "00:00:00"
                    idx += 2
                    
                st.session_state.data_loaded = True
                st.rerun() # Volvemos a cargar la vista con los datos cargados
                return
                
            except Exception as e:
                st.error(f"No se pudieron cargar los datos de la hoja de cálculo: {e}")
                return

    # 4. VISTA: Mostrar las tarjetas por categoría (F. Idiomas / I. Idiomas)
    st.header(f"Lista de Idiomas a Estudiar para {get_current_user()}")
    
    for category, languages in MATERIAS_IDIOMAS.items():
        st.subheader(f"🌐 {category}")
        
        # Usamos columnas fluidas para mostrar los idiomas dentro de la categoría
        lang_names = list(languages.keys())
        cols = st.columns(len(lang_names) if lang_names else 1)
        
        for i, lang_name in enumerate(lang_names):
            full_materia_name = f"{category}: {lang_name}"
            data = st.session_state.time_data.get(full_materia_name, {})
            
            # Contenedor para cada idioma
            with cols[i].container(border=True): 
                st.markdown(f"**{lang_name}**")
                st.markdown(f"**Total acumulado:** {data.get('total_hms', '00:00:00')}")
                st.markdown(f"**Tiempo hoy:** {data.get('daily_hms', '00:00:00')}")
                
                # Botón de Empezar
                st.markdown('<div class="btn-start">', unsafe_allow_html=True)
                st.button(
                    f"▶️ Empezar {lang_name}", 
                    key=f"start_{sanitize_key(full_materia_name)}", 
                    on_click=start_study, 
                    args=(full_materia_name,), 
                    use_container_width=True
                )
                st.markdown('</div>', unsafe_allow_html=True)
                
                # Formulario de corrección de tiempo
                with st.expander("Corregir tiempo de hoy"):
                    correction_key = f"input_{sanitize_key(full_materia_name)}"
                    
                    # Usamos el tiempo actual como valor por defecto
                    default_value = data.get('daily_hms', '00:00:00')
                    val = st.text_input("HH:MM:SS de corrección:", key=correction_key, value=default_value)
                    
                    # Botón de corrección
                    def save_correction_callback(materia_key_closure):
                        try:
                            val = st.session_state[f"input_{sanitize_key(materia_key_closure)}"]
                            current_data = st.session_state.time_data[materia_key_closure]
                            
                            # 1. Calcular diferencia
                            old_daily_segs = hms_a_segundos(current_data['daily_hms'])
                            new_daily_segs = hms_a_segundos(val)
                            
                            delta_segs = new_daily_segs - old_daily_segs
                            
                            # 2. Corregir tiempo total
                            total_segs = hms_a_segundos(current_data['total_hms'])
                            new_total_segs = total_segs + delta_segs
                            new_total_hms = segundos_a_hms(new_total_segs)

                            # 3. Preparar escritura
                            daily_cell = current_data["daily_range"]
                            total_cell = current_data["total_range"]
                            
                            batch_write([
                                (daily_cell, val),       # Nuevo tiempo diario
                                (total_cell, new_total_hms) # Nuevo tiempo total
                            ])
                            st.success(f"Tiempo de {materia_key_closure} corregido correctamente.")
                            
                            # Forzamos la recarga de datos
                            st.session_state.data_loaded = False 
                            
                        except Exception as e:
                            st.error(f"Error al corregir el tiempo: {e}")
                        finally:
                            pedir_rerun()
                    
                    if st.button("Guardar Corrección", key=f"save_{sanitize_key(full_materia_name)}", on_click=save_correction_callback, args=(full_materia_name,), use_container_width=True):
                        pass # La acción está en on_click
            

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        st.error(f"Error crítico en main(): {e}")
        st.sidebar.error(f"Error crítico: {e}")
        if st.sidebar.button("Reiniciar sesión (limpiar estado)"):
            st.session_state.clear()
            st.rerun()