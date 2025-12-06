import streamlit as st
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, date

# Intentar importar manejo de zonas horarias de forma robusta (estilo app.py)
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

# -------------------------------------------------------------------
# ZONA HORARIA ARGENTINA (Lógica robusta app.py)
# -------------------------------------------------------------------
def _argentina_now_global():
    if ZoneInfo is not None:
        return datetime.now(ZoneInfo('America/Argentina/Cordoba')) # Usando Cordoba como en tu script original
    if 'pytz' in globals() and pytz is not None:
        return datetime.now(pytz.timezone('America/Argentina/Cordoba'))
    return datetime.now()

def ahora_str():
    return _argentina_now_global().isoformat(sep=" ", timespec="seconds")

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
        
    fmts = [
        "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=TZ)
            return dt.astimezone(TZ)
        except:
            continue
    raise ValueError(f"Formato inválido en marca temporal: {s}")

# -------------------------------------------------------------------
# CONEXIÓN Y UTILIDADES (Cacheada estilo app.py)
# -------------------------------------------------------------------
@st.cache_resource
def get_service():
    try:
        key_dict = json.loads(st.secrets["textkey"])
        creds = service_account.Credentials.from_service_account_info(
            key_dict,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        service = build("sheets", "v4", credentials=creds)
        return service.spreadsheets()
    except KeyError:
        st.error("Error: Falta configurar el secreto 'textkey'.")
        st.stop()

sheet = get_service()

# Variables Globales de Configuración
FILA_BASE = 170
FECHA_BASE = date(2025, 12, 2)
SHEET_FACUNDO = "F. Economía"
SHEET_IVAN = "I. Física"
SHEET_MARCAS = "marcas"

def fila_para_fecha(fecha_actual):
    delta = (fecha_actual - FECHA_BASE).days
    return FILA_BASE + delta

def get_time_row():
    hoy = _argentina_now_global().date()
    return fila_para_fecha(hoy)

TIME_ROW = get_time_row()
MARCAS_ROW = 2

# Mapeo de Usuarios
USERS = {
    "Facundo": {
        "Matemática para Economistas 1": {"time": f"'{SHEET_FACUNDO}'!B{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!B{MARCAS_ROW}"},
        "Matemática para Economistas 2": {"time": f"'{SHEET_FACUNDO}'!C{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!C{MARCAS_ROW}"},
        "Macroeconomía 1":               {"time": f"'{SHEET_FACUNDO}'!D{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!D{MARCAS_ROW}"},
        "Historia":                      {"time": f"'{SHEET_FACUNDO}'!E{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!E{MARCAS_ROW}"},
    },
    "Iván": {
        "Física":   {"time": f"'{SHEET_IVAN}'!B{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!F{MARCAS_ROW}"},
        "Análisis": {"time": f"'{SHEET_IVAN}'!C{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!G{MARCAS_ROW}"},
    }
}

# -------------------------------------------------------------------
# FUNCIONES AUXILIARES (Tiempo y Formato)
# -------------------------------------------------------------------
def hms_a_segundos(hms):
    if not hms or str(hms).strip() == "": return 0
    try:
        h, m, s = map(int, hms.split(":"))
        return h*3600 + m*60 + s
    except: return 0

def segundos_a_hms(seg):
    h = seg // 3600
    m = (seg % 3600) // 60
    s = seg % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def hms_a_fraction(hms): return hms_a_segundos(hms) / 86400
def hms_a_minutos(hms): return hms_a_segundos(hms) / 60
def parse_float_or_zero(s):
    if s is None: return 0.0
    s = str(s).replace(",", ".").strip()
    try: return float(s)
    except: return 0.0

def enable_manual_input(materia_key):
    st.session_state[f"show_manual_{materia_key}"] = True

# -------------------------------------------------------------------
# LÓGICA GOOGLE SHEETS (Lectura/Escritura)
# -------------------------------------------------------------------
def cargar_todo():
    ranges = []
    for user, materias in USERS.items():
        for m, info in materias.items():
            ranges.append(info["est"])
            ranges.append(info["time"])

    res = sheet.values().batchGet(
        spreadsheetId=st.secrets["sheet_id"],
        ranges=ranges,
        valueRenderOption="FORMATTED_VALUE"
    ).execute()

    values = res.get("valueRanges", [])
    data = {u: {"estado": {}, "tiempos": {}} for u in USERS}
    idx = 0
    for user, materias in USERS.items():
        for materia, info in materias.items():
            est_val = values[idx].get("values", [[]])
            est_val = est_val[0][0] if est_val and est_val[0] else ""
            idx += 1
            time_val = values[idx].get("values", [[]])
            time_val = time_val[0][0] if time_val and time_val[0] else "00:00:00"
            idx += 1
            data[user]["estado"][materia] = est_val
            data[user]["tiempos"][materia] = time_val
    return data

def cargar_resumen_marcas():
    ranges = [f"'{SHEET_MARCAS}'!C{TIME_ROW}", f"'{SHEET_MARCAS}'!B{TIME_ROW}"]
    try:
        res = sheet.values().batchGet(spreadsheetId=st.secrets["sheet_id"], ranges=ranges, valueRenderOption="FORMATTED_VALUE").execute()
        vr = res.get("valueRanges", [])
    except:
        vr = [{} for _ in ranges]
    
    def _get(i):
        try: return vr[i].get("values", [[]])[0][0] or ""
        except: return ""
        
    return {"Facundo": {"per_min": _get(0)}, "Iván": {"per_min": _get(1)}}

def batch_write(updates):
    body = {"valueInputOption": "USER_ENTERED", "data": [{"range": r, "values": [[v]]} for r, v in updates]}
    sheet.values().batchUpdate(spreadsheetId=st.secrets["sheet_id"], body=body).execute()

def limpiar_estudiando(materias):
    batch_write([(datos["est"], "") for materia, datos in materias.items()])

def acumular_tiempo(usuario, materia, minutos_sumar):
    info = USERS[usuario][materia]
    res = sheet.values().get(spreadsheetId=st.secrets["sheet_id"], range=info["est"]).execute()
    valor_prev = parse_float_or_zero(res.get("values", [[0]])[0][0])
    batch_write([(info["est"], valor_prev + minutos_sumar)])

# -------------------------------------------------------------------
# SELECCIÓN DE USUARIO (Pantalla intermedia)
# -------------------------------------------------------------------
if "usuario_seleccionado" not in st.session_state:
    st.markdown("<h1 style='text-align: center;'>¿Quién sos?</h1>", unsafe_allow_html=True)
    st.write("")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        if st.button("👤 Soy Facundo", use_container_width=True):
            st.session_state["usuario_seleccionado"] = "Facundo"
            st.rerun()
        if st.button("👤 Soy Iván", use_container_width=True):
            st.session_state["usuario_seleccionado"] = "Iván"
            st.rerun()
    st.stop()

# -------------------------------------------------------------------
# INTERFAZ PRINCIPAL
# -------------------------------------------------------------------
USUARIO_ACTUAL = st.session_state["usuario_seleccionado"]
OTRO_USUARIO = "Iván" if USUARIO_ACTUAL == "Facundo" else "Facundo"

# Encabezado con Logout en Sidebar
st.sidebar.title(f"Hola, {USUARIO_ACTUAL}")
if st.sidebar.button("Cerrar sesión / Cambiar"):
    del st.session_state["usuario_seleccionado"]
    st.rerun()

st.title("⏳ Control de Estudio")

# Carga de Datos
datos = cargar_todo()
resumen_marcas = cargar_resumen_marcas()

# Función para renderizar barra de progreso (reutilizada para limpieza)
def render_progress(total_calc, per_min_val, objetivo, objetivo_hms):
    pago_objetivo = per_min_val * objetivo
    progreso = min(total_calc / max(1, pago_objetivo), 1.0) * 100
    color = "#5cb85c" if progreso >= 90 else "#f0ad4e" if progreso >= 50 else "#d9534f"
    
    st.markdown(f"<div style='font-size:32px; font-weight:bold; color:#333; line-height:1;'>${total_calc:.2f}</div>", unsafe_allow_html=True)
    st.markdown(f"""
        <div style="width:100%; background-color:#262730; border-radius:8px; height:8px; margin:4px 0 10px 0;">
            <div style="width:{progreso}%; background-color:{color}; height:100%; border-radius:8px; transition: width 0.4s ease;"></div>
        </div>
        <div style="color:#666; font-size:13px; margin-bottom:12px;">
            ${per_min_val:.2f}/min &nbsp;|&nbsp; Meta: ${pago_objetivo:.2f} ({objetivo_hms})
        </div>
    """, unsafe_allow_html=True)

# --- CÁLCULO DE MÉTRICAS COMPARTIDAS ---
def calcular_metricas(usuario):
    per_min = parse_float_or_zero(resumen_marcas[usuario].get("per_min", ""))
    total_min = 0.0
    
    for materia, info in USERS[usuario].items():
        base = hms_a_minutos(datos[usuario]["tiempos"][materia])
        progreso = 0
        est_raw = datos[usuario]["estado"][materia]
        if str(est_raw).strip() != "":
            try:
                inicio = parse_datetime(est_raw)
                progreso = (_argentina_now_global() - inicio).total_seconds() / 60
            except: pass
        total_min += base + progreso
    
    col_obj = "O" if usuario == "Iván" else "P"
    objetivo = 0.0
    try:
        # Nota: Esto es un poco ineficiente (hace call a API), pero mantiene la lógica original
        res = sheet.values().get(spreadsheetId=st.secrets["sheet_id"], range=f"'{SHEET_MARCAS}'!{col_obj}{TIME_ROW}").execute()
        objetivo = parse_float_or_zero(res.get("values", [[0]])[0][0])
    except: pass
    
    return total_min * per_min, per_min, objetivo, segundos_a_hms(int(objetivo * 60))

# -------------------------------------------------------------------
# PANEL SUPERIOR: MI PROGRESO vs EL DEL OTRO
# -------------------------------------------------------------------
col_me, col_other = st.columns(2)

with col_me:
    st.subheader("Mi Día")
    m_tot, m_rate, m_obj, m_obj_hms = calcular_metricas(USUARIO_ACTUAL)
    render_progress(m_tot, m_rate, m_obj, m_obj_hms)

with col_other:
    st.subheader(f"Día de {OTRO_USUARIO}")
    o_tot, o_rate, o_obj, o_obj_hms = calcular_metricas(OTRO_USUARIO)
    render_progress(o_tot, o_rate, o_obj, o_obj_hms)

if st.button("🔄 Sincronizar Tiempos", use_container_width=True):
    st.rerun()

# -------------------------------------------------------------------
# SECCIÓN: MATERIAS (Estilo Tarjetas/Botones como app.py)
# -------------------------------------------------------------------
st.divider()
st.subheader("📚 Mis Materias")

materia_en_curso = None
mis_materias = USERS[USUARIO_ACTUAL]
for m, info in mis_materias.items():
    if str(datos[USUARIO_ACTUAL]["estado"][m]).strip() != "":
        materia_en_curso = m
        break

# Iterar materias y mostrarlas más limpias
for materia, info in mis_materias.items():
    est_raw = datos[USUARIO_ACTUAL]["estado"][materia]
    tiempo_acum = datos[USUARIO_ACTUAL]["tiempos"][materia]
    
    # Calcular tiempo real
    tiempo_anadido_seg = 0
    en_curso = False
    if str(est_raw).strip() != "":
        try:
            inicio = parse_datetime(est_raw)
            tiempo_anadido_seg = int((_argentina_now_global() - inicio).total_seconds())
            en_curso = True
        except: pass

    tiempo_total_hms = segundos_a_hms(hms_a_segundos(tiempo_acum) + max(0, tiempo_anadido_seg))
    
    # Contenedor visual para cada materia
    with st.container():
        c1, c2, c3 = st.columns([0.5, 0.3, 0.2])
        
        # Nombre y Estado Visual
        with c1:
            st.markdown(f"**{materia}**")
            if en_curso:
                st.caption("🟢 Estudiando ahora...")
        
        # Tiempo
        with c2:
            st.markdown(f"⏱️ `{tiempo_total_hms}`")
        
        # Acciones
        with c3:
            if materia_en_curso == materia:
                # Botón de STOP
                if st.button("⛔ Parar", key=f"stop_{materia}", use_container_width=True):
                    diff_seg = int((_argentina_now_global() - parse_datetime(est_raw)).total_seconds())
                    acumular_tiempo(USUARIO_ACTUAL, materia, diff_seg/60)
                    batch_write([
                        (info["time"], hms_a_fraction(segundos_a_hms(diff_seg + hms_a_segundos(tiempo_acum)))),
                        (info["est"], "")
                    ])
                    st.rerun()
            else:
                if materia_en_curso is None:
                    # Botón de PLAY
                    if st.button("▶ Iniciar", key=f"start_{materia}", use_container_width=True):
                        limpiar_estudiando(mis_materias)
                        batch_write([(info["est"], ahora_str())])
                        st.rerun()
                else:
                    st.button("...", disabled=True, key=f"dis_{materia}")
                    
            # Edición Manual (expander pequeño dentro de la fila o botón simple)
            if st.button("✏️", key=f"btn_edit_{materia}"):
                enable_manual_input(materia)

    # Input manual si está activo
    if st.session_state.get(f"show_manual_{materia}", False):
        c_edit_1, c_edit_2 = st.columns([0.7, 0.3])
        new_val = c_edit_1.text_input("HH:MM:SS", value=tiempo_acum, key=f"input_{materia}")
        if c_edit_2.button("Guardar", key=f"save_{materia}"):
            try:
                batch_write([(info["time"], hms_a_fraction(new_val))])
                st.session_state[f"show_manual_{materia}"] = False
                st.rerun()
            except:
                st.error("Error formato")
    
    st.markdown("---") # Separador sutil

# -------------------------------------------------------------------
# EXPANDER: INFO ADICIONAL (Estilo app.py "No pensar, actuar")
# -------------------------------------------------------------------
md_content = st.secrets["md"]["facundo"] if USUARIO_ACTUAL == "Facundo" else st.secrets["md"]["ivan"]

with st.expander("ℹ️ No pensar, actuar (Manifiesto)", expanded=False):
    st.markdown(md_content)

