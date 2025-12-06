import streamlit as st
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, date

# Intentar importar manejo de zonas horarias de forma robusta
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
# CONFIGURACIÓN DE PÁGINA Y ESTILOS CSS (MOBILE FIRST)
# -------------------------------------------------------------------
st.set_page_config(
    page_title="Control de Estudio",
    page_icon="⏳",
    layout="centered"  # Centered es mejor para móvil que Wide
)

# Inyectar CSS para agrandar fuentes y mejorar botones en móvil
st.markdown("""
    <style>
    /* Agrandar la fuente global del cuerpo */
    html, body, [class*="css"] {
        font-size: 18px !important; 
    }
    
    /* Agrandar títulos */
    h1 { font-size: 2.5rem !important; }
    h2 { font-size: 2rem !important; }
    h3 { font-size: 1.5rem !important; }
    
    /* Estilo para Tarjetas de Materia */
    .materia-card {
        background-color: #262730;
        border: 1px solid #464b5c;
        padding: 20px;
        border-radius: 15px;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .materia-title {
        font-size: 1.4rem;
        font-weight: bold;
        color: #ffffff;
        margin-bottom: 5px;
    }
    .materia-time {
        font-size: 2.2rem;
        font-weight: bold;
        color: #00e676; /* Verde neón para contraste */
        font-family: 'Courier New', monospace;
        margin-bottom: 15px;
    }
    .status-badge {
        display: inline-block;
        padding: 5px 10px;
        border-radius: 12px;
        font-size: 0.9rem;
        font-weight: bold;
        margin-bottom: 10px;
    }
    .status-active {
        background-color: rgba(0, 230, 118, 0.2);
        color: #00e676;
        border: 1px solid #00e676;
    }
    
    /* Ajuste de botones para que sean más altos y fáciles de tocar */
    div.stButton > button {
        height: 3.5rem;
        font-size: 1.2rem !important;
        font-weight: bold !important;
        border-radius: 12px !important;
    }
    </style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------------
# ZONA HORARIA Y UTILS
# -------------------------------------------------------------------
def _argentina_now_global():
    if ZoneInfo is not None:
        return datetime.now(ZoneInfo('America/Argentina/Cordoba'))
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

# -------------------------------------------------------------------
# CONEXIÓN GOOGLE SHEETS
# -------------------------------------------------------------------
@st.cache_resource
def get_service():
    try:
        key_dict = json.loads(st.secrets["textkey"])
        creds = service_account.Credentials.from_service_account_info(
            key_dict,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        return build("sheets", "v4", credentials=creds).spreadsheets()
    except Exception as e:
        st.error(f"Error config secrets: {e}")
        st.stop()

sheet = get_service()

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

# Utils conversión
def hms_a_segundos(hms):
    if not hms: return 0
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
    try: return float(str(s).replace(",", ".").strip())
    except: return 0.0

def enable_manual_input(materia_key):
    st.session_state[f"show_manual_{materia_key}"] = True

# -------------------------------------------------------------------
# LÓGICA DATOS
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
        return {"Facundo": {"per_min": vr[0].get("values",[[0]])[0][0]}, 
                "Iván": {"per_min": vr[1].get("values",[[0]])[0][0]}}
    except:
        return {"Facundo": {"per_min": 0}, "Iván": {"per_min": 0}}

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
# SELECCIÓN USUARIO
# -------------------------------------------------------------------
if "usuario_seleccionado" not in st.session_state:
    st.markdown("<h1 style='text-align: center; margin-bottom: 30px;'>¿Quién sos?</h1>", unsafe_allow_html=True)
    
    # Botones grandes para móvil
    if st.button("👤 Soy Facundo", use_container_width=True):
        st.session_state["usuario_seleccionado"] = "Facundo"
        st.rerun()
    
    st.write("") # Espacio
    
    if st.button("👤 Soy Iván", use_container_width=True):
        st.session_state["usuario_seleccionado"] = "Iván"
        st.rerun()
    st.stop()

# -------------------------------------------------------------------
# INTERFAZ PRINCIPAL
# -------------------------------------------------------------------
USUARIO_ACTUAL = st.session_state["usuario_seleccionado"]
OTRO_USUARIO = "Iván" if USUARIO_ACTUAL == "Facundo" else "Facundo"

# Sidebar simple
with st.sidebar:
    st.header(f"Hola, {USUARIO_ACTUAL}")
    if st.button("Cerrar Sesión", use_container_width=True):
        del st.session_state["usuario_seleccionado"]
        st.rerun()

st.title("⏳ Control Estudio")

# Carga de datos
datos = cargar_todo()
resumen_marcas = cargar_resumen_marcas()

# --- MÉTRICAS ---
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
        res = sheet.values().get(spreadsheetId=st.secrets["sheet_id"], range=f"'{SHEET_MARCAS}'!{col_obj}{TIME_ROW}").execute()
        objetivo = parse_float_or_zero(res.get("values", [[0]])[0][0])
    except: pass
    
    return total_min * per_min, per_min, objetivo

# Barra de progreso grande
m_tot, m_rate, m_obj = calcular_metricas(USUARIO_ACTUAL)
pago_objetivo = m_rate * m_obj
progreso_pct = min(m_tot / max(1, pago_objetivo), 1.0) * 100
color_bar = "#00e676" if progreso_pct >= 90 else "#ffeb3b" if progreso_pct >= 50 else "#ff1744"

st.markdown(f"""
    <div style="background-color: #1e1e1e; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
        <div style="font-size: 1.2rem; color: #aaa; margin-bottom: 5px;">Tu Ganancia Hoy</div>
        <div style="font-size: 3rem; font-weight: bold; color: #fff; line-height: 1;">${m_tot:.2f}</div>
        <div style="width:100%; background-color:#333; border-radius:10px; height:12px; margin: 15px 0;">
            <div style="width:{progreso_pct}%; background-color:{color_bar}; height:100%; border-radius:10px; transition: width 0.5s;"></div>
        </div>
        <div style="text-align: right; color: #888;">Meta: ${pago_objetivo:.2f}</div>
    </div>
""", unsafe_allow_html=True)

# -------------------------------------------------------------------
# LISTA DE MATERIAS (Diseño de Tarjetas Grandes)
# -------------------------------------------------------------------
st.subheader("Tus Materias")

mis_materias = USERS[USUARIO_ACTUAL]
materia_en_curso = None
for m, info in mis_materias.items():
    if str(datos[USUARIO_ACTUAL]["estado"][m]).strip() != "":
        materia_en_curso = m
        break

for materia, info in mis_materias.items():
    est_raw = datos[USUARIO_ACTUAL]["estado"][materia]
    tiempo_acum = datos[USUARIO_ACTUAL]["tiempos"][materia]
    
    tiempo_anadido_seg = 0
    en_curso = False
    if str(est_raw).strip() != "":
        try:
            inicio = parse_datetime(est_raw)
            tiempo_anadido_seg = int((_argentina_now_global() - inicio).total_seconds())
            en_curso = True
        except: pass

    tiempo_total_hms = segundos_a_hms(hms_a_segundos(tiempo_acum) + max(0, tiempo_anadido_seg))
    
    # --- RENDERIZADO DE TARJETA ---
    # Usamos HTML puro para el contenido estático para controlar totalmente el tamaño
    html_card = f"""
    <div class="materia-card">
        <div class="materia-title">{materia}</div>
        {'<div class="status-badge status-active">🟢 Estudiando...</div>' if en_curso else ''}
        <div class="materia-time">{tiempo_total_hms}</div>
    </div>
    """
    st.markdown(html_card, unsafe_allow_html=True)

    # Botones debajo de la tarjeta (fuera del HTML para mantener funcionalidad de Streamlit)
    # Usamos columnas pero con ratios que funcionen en móvil (botones anchos)
    c_actions = st.container()
    
    with c_actions:
        if materia_en_curso == materia:
            # BOTÓN DE PARAR (Rojo y Grande)
            if st.button(f"⛔ DETENER {materia[:10]}...", key=f"stop_{materia}", use_container_width=True, type="primary"):
                diff_seg = int((_argentina_now_global() - parse_datetime(est_raw)).total_seconds())
                acumular_tiempo(USUARIO_ACTUAL, materia, diff_seg/60)
                batch_write([
                    (info["time"], hms_a_fraction(segundos_a_hms(diff_seg + hms_a_segundos(tiempo_acum)))),
                    (info["est"], "")
                ])
                st.rerun()
        else:
            if materia_en_curso is None:
                # BOTÓN DE INICIAR (Normal y Grande)
                if st.button(f"▶ INICIAR", key=f"start_{materia}", use_container_width=True):
                    limpiar_estudiando(mis_materias)
                    batch_write([(info["est"], ahora_str())])
                    st.rerun()
            else:
                # Deshabilitado si otra corre
                st.button("...", disabled=True, key=f"dis_{materia}", use_container_width=True)

    # Botón Editar pequeño y discreto abajo a la derecha de la tarjeta
    with st.expander("🛠️ Corregir tiempo manualmente"):
        new_val = st.text_input("Tiempo (HH:MM:SS)", value=tiempo_acum, key=f"input_{materia}")
        if st.button("Guardar Corrección", key=f"save_{materia}"):
            try:
                batch_write([(info["time"], hms_a_fraction(new_val))])
                st.rerun()
            except:
                st.error("Formato inválido")
    
    st.write("") # Margen extra entre tarjetas

# -------------------------------------------------------------------
# FOOTER / EXTRAS
# -------------------------------------------------------------------
st.divider()
if st.button("🔄 Actualizar Datos", use_container_width=True):
    st.rerun()

with st.expander("ℹ️ Manifiesto"):
    md_content = st.secrets["md"]["facundo"] if USUARIO_ACTUAL == "Facundo" else st.secrets["md"]["ivan"]
    st.markdown(md_content)

