import re
import json
import time
import requests # Mantenido para Anki
from datetime import datetime, date, timedelta, time as dt_time
import streamlit as st
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from requests.exceptions import RequestException
import math

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

def get_argentina_timezone():
    """Retorna el objeto de zona horaria de Argentina."""
    if _HAS_ZONEINFO:
        return ZoneInfo("America/Argentina/Buenos_Aires")
    elif pytz:
        return pytz.timezone("America/Argentina/Buenos_Aires")
    else:
        # Fallback si no hay soporte de timezone avanzado
        return None

def _argentina_now_global():
    """Retorna la hora actual de Argentina con manejo de zona horaria."""
    tz = get_argentina_timezone()
    if tz:
        return datetime.now(tz)
    else:
        # Si no hay soporte de timezone, usar UTC o datetime.now() sin tz
        return datetime.now()

# ------------------ CONSTANTES Y ESTRUCTURAS ------------------

# Estos son rangos fijos de la hoja de cálculo donde se almacenan los tiempos por día
# La fila real se calcula dinámicamente con get_time_row()
FILA_BASE = 170
FECHA_BASE = date(2025, 12, 2)
SHEET_FACUNDO = "F. Idiomas"
SHEET_IVAN = "I. Idiomas"
SHEET_MARCAS = "marcas"
TIME_ROW = 1 # Fila en la hoja 'marcas' para la data de tiempos (si se necesita, sino se puede omitir)


# Estructura de usuarios y materias con sus respectivos rangos en Google Sheets
USERS = {
    "Facundo": {
        "Inglés": {"time": f"'{SHEET_FACUNDO}'!B{{}}", "est": f"'{SHEET_MARCAS}'!G{{}}"},
        "Portugués": {"time": f"'{SHEET_FACUNDO}'!C{{}}", "est": f"'{SHEET_MARCAS}'!H{{}}"},
    },
    "Iván": {
        "Inglés": {"time": f"'{SHEET_IVAN}'!B{{}}", "est": f"'{SHEET_MARCAS}'!I{{}}"},
        "Japonés": {"time": f"'{SHEET_IVAN}'!C{{}}", "est": f"'{SHEET_MARCAS}'!J{{}}"},
    }
}

# ------------------ FIREBASE GOOGLE SHEETS API ------------------

def init_sheets_service():
    """Inicializa la sesión autenticada con Google Sheets."""
    try:
        # Carga la configuración de Firebase/Google Sheets desde st.secrets
        creds_json = st.secrets["service_account"]
        creds = service_account.Credentials.from_service_account_info(creds_json)
        
        # Configura el alcance para Google Sheets
        scoped_creds = creds.with_scopes([
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ])
        
        # Autoriza la sesión de requests
        session = AuthorizedSession(scoped_creds)
        return session
    except Exception as e:
        st.error(f"Error al inicializar el servicio de Google Sheets: {e}")
        return None

@st.cache_resource
def get_sheets_session():
    """Retorna la sesión de Google Sheets (cacheada)."""
    return init_sheets_service()

def sheets_batch_get(spreadsheet_id, ranges):
    """Obtiene datos de varios rangos en una sola llamada batch."""
    session = get_sheets_session()
    if not session: return None
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values:batchGet?ranges={','.join(ranges)}"
    try:
        response = session.get(url)
        response.raise_for_status() 
        return response.json()
    except RequestException as e:
        st.error(f"Error al obtener datos de Google Sheets: {e}")
        return None
    except Exception as e:
        st.error(f"Error desconocido al obtener datos: {e}")
        return None

def batch_write(updates):
    """Escribe datos en múltiples celdas de Google Sheets en una sola llamada batch."""
    session = get_sheets_session()
    if not session: return False
    
    value_input_option = "USER_ENTERED"
    data = []
    for range_name, value in updates:
        data.append({
            "range": range_name,
            "values": [[value]]
        })

    body = {
        "value_input_option": value_input_option,
        "data": data
    }
    
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{st.secrets['sheet_id']}/values:batchUpdate"
    try:
        response = session.post(url, json=body)
        response.raise_for_status() 
        return True
    except RequestException as e:
        st.error(f"Error al escribir en Google Sheets: {e}")
        return False
    except Exception as e:
        st.error(f"Error desconocido al escribir datos: {e}")
        return False

# ------------------ HELPERS DE TIEMPO ------------------

def get_time_row(fecha_actual=None):
    """Calcula la fila de la hoja de cálculo correspondiente a la fecha actual."""
    if fecha_actual is None:
        fecha_actual = _argentina_now_global().date()
    
    delta = fecha_actual - FECHA_BASE
    # FILA_BASE es la fila en la hoja de cálculo. delta.days son los días transcurridos.
    return FILA_BASE + delta.days

def replace_row_in_range(range_template, row):
    """Reemplaza el placeholder {} con el número de fila."""
    return range_template.format(row)

def hms_a_segundos(hms_str):
    """Convierte HH:MM:SS a segundos totales."""
    if not hms_str:
        return 0
    
    parts = list(map(int, hms_str.split(':')))
    
    # Asume HH:MM:SS, MM:SS, o S
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, m, s = 0, parts[0], parts[1]
    elif len(parts) == 1:
        h, m, s = 0, 0, parts[0]
    else:
        return 0
        
    return h * 3600 + m * 60 + s

def segundos_a_hms(segundos):
    """Convierte segundos totales a HH:MM:SS."""
    if segundos < 0:
        segundos = 0
    segundos = int(segundos)
    h = segundos // 3600
    m = (segundos % 3600) // 60
    s = segundos % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def parse_float_or_zero(value):
    """Intenta parsear un float o retorna 0.0 si falla."""
    try:
        return float(str(value).replace(',', '.'))
    except (ValueError, TypeError):
        return 0.0

def pedir_rerun():
    """Fuerza un re-ejecución del script de Streamlit."""
    raise st.runtime.scriptrunner.RerunException(st.runtime.scriptrunner.RerunData(None))

def sanitize_key(text):
    """Limpia texto para usarlo como clave única."""
    return re.sub(r'[^a-zA-Z0-9_]', '', text)

# ------------------ FUNCIONES DE ANKI ------------------

@st.cache_data(ttl=300) # Cachear por 5 minutos
def fetch_anki_stats(USUARIO_ACTUAL):
    """
    Obtiene las estadísticas de tarjetas inmaduras y maduras de Anki para el usuario.
    Se conecta a un servidor local de Anki con la API de AnkiConnect.
    """
    if USUARIO_ACTUAL == "Facundo":
        port = 8766
    elif USUARIO_ACTUAL == "Iván":
        port = 8765
    else:
        return None

    try:
        url = f"http://127.0.0.1:{port}"
        payload = {
            "action": "deckNames",
            "version": 6
        }
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()

        deck_names = response.json().get('result', [])
        
        # Filtramos solo los mazos de idiomas
        if USUARIO_ACTUAL == "Facundo":
            target_decks = ["Inglés", "Portugués"]
        else: # Iván
            target_decks = ["Japonés", "Inglés"]

        filtered_decks = [name for name in deck_names if any(td in name for td in target_decks)]

        if not filtered_decks:
            return None

        # Obtener datos de revisión
        payload = {
            "action": "getCollectionStats",
            "version": 6
        }
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        collection_stats = response.json().get('result', {}).get('misc', {})
        
        # Obtener información de tarjetas
        payload = {
            "action": "getDeckNamesAndIds",
            "version": 6
        }
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        deck_info = response.json().get('result', {})
        
        deck_ids = [deck_info[d] for d in filtered_decks if d in deck_info]

        if not deck_ids:
            return None
            
        # Contar tarjetas por ID de mazo
        cards_data = {
            "mature_count": 0,
            "young_count": 0,
            "other_count": 0,
            "reviews_today": collection_stats.get("reviewedToday", 0)
        }
        
        for deck_id in deck_ids:
            # Consulta para contar tarjetas maduras (intervalo >= 21 días = 1814400 segundos)
            query_mature = f'deck:{deck_id} prop:ivl>=21 is:review'
            # Consulta para contar tarjetas inmaduras (intervalo < 21 días)
            query_young = f'deck:{deck_id} prop:ivl<21 is:review'
            # Consulta para contar tarjetas nuevas (no revisadas)
            query_new = f'deck:{deck_id} is:new'

            for count_type, query in [("mature_count", query_mature), ("young_count", query_young), ("other_count", query_new)]:
                payload = {
                    "action": "findCards",
                    "version": 6,
                    "params": {"query": query}
                }
                response = requests.post(url, json=payload, timeout=5)
                response.raise_for_status()
                card_ids = response.json().get('result', [])
                cards_data[count_type] += len(card_ids)

        # Si el usuario es Facundo, agregamos el mazo "Facu::Memrise::Español" a los "otros"
        if USUARIO_ACTUAL == "Facundo":
            query_spanish = 'deck:"Facu::Memrise::Español"'
            payload = {
                "action": "findCards",
                "version": 6,
                "params": {"query": query_spanish}
            }
            response = requests.post(url, json=payload, timeout=5)
            response.raise_for_status()
            card_ids = response.json().get('result', [])
            cards_data["other_count"] += len(card_ids)
        
        return cards_data

    except requests.exceptions.Timeout:
        st.warning(f"AnkiConnect no responde en el puerto {port} (Timeout).")
        return None
    except requests.exceptions.ConnectionError:
        st.warning(f"AnkiConnect no está corriendo en el puerto {port}. Inicia Anki.")
        return None
    except Exception as e:
        st.error(f"Error desconocido al obtener stats de Anki: {e}")
        return None

# ------------------ FUNCIONES DE ESTADO Y CARGA ------------------

@st.cache_data()
def cargar_datos_unificados():
    """
    Carga todos los datos necesarios de la planilla de cálculo de una sola vez.
    (Solo datos de tiempos y estado de materias).
    """
    all_ranges = []
    mapa_indices = {"materias": {}}
    idx = 0
    
    # 1. Rangos de materias
    for user, materias in USERS.items():
        for m, info in materias.items():
            # Estado (est)
            all_ranges.append(info["est"].format(TIME_ROW)); mapa_indices["materias"][(user, m, "est")] = idx; idx += 1
            # Tiempo (time)
            all_ranges.append(info["time"].format(get_time_row())); mapa_indices["materias"][(user, m, "time")] = idx; idx += 1
            
    # La fila del tiempo diario (get_time_row()) se calcula en cada ejecución
    # La fila del estado de la materia (TIME_ROW=1) es fija

    res = sheets_batch_get(st.secrets["sheet_id"], all_ranges)
    if res is None:
        return {"users_data": {u: {"estado": {}, "tiempos": {}, "inicio_dt": None, "materia_activa": None} for u in USERS}}

    values = res.get("valueRanges", [])
    
    def get_val(i, default=""):
        """Obtiene el valor de un índice, manejando celdas vacías."""
        try:
            val = values[i]["values"][0][0]
            # Si el valor es de tiempo (Ej: 0.5 o 0.25), lo pasamos a string
            if isinstance(val, (int, float)):
                # La API a veces devuelve tiempo como decimal. Lo dejamos como string para manejarlo como HH:MM:SS
                return str(val)
            return val
        except (IndexError, KeyError):
            return default

    # 1. Procesar datos de materias (estado y tiempos)
    data_usuarios = {u: {"estado": {}, "tiempos": {}, "inicio_dt": None, "materia_activa": None} for u in USERS}
    materia_en_curso = None
    inicio_dt = None

    for user in USERS:
        for materia_key in USERS[user]:
            # Estado (est)
            est_idx = mapa_indices["materias"][(user, materia_key, "est")]
            est_val = get_val(est_idx, "")
            
            # Tiempo (time)
            time_idx = mapa_indices["materias"][(user, materia_key, "time")]
            time_val = get_val(time_idx, "00:00:00")
            
            data_usuarios[user]["estado"][materia_key] = est_val
            data_usuarios[user]["tiempos"][materia_key] = time_val

            # Determinar si la materia está en curso
            if est_val.startswith("ESTUDIANDO_"):
                materia_en_curso = materia_key
                try:
                    timestamp = float(est_val.split("_")[1])
                    # La marca de tiempo guardada es UTC, la cargamos como datetime y la convertimos a la TZ de Arg
                    tz = get_argentina_timezone()
                    inicio_dt = datetime.fromtimestamp(timestamp, tz)
                except (ValueError, IndexError):
                    inicio_dt = None # En caso de estado malformado

    # Sincronizar estado en sesión si hay usuario seleccionado
    if "usuario_seleccionado" in st.session_state:
        st.session_state["materia_activa"] = materia_en_curso
        st.session_state["inicio_dt"] = inicio_dt

    return {
        "users_data": data_usuarios,
    }


# ------------------ CALLBACKS DE STREAMLIT ------------------

def start_materia_callback(materia_key):
    """
    Callback para iniciar el cronometraje de una materia.
    Actualiza el estado en Google Sheets y en la sesión de Streamlit.
    """
    USUARIO_ACTUAL = st.session_state["usuario_seleccionado"]
    
    # 1. Detener cualquier otra materia en curso (por seguridad)
    materia_activa = st.session_state.get("materia_activa")
    if materia_activa:
        # Se guarda el tiempo de la materia que estaba corriendo
        stop_materia_callback(materia_activa) # Llama a la función de detener para que guarde el tiempo
        st.toast(f"🛑 Se detuvo: {materia_activa}")

    # 2. Iniciar la nueva materia
    try:
        # Obtener el rango de estado para la materia
        est_range_for_row = replace_row_in_range(USERS[USUARIO_ACTUAL][materia_key]["est"], TIME_ROW)
        
        # Guardar el timestamp actual (UTC) como parte del estado
        current_timestamp = _argentina_now_global().timestamp()
        new_state = f"ESTUDIANDO_{current_timestamp}"
        
        if batch_write([(est_range_for_row, new_state)]):
            st.session_state["materia_activa"] = materia_key
            st.session_state["inicio_dt"] = _argentina_now_global()
            st.toast(f"▶️ Iniciando: {materia_key}")
        else:
            st.error(f"❌ Error al iniciar la materia: {materia_key}")
            
    except Exception as e:
        st.error(f"Error al iniciar el cronometraje: {e}")
    finally:
        # Forzar un rerun para actualizar la UI
        pedir_rerun()


def stop_materia_callback(materia_key):
    """
    Callback para detener el cronometraje de una materia.
    Calcula el tiempo transcurrido y lo suma al total en Google Sheets.
    """
    USUARIO_ACTUAL = st.session_state["usuario_seleccionado"]
    inicio_dt = st.session_state.get("inicio_dt")
    
    if inicio_dt is None or st.session_state.get("materia_activa") != materia_key:
        # Esto no debería pasar si se llama correctamente
        st.error(f"Error: La materia {materia_key} no estaba activa o el tiempo de inicio es nulo.")
        return

    # 1. Calcular tiempo transcurrido
    tiempo_transcurrido = int((_argentina_now_global() - inicio_dt).total_seconds())

    # 2. Obtener el tiempo total actual
    datos_globales = cargar_datos_unificados()
    datos_usuario = datos_globales["users_data"][USUARIO_ACTUAL]
    tiempo_actual_hms = datos_usuario["tiempos"][materia_key]
    tiempo_actual_seg = hms_a_segundos(tiempo_actual_hms)
    
    # 3. Sumar tiempo
    nuevo_tiempo_seg = tiempo_actual_seg + tiempo_transcurrido
    nuevo_tiempo_hms = segundos_a_hms(nuevo_tiempo_seg)
    
    # 4. Obtener rangos para escribir
    target_row = get_time_row()
    time_cell_for_row = replace_row_in_range(USERS[USUARIO_ACTUAL][materia_key]["time"], target_row)
    est_range_for_row = replace_row_in_range(USERS[USUARIO_ACTUAL][materia_key]["est"], TIME_ROW)
    
    # 5. Escribir nuevos valores
    if batch_write([(time_cell_for_row, nuevo_tiempo_hms), (est_range_for_row, "") ]):
        st.session_state["materia_activa"] = None
        st.session_state["inicio_dt"] = None
        st.toast(f"✅ Detenido: {materia_key} (+{segundos_a_hms(tiempo_transcurrido)})")
    else:
        st.error(f"❌ Error al guardar el tiempo para {materia_key}")
    
    # Forzar un rerun para actualizar la UI y recargar datos
    pedir_rerun()


# ------------------ UI Y MAIN ------------------

def cargar_estilos():
    st.markdown("""
        <style>
        /* Estilos generales para Streamlit */
        html, body, [class*="css"] { font-size: 18px !important; }
        h1 { font-size: 2.5rem !important; }
        h2 { font-size: 2rem !important; }
        h3 { font-size: 1.5rem !important; }

        /* Estilo de la tarjeta de materia */
        .materia-card {
            background-color: #262730;
            border: 1px solid #464b5c;
            padding: 20px;
            border-radius: 15px;
            margin-bottom: 20px;
            transition: all 0.3s ease;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        .materia-card:hover {
            border-color: #38761d;
            box-shadow: 0 6px 10px rgba(0, 0, 0, 0.2);
        }

        /* Estilo para el cronómetro activo */
        .card-active {
            background-color: #38761d30; /* Fondo más oscuro y con verde */
            border-color: #6AA84F; /* Borde verde */
            animation: pulse-border 1.5s infinite alternate;
        }

        /* Animación para el borde de la tarjeta activa */
        @keyframes pulse-border {
            from { border-color: #6AA84F; }
            to { border-color: #93C47D; }
        }

        /* Estilo del botón */
        .stButton>button {
            width: 100%;
            height: 50px;
            font-size: 1.1rem;
            border-radius: 10px;
            border: none;
            color: white;
            transition: background-color 0.3s, transform 0.1s;
        }
        .stButton>button:hover {
            transform: translateY(-2px);
        }
        
        /* Botón de Iniciar */
        .stButton>button[kind="start"] {
            background-color: #6AA84F;
        }
        .stButton>button[kind="start"]:hover {
            background-color: #93C47D;
        }

        /* Botón de Detener */
        .stButton>button[kind="stop"] {
            background-color: #CC0000;
        }
        .stButton>button[kind="stop"]:hover {
            background-color: #FF6666;
        }
        
        /* Contenedor del reloj */
        .reloj-display {
            font-size: 2.2rem;
            font-weight: bold;
            text-align: center;
            margin-top: 10px;
            color: #6AA84F;
        }

        /* Color para las estadísticas de Anki */
        .anki-mature { color: #31A354; font-weight: bold; }
        .anki-young { color: #74C476; font-weight: bold; }
        .anki-other { color: #BDBDBD; font-weight: bold; }

        </style>
        """, unsafe_allow_html=True)


def main():
    cargar_estilos()
    st.title("⏱️ Cronómetro de Idiomas")

    # Inicialización de estado de sesión
    if "usuario_seleccionado" not in st.session_state:
        st.session_state["usuario_seleccionado"] = None
    if "materia_activa" not in st.session_state:
        st.session_state["materia_activa"] = None
    if "inicio_dt" not in st.session_state:
        st.session_state["inicio_dt"] = None

    # Selector de usuario en la barra lateral
    st.sidebar.title("Selecciona Usuario")
    opciones_usuario = list(USERS.keys())
    
    # Usar un selectbox para la selección de usuario
    user_selection = st.sidebar.selectbox(
        "¿Quién está usando la app?",
        options=[""] + opciones_usuario,
        index=0,
        format_func=lambda x: x if x else "Elige un usuario"
    )

    if user_selection and user_selection != st.session_state["usuario_seleccionado"]:
        st.session_state["usuario_seleccionado"] = user_selection
        # Forzar recarga para que el estado se actualice
        pedir_rerun()

    if not st.session_state["usuario_seleccionado"]:
        st.info("Por favor, selecciona un usuario en el menú lateral para comenzar a cronometrar.")
        st.stop()

    # --- Carga de datos ---
    # La carga de datos se realiza en cada ejecución para obtener el estado actual
    datos_globales = cargar_datos_unificados()
    datos = datos_globales["users_data"]
    
    USUARIO_ACTUAL = st.session_state["usuario_seleccionado"]
    
    # La data de un solo usuario
    user_data = datos[USUARIO_ACTUAL]
    
    # Determinar estado de estudio
    usuario_estudiando = st.session_state["materia_activa"] is not None
    materia_en_curso = st.session_state["materia_activa"]
    inicio_dt = st.session_state["inicio_dt"]

    st.header(f"Estudio de {USUARIO_ACTUAL}")

    while True:
        tiempo_anadido_seg = 0
        if usuario_estudiando and inicio_dt is not None:
            # Calcular tiempo transcurrido desde el inicio_dt
            tiempo_anadido_seg = int((_argentina_now_global() - inicio_dt).total_seconds())

            # ------------------ ANKI STATS (MANTENIDO) ------------------
            anki_data = fetch_anki_stats(USUARIO_ACTUAL)
            C_MATURE, C_YOUNG, C_OTHER = "#31A354", "#74C476", "#BDBDBD" # Colores definidos en CSS
            
            if anki_data:
                st.subheader("📚 Anki Stats")
                reviews_today = anki_data['reviews_today']
                
                # Resumen de tarjetas
                total_cards = anki_data['mature_count'] + anki_data['young_count'] + anki_data['other_count']
                
                st.markdown(f"**🔄 Hoy:** **{reviews_today}** repeticiones")
                
                col_m, col_y, col_o = st.columns(3)
                
                with col_m:
                    st.markdown(f"**Maduras:** <span class='anki-mature'>{anki_data['mature_count']}</span>", unsafe_allow_html=True)
                with col_y:
                    st.markdown(f"**Inmaduras:** <span class='anki-young'>{anki_data['young_count']}</span>", unsafe_allow_html=True)
                with col_o:
                    st.markdown(f"**Otras:** <span class='anki-other'>{anki_data['other_count']}</span>", unsafe_allow_html=True)

                if total_cards > 0:
                    # Crear gráfico de barras para el balance de tarjetas
                    data = [
                        {"category": "Maduras", "count": anki_data['mature_count'], "color": C_MATURE},
                        {"category": "Inmaduras", "count": anki_data['young_count'], "color": C_YOUNG},
                        {"category": "Otras/Nuevas", "count": anki_data['other_count'], "color": C_OTHER}
                    ]
                    
                    st.bar_chart(
                        data,
                        x="category",
                        y="count",
                        color="color",
                        use_container_width=True
                    )
            # ------------------------------------------------------------


        # --- Renderizar Materias ---
        st.subheader("Tiempo Diario Registrado")
        materias_keys = list(USERS[USUARIO_ACTUAL].keys())
        # Usamos columnas fluidas (auto) para que se ajusten al contenido
        cols = st.columns(len(materias_keys)) 

        for i, materia_key in enumerate(materias_keys):
            with cols[i]:
                materia = materia_key
                tiempo_total_hms = user_data["tiempos"][materia_key]
                en_curso = materia_key == materia_en_curso

                # Aplicar la clase 'card-active' si está en curso
                card_class = "materia-card card-active" if en_curso else "materia-card"

                with st.container():
                    st.markdown(f'<div class="{card_class}">', unsafe_allow_html=True)
                    
                    st.markdown(f"#### {materia}")
                    
                    # Mostrar el tiempo total registrado
                    st.markdown(f"**Total:** `{tiempo_total_hms}`")
                    
                    # Mostrar el cronómetro si está activo
                    if en_curso:
                        tiempo_parcial_hms = segundos_a_hms(tiempo_anadido_seg)
                        st.markdown(f"<p class='reloj-display'>{tiempo_parcial_hms}</p>", unsafe_allow_html=True)
                        
                        # Botón de Detener
                        st.button(
                            "Detener",
                            key=f"stop_{sanitize_key(materia)}",
                            on_click=stop_materia_callback,
                            args=(materia,),
                            use_container_width=True,
                            type="primary",
                            help="Guarda el tiempo transcurrido y detiene el cronómetro.",
                            # Usar un 'kind' custom para el estilo CSS
                            kwargs={"kind": "stop"} 
                        )
                    else:
                        # Botón de Iniciar
                        disabled = usuario_estudiando and not en_curso
                        st.button(
                            "Iniciar",
                            key=f"start_{sanitize_key(materia)}",
                            on_click=start_materia_callback,
                            args=(materia,),
                            use_container_width=True,
                            disabled=disabled,
                            type="secondary",
                            help="Inicia el cronometraje para esta materia.",
                            kwargs={"kind": "start"}
                        )
                    
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # --- Corrección Manual de Tiempo ---
                    with st.expander("Corregir Tiempo"):
                        st.markdown("Reemplaza el tiempo total del día con el valor ingresado (`HH:MM:SS`).")
                        
                        val_actual = user_data["tiempos"][materia_key]
                        new_val = st.text_input("Tiempo Actual (`HH:MM:SS`)", value=val_actual, key=f"input_{sanitize_key(materia)}")
                        
                        def save_correction_callback(materia_key_to_correct):
                            try:
                                # Asegurar el formato HH:MM:SS
                                val = st.session_state[f"input_{sanitize_key(materia_key_to_correct)}"]
                                if not re.match(r"^\d{1,2}:\d{2}:\d{2}$", val):
                                    raise ValueError("Formato de tiempo inválido. Usa HH:MM:SS.")
                                
                                # Convertir a segundos para validación y volver a HMS
                                segs = hms_a_segundos(val)
                                hhmmss = segundos_a_hms(segs)
                                
                                target_row = get_time_row()  # fila actual
                                time_cell_for_row = replace_row_in_range(USERS[USUARIO_ACTUAL][materia_key_to_correct]["time"], target_row)
                                
                                # Escribir el nuevo tiempo
                                if batch_write([(time_cell_for_row, hhmmss)]):
                                    st.success("Tiempo corregido correctamente.")
                                else:
                                    st.error("Error al escribir la corrección.")
                                    
                            except Exception as e:
                                st.error(f"Error al corregir el tiempo: {e}")
                            finally:
                                # Forzar recarga para ver el tiempo actualizado
                                pedir_rerun()

                        if en_curso or usuario_estudiando:
                            st.info("⛔ No podés corregir el tiempo mientras estás estudiando.")
                        else:
                            # Nota: El botón llama al callback para guardar el input
                            st.button("Guardar Corrección", key=f"save_{sanitize_key(materia)}", on_click=save_correction_callback, args=(materia,))


        if not usuario_estudiando:
            st.stop() # Detener la ejecución si no hay cronómetro activo

        # Si el cronómetro está activo, esperar 10 segundos y forzar un rerun para actualizar la UI
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
            pedir_rerun()