import re
import json
import time # Importamos 'time' para el sleep en el bucle
from datetime import datetime, date, timedelta, time as dt_time
import streamlit as st
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from requests.exceptions import RequestException
import streamlit.components.v1 as components # Importamos para el widget de Android

# ------------------ CONFIG ------------------
st.set_page_config(page_title="Tiempo de Estudio", page_icon="⏳", layout="centered")

# ------------------ STYLES ------------------
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

# ------------------ RERUN HELPER (recomendado para callbacks) ------------------
def pedir_rerun():
    """Establece un flag en session_state para que el rerun se haga fuera del callback."""
    st.session_state["_do_rerun"] = True

# ------------------ GOOGLE SHEETS SESSION ------------------
@st.cache_resource
def get_sheets_session():
    try:
        key_dict = json.loads(st.secrets["textkey"])
    except Exception as e:
        st.error(f"Error leyendo st.secrets['textkey']: {e}")
        st.stop()
    try:
        creds = service_account.Credentials.from_service_account_info(
            key_dict,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        return AuthorizedSession(creds)
    except Exception as e:
        st.error(f"Error creando credenciales: {e}")
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

# ------------------ CONSTANTES Y ESTRUCTURAS ------------------
FILA_BASE = 170
FECHA_BASE = date(2025, 12, 2)
SHEET_FACUNDO = "F. Economía"
SHEET_IVAN = "I. Física"
SHEET_MARCAS = "marcas"

def get_time_row():
    hoy = _argentina_now_global().date()
    delta = (hoy - FECHA_BASE).days
    return FILA_BASE + delta

TIME_ROW = get_time_row()
MARCAS_ROW = 2
WEEK_RANGE = f"'{SHEET_MARCAS}'!R{TIME_ROW}"

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

# ------------------ CARGA UNIFICADA (cacheada) ------------------
@st.cache_data()
def cargar_datos_unificados():
    """Carga todos los datos necesarios de Google Sheets (solo al inicio o tras acción de botón)."""
    all_ranges = []
    mapa_indices = {"materias": {}, "rates": {}, "objs": {}, "week": None}
    idx = 0
    for user, materias in USERS.items():
        for m, info in materias.items():
            # Estado (Marca de inicio)
            all_ranges.append(info["est"]); mapa_indices["materias"][(user, m, "est")] = idx; idx += 1
            # Tiempo acumulado
            all_ranges.append(info["time"]); mapa_indices["materias"][(user, m, "time")] = idx; idx += 1
    all_ranges.append(RANGO_RATE_FACU); mapa_indices["rates"]["Facundo"] = idx; idx += 1
    all_ranges.append(RANGO_RATE_IVAN); mapa_indices["rates"]["Iván"] = idx; idx += 1
    all_ranges.append(RANGO_OBJ_FACU); mapa_indices["objs"]["Facundo"] = idx; idx += 1
    all_ranges.append(RANGO_OBJ_IVAN); mapa_indices["objs"]["Iván"] = idx; idx += 1
    all_ranges.append(WEEK_RANGE); mapa_indices["week"] = idx; idx += 1

    try:
        # Llamada a la API de Sheets
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

    data_usuarios = {u: {"estado": {}, "tiempos": {}} for u in USERS}
    
    materia_en_curso = None
    inicio_dt = None
    
    for user, materias in USERS.items():
        for m in materias:
            idx_est = mapa_indices["materias"][(user, m, "est")]
            raw_est = get_val(idx_est)
            data_usuarios[user]["estado"][m] = raw_est
            
            idx_time = mapa_indices["materias"][(user, m, "time")]
            raw_time = get_val(idx_time)
            secs = parse_time_cell_to_seconds(raw_time)
            data_usuarios[user]["tiempos"][m] = segundos_a_hms(secs)
            
            # Buscar el inicio_dt y materia_activa para el usuario actualmente seleccionado
            if "usuario_seleccionado" in st.session_state and user == st.session_state.get("usuario_seleccionado") and str(raw_est).strip() != "":
                try:
                    inicio_dt = parse_datetime(raw_est)
                    materia_en_curso = m
                except Exception:
                    pass
                
    resumen = {
        "Facundo": {"per_min": parse_float_or_zero(get_val(mapa_indices["rates"]["Facundo"])), "obj": parse_float_or_zero(get_val(mapa_indices["objs"]["Facundo"]))},
        "Iván": {"per_min": parse_float_or_zero(get_val(mapa_indices["rates"]["Iván"])), "obj": parse_float_or_zero(get_val(mapa_indices["objs"]["Iván"]))}
    }
    raw_week = get_val(mapa_indices["week"], "0")
    balance_val = parse_float_or_zero(raw_week)

    # Inicializar/Actualizar el estado de sesión (solo si el usuario ya está seleccionado)
    if "usuario_seleccionado" in st.session_state:
        st.session_state["materia_activa"] = materia_en_curso
        st.session_state["inicio_dt"] = inicio_dt

    return {"users_data": data_usuarios, "resumen": resumen, "balance": balance_val}

def batch_write(updates):
    """Escribe los datos y limpia la caché para forzar una recarga al siguiente ciclo."""
    try:
        sheets_batch_update(st.secrets["sheet_id"], updates)
        cargar_datos_unificados.clear() # Limpiar caché para forzar relectura en el próximo rerun
    except Exception as e:
        st.error(f"Error escribiendo Google Sheets: {e}")
        st.stop()

# ------------------ HELPERS DE INICIO/STOP (callbacks) ------------------
def start_materia_callback(usuario, materia):
    """Callback para iniciar: escribe la marca de inicio en la celda 'est', actualiza session_state."""
    try:
        info = USERS[usuario][materia]
        
        # 1. Preparar updates para Google Sheets: Marca actual y limpieza de otras
        now_str = ahora_str()
        updates = [(info["est"], now_str)] + [
            (m_datos["est"], "") 
            for m_datos in USERS[usuario].values() 
            if m_datos is not None and m_datos is not info
        ]
        
        # 2. Escribir en Google Sheets
        batch_write(updates)
        
        # 3. Actualizar session_state para el contador en tiempo real
        st.session_state["materia_activa"] = materia
        st.session_state["inicio_dt"] = parse_datetime(now_str)
        
    except Exception as e:
        st.error(f"start_materia error: {e}")
    finally:
        pedir_rerun()

def stop_materia_callback(usuario, materia):
    """Callback para detener: lee la marca (de session_state o releyendo si es necesario), calcula duración, suma al día correcto y limpia 'est'."""
    try:
        info = USERS[usuario][materia]
        inicio = st.session_state.get("inicio_dt")
        
        if inicio is None or st.session_state.get("materia_activa") != materia:
            # Fallback: leemos la hoja si session_state no tiene el inicio (mínimo uso de la hoja)
            st.warning("Marca de inicio no encontrada en session_state, releyendo de la hoja...")
            try:
                res = sheets_batch_get(st.secrets["sheet_id"], [info["est"]])
                vr = res.get("valueRanges", [{}])[0]
                prev_est = vr.get("values", [[""]])[0][0] if vr.get("values") else ""
                if not prev_est:
                     st.error("No hay marca de inicio registrada (no se puede detener).")
                     pedir_rerun()
                     return
                inicio = parse_datetime(prev_est)
            except Exception as e:
                 st.error(f"Error leyendo marca de inicio de la hoja: {e}")
                 pedir_rerun()
                 return
                 
        fin = _argentina_now_global()
        if fin <= inicio:
            st.error("Tiempo inválido. La hora de fin es anterior a la de inicio.")
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
            
            # Leer previo (necesario para sumarlo)
            try:
                res2 = sheets_batch_get(st.secrets["sheet_id"], [time_cell_for_row])
                vr2 = res2.get("valueRanges", [{}])[0]
                prev_raw = vr2.get("values", [[""]])[0][0] if vr2.get("values") else ""
            except:
                prev_raw = ""
                
            new_secs = parse_time_cell_to_seconds(prev_raw) + segs
            updates.append((time_cell_for_row, segundos_a_hms(new_secs)))

        updates.append((info["est"], ""))  # limpiar marca de inicio en la hoja
        batch_write(updates)
        
        # Limpiar session_state
        st.session_state["materia_activa"] = None
        st.session_state["inicio_dt"] = None
        
    except Exception as e:
        st.error(f"stop_materia error: {e}")
    finally:
        pedir_rerun()

def main():
    # Si un callback pidió un rerun, hacerlo aquí (fuera del callback)
    if st.session_state.get("_do_rerun", False):
        st.session_state["_do_rerun"] = False
        st.rerun()
        
    # --- Sidebar debug ---
    st.sidebar.header("🔧 Debug & Controls")
    
    st.sidebar.markdown("**session_state**")
    st.sidebar.write(dict(st.session_state))
    if st.sidebar.button("Test click (sidebar)"):
        st.sidebar.write("Click registrado:", ahora_str())

    # --- Lógica de Selección de Usuario ---
    try:
        params = st.query_params
    except Exception:
        params = st.experimental_get_query_params()

    def set_user_and_rerun(u):
        st.session_state["usuario_seleccionado"] = u
        st.rerun()

    if "usuario_seleccionado" not in st.session_state:
        # Lógica de detección inicial por URL
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
        # UI de selección inicial
        st.markdown("<h1 style='text-align: center; margin-bottom: 30px;'>¿Quién sos?</h1>", unsafe_allow_html=True)
        if st.button("👤 Facundo", use_container_width=True):
            set_user_and_rerun("Facundo")
        st.write("")
        if st.button("👤 Iván", use_container_width=True):
            set_user_and_rerun("Iván")
        st.stop()

    # --- Carga de Datos y Variables Globales ---
    datos_globales = cargar_datos_unificados()
    datos = datos_globales["users_data"]
    resumen_marcas = datos_globales["resumen"]
    balance_val_raw = datos_globales["balance"]

    USUARIO_ACTUAL = st.session_state["usuario_seleccionado"]
    OTRO_USUARIO = "Iván" if USUARIO_ACTUAL == "Facundo" else "Facundo"
    
    # Obtener estado de session_state (para el contador en tiempo real)
    materia_en_curso = st.session_state.get("materia_activa")
    inicio_dt = st.session_state.get("inicio_dt")
    
    # Determinar si el usuario está estudiando (usando session_state para el contador)
    usuario_estudiando = materia_en_curso is not None
    
    # Determinar si el otro usuario está estudiando (usando la data cargada de la hoja)
    materia_otro = next((m for m, v in datos[OTRO_USUARIO]["estado"].items() if str(v).strip() != ""), "")
    otro_estudiando = materia_otro != ""

    def circle(color):
        return (f'<span style="display:inline-flex; align-items:center; justify-content:center; '
                f'width:10px; height:10px; border-radius:50%; background:{color}; '
                f'margin-right:6px; flex-shrink:0;"></span>')

    circle_usuario = circle("#00e676" if usuario_estudiando else "#ffffff")
    circle_otro = circle("#00e676" if otro_estudiando else "#ffffff")

    
    # =========================================================================================
    # CÁLCULOS ESTÁTICOS Y EN TIEMPO REAL
    # =========================================================================================

    # Calcular métricas (se necesita antes o dentro del bucle)
    def calcular_metricas(usuario, tiempo_activo_seg_local=0):
        per_min = resumen_marcas[usuario]["per_min"]
        objetivo = resumen_marcas[usuario]["obj"]
        total_min = 0.0
        
        for materia in USERS[usuario]:
            base_seg = hms_a_segundos(datos[usuario]["tiempos"][materia])
            segs_materia = base_seg
            
            # Si es la materia activa, agregar el tiempo_activo_seg_local
            if usuario == USUARIO_ACTUAL and materia == materia_en_curso:
                segs_materia += tiempo_activo_seg_local
                
            total_min += segs_materia / 60
            
        progreso_en_dinero = (tiempo_activo_seg_local / 60) * per_min 
        m_tot = total_min * per_min
        
        return m_tot, per_min, objetivo, total_min, progreso_en_dinero

    # Iniciar con 0 segundos extra si no estamos estudiando, o calcular si estamos estudiando.
    tiempo_anadido_seg = 0
    if usuario_estudiando and inicio_dt is not None:
        tiempo_anadido_seg = int((_argentina_now_global() - inicio_dt).total_seconds())

    m_tot, m_rate, m_obj, total_min, progreso_en_dinero = calcular_metricas(USUARIO_ACTUAL, tiempo_anadido_seg)
    o_tot, o_rate, o_obj, total_min_otro, _ = calcular_metricas(OTRO_USUARIO) # El otro usuario no tiene tiempo activo local

    # Métricas para la UI y el Widget
    pago_objetivo = m_rate * m_obj
    progreso_pct = min(m_tot / max(1, pago_objetivo), 1.0) * 100
    color_bar = "#00e676" if progreso_pct >= 90 else "#ffeb3b" if progreso_pct >= 50 else "#ff1744"
    objetivo_hms = segundos_a_hms(int(m_obj * 60))
    total_hms = segundos_a_hms(int(total_min * 60))

    balance_val = balance_val_raw
    if USUARIO_ACTUAL == "Facundo":
        balance_val = -balance_val
    balance_val += progreso_en_dinero
    balance_color = "#00e676" if balance_val > 0 else "#ff1744" if balance_val < 0 else "#aaa"
    balance_str = f"+${balance_val:.2f}" if balance_val > 0 else (f"-${abs(balance_val):.2f}" if balance_val < 0 else "$0.00")

    # --- CÁLCULO DEL OTRO USUARIO PARA WIDGET ---
    o_pago_obj = o_rate * o_obj
    o_progreso_pct = min(o_tot / max(1, o_pago_obj), 1.0) * 100
    o_total_hms = segundos_a_hms(int(total_min_otro * 60))
    
    # --------------------------------------------------------------------------------------
    # 🚨 INICIO: INTEGRACIÓN CON WIDGET DE ANDROID (Se ejecuta siempre para enviar datos) 🚨
    # --------------------------------------------------------------------------------------
    
    # 1. Preparar los datos para el widget
    widget_data = {
        "totalHms": total_hms,
        "money": round(m_tot, 2), # Redondeamos a 2 decimales para JS
        "progress": int(progreso_pct), 
        "weekValue": round(balance_val, 2), # Redondeamos el balance
        "goal": objetivo_hms,
        "otherUserTotalHms": o_total_hms,
        "otherUserMoney": round(o_tot, 2),
        "otherUserProgress": int(o_progreso_pct)
    }

    # 2. Convertir el diccionario de Python a un objeto JSON para JavaScript
    widget_data_json = json.dumps(widget_data)

    # 3. Crear el script de JavaScript para llamar al puente de Android
    js_code = f"""
    <script>
        (function() {{
            // Solo intentar llamar si el puente 'AndroidBridge' existe
            if (typeof AndroidBridge !== "undefined" && typeof AndroidBridge.updateWidgetData === "function") {{
                const data = {widget_data_json};
                AndroidBridge.updateWidgetData(
                    data.totalHms,
                    data.money,
                    data.progress,
                    data.weekValue,
                    data.goal,
                    data.otherUserTotalHms,
                    data.otherUserMoney,
                    data.otherUserProgress
                );
            }}
        }})();
    </script>
    """

    # 4. Ejecutar el script en Streamlit
    import streamlit.components.v1 as components
    components.html(js_code, height=0)

    # --------------------------------------------------------------------------------------
    # 🏁 FIN: INTEGRACIÓN CON WIDGET DE ANDROID 🏁
    # --------------------------------------------------------------------------------------

    # =========================================================================================
    # RENDERIZADO PRINCIPAL (Se renderiza siempre, si el usuario está estudiando,
    # se usará un placeholder que se actualiza en el bucle. Si no, se renderiza estático)
    # =========================================================================================

    # --- Actualizar Placeholder Global (Dashboard Principal) ---
    placeholder_total = st.empty()
    
    with placeholder_total.container():
        st.markdown(f"""
            <div style="background-color: #1e1e1e; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
                <div style="font-size: 1.2rem; color: #aaa; margin-bottom: 5px;">Hoy</div>
                <div style="width: 100%; font-size: 2.2rem; font-weight: bold; color: #fff; line-height: 1;">{total_hms} | ${m_tot:.2f}</div>
                <div style="width:100%; background-color:#333; border-radius:10px; height:12px; margin: 15px 0;">
                    <div style="width:{progreso_pct}%; background-color:{color_bar}; height:100%; border-radius:10px; transition: width 0.5s;"></div>
                </div>
                <div style="display:flex; justify-content:space-between; color:#888;">
                    <div>Balance: <span style="color:{balance_color};">{balance_str}</span></div>
                    <div>{objetivo_hms} | ${pago_objetivo:.2f}</div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
    # --- Progreso Otro Usuario (Renderizado Estático) ---
    o_color_bar = "#00e676" if o_progreso_pct >= 90 else "#ffeb3b" if o_progreso_pct >= 50 else "#ff1744"
    o_obj_hms = segundos_a_hms(int(o_obj * 60))

    with st.expander(f"Progreso de {OTRO_USUARIO}.", expanded=True):
            st.markdown(f"""
            <div style="margin-bottom: 10px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-size: 1.1rem; color: #ddd;"><b>{o_total_hms} | ${o_tot:.2f}</b></span>
                </div>
                <div style="width:100%; background-color:#444; border-radius:8px; height:8px; margin-top: 8px;">
                    <div style="width:{o_progreso_pct}%; background-color:{o_color_bar}; height:100%; border-radius:8px;"></div>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center; font-size:0.8rem; color:#aaa; margin-top:5px;">
                    <div style="display:flex; align-items:center;">
                        {circle_otro}
                        <span style="color:#00e676; margin-left:6px; visibility:{ 'visible' if materia_otro else 'hidden' };">
                            {materia_otro if materia_otro else 'Placeholder'}
                        </span>
                    </div>
                    <span style="font-size: 0.9rem; color: #888;">{o_obj_hms} | ${o_pago_obj:.2f}</span>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
    # Manifiesto
    with st.expander("ℹ️ No pensar, actuar."):
        md_content = st.secrets["md"]["facundo"] if USUARIO_ACTUAL == "Facundo" else st.secrets["md"]["ivan"]
        st.markdown(md_content)

    st.subheader("Materias")

    # =========================================================================================
    # BUCLE DE ACTUALIZACIÓN (Solo si el usuario está estudiando)
    # =========================================================================================

    if usuario_estudiando:
        
        # Crear placeholders para los contadores que se actualizarán
        placeholder_materias = {m: st.empty() for m in USERS[USUARIO_ACTUAL]}

        while True:
            # Recalculamos el tiempo
            tiempo_anadido_seg = int((_argentina_now_global() - inicio_dt).total_seconds())
            
            # Recalculamos todas las métricas que dependen del tiempo_anadido_seg
            m_tot, m_rate, m_obj, total_min, progreso_en_dinero = calcular_metricas(USUARIO_ACTUAL, tiempo_anadido_seg)
            # ... (Aquí iría todo el recálculo de total_hms, progreso_pct, balance_val, etc., para actualizar)
            
            # NOTA: En el código real, tendrías que repetir los cálculos de métricas y widget_data aquí,
            # pero dado que ya los calculaste arriba ANTES del bucle (con el valor de tiempo_anadido_seg de la primera ejecución),
            # solo necesitamos enfocarnos en el renderizado de las tarjetas dentro del bucle.
            
            # --- Actualizar Placeholders de Materias y Botones ---
            mis_materias = USERS[USUARIO_ACTUAL]
            for materia, info in mis_materias.items():
                
                base_seg = hms_a_segundos(datos[USUARIO_ACTUAL]["tiempos"][materia])
                tiempo_total_seg = base_seg
                en_curso = materia_en_curso == materia
                
                # Sumar el tiempo en curso solo a la materia activa
                if en_curso:
                    tiempo_total_seg += max(0, tiempo_anadido_seg)

                tiempo_total_hms = segundos_a_hms(tiempo_total_seg)
                badge_html = f'<div class="status-badge status-active">🟢 Estudiando...</div>' if en_curso else ''
                html_card = f"""<div class="materia-card"><div class="materia-title">{materia}</div>{badge_html}<div class="materia-time">{tiempo_total_hms}</div></div>"""
                
                # Usar el placeholder específico de la materia
                with placeholder_materias[materia].container():
                    st.markdown(html_card, unsafe_allow_html=True)

                    # Buttons using on_click callbacks
                    key_start = sanitize_key(f"start_{USUARIO_ACTUAL}_{materia}")
                    key_stop = sanitize_key(f"stop_{USUARIO_ACTUAL}_{materia}")

                    cols = st.columns([1,1,1])
                    with cols[0]:
                        if en_curso:
                            st.button(f"⛔ DETENER {materia[:14]}", key=key_stop, use_container_width=True,
                                        on_click=stop_materia_callback, args=(USUARIO_ACTUAL, materia))
                        else:
                            st.button("...", disabled=True, key=f"dis_{key_start}", use_container_width=True)

                    with cols[1]:
                        # Manual correction expander y guardado
                        with st.expander("🛠️ Corregir tiempo manualmente"):
                            tiempo_acumulado_hms = datos[USUARIO_ACTUAL]["tiempos"][materia]
                            new_val = st.text_input("Tiempo (HH:MM:SS)", value=tiempo_acumulado_hms, key=f"input_{sanitize_key(materia)}")
                            
                            def save_correction_callback(materia_key, new_time_val):
                                if ":" in new_time_val:
                                    batch_write([(USERS[USUARIO_ACTUAL][materia_key]["time"], new_time_val)])
                                else:
                                    st.error("Formato inválido (debe ser HH:MM:SS)")
                                pedir_rerun()
                            
                            if st.button("Guardar Corrección", key=f"save_{sanitize_key(materia)}", on_click=save_correction_callback, args=(materia, new_val)):
                                pass


            # Esperar 1 segundo antes de la próxima actualización
            time.sleep(1)
            st.rerun() # Fuerza el ciclo de Streamlit para la actualización del tiempo.

    else:
        # El usuario NO está estudiando. Renderizado estático de materias y botones INICIAR.
        mis_materias = USERS[USUARIO_ACTUAL]
        for materia, info in mis_materias.items():
            
            tiempo_total_hms = datos[USUARIO_ACTUAL]["tiempos"][materia]
            
            # Renderizado de tarjeta estática
            html_card = f"""<div class="materia-card"><div class="materia-title">{materia}</div><div class="materia-time">{tiempo_total_hms}</div></div>"""
            st.markdown(html_card, unsafe_allow_html=True)

            key_start = sanitize_key(f"start_{USUARIO_ACTUAL}_{materia}")
            cols = st.columns([1,1,1])
            with cols[0]:
                st.button("▶ INICIAR", key=key_start, use_container_width=True,
                            on_click=start_materia_callback, args=(USUARIO_ACTUAL, materia))

            with cols[1]:
                # Manual correction expander y guardado (igual que en el bucle)
                with st.expander("🛠️ Corregir tiempo manualmente"):
                    tiempo_acumulado_hms = datos[USUARIO_ACTUAL]["tiempos"][materia]
                    new_val = st.text_input("Tiempo (HH:MM:SS)", value=tiempo_acumulado_hms, key=f"input_{sanitize_key(materia)}")
                    
                    def save_correction_callback(materia_key, new_time_val):
                        if ":" in new_time_val:
                            batch_write([(USERS[USUARIO_ACTUAL][materia_key]["time"], new_time_val)])
                        else:
                            st.error("Formato inválido (debe ser HH:MM:SS)")
                        pedir_rerun()
                    
                    if st.button("Guardar Corrección", key=f"save_{sanitize_key(materia)}", on_click=save_correction_callback, args=(materia, new_val)):
                        pass

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        st.error(f"Error crítico en main(): {e}")
        st.sidebar.error(f"Error crítico: {e}")
        # footer: opción de reinicio de sesión si hay una excepción grave
        if st.sidebar.button("Reiniciar sesión (limpiar estado)"):
            st.session_state.clear()
            st.rerun()

