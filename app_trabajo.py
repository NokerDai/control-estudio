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

def cargar_estilos():
    st.markdown("""
        <style>
        html, body, [class*="css"] { font-size: 18px !important; }
        h1 { font-size: 2.5rem !important; }
        h2 { font-size: 2rem !important; }
        
        /* Estilo tarjeta cronómetro */
        .work-card {
            background-color: #262730;
            border: 1px solid #464b5c;
            padding: 20px;
            border-radius: 15px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
            text-align: center;
        }
        .work-title { font-size: 1.6rem; font-weight: bold; color: #ffffff; margin-bottom: 10px; }
        .work-time { 
            font-size: 2.5rem; 
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

# ------------------ GOOGLE SHEETS ------------------
@st.cache_resource
def get_sheets_session():
    try:
        key_dict = json.loads(st.secrets["service_account"])
    except Exception as e:
        st.error(f"Error leyendo st.secrets['service_account']")
        st.stop()
    try:
        creds = service_account.Credentials.from_service_account_info(
            key_dict,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        return AuthorizedSession(creds)
    except Exception as e:
        st.error(f"Error creando credenciales")
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

# ------------------ CONFIGURACIÓN DE HOJAS ------------------
# CRONÓMETRO:
SHEET_TRABAJO_CRONO = "F. Trabajo" # Puedes cambiar esto si el cronómetro también va a F. Trabajo
SHEET_MARCAS = "marcas"
FILA_BASE = 170
FECHA_BASE = date(2025, 12, 2)
MARCAS_ROW = 4 

# TAREAS:
SHEET_TAREAS = "F. Trabajo" # Hoja específica para las tareas
RANGE_TAREAS = f"'{SHEET_TAREAS}'!C2:D100" # Leemos hasta 100 tareas. A=Desc, B=Done

def get_time_row():
    hoy = _argentina_now_global().date()
    delta = (hoy - FECHA_BASE).days
    return FILA_BASE + delta

TIME_ROW = get_time_row()

WORK_PROJECTS = {
    "Facundo": {
        "Trabajo": {"time": f"'{SHEET_TRABAJO_CRONO}'!B{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!B{MARCAS_ROW}"}
    }
}

# ------------------ LÓGICA DE DATOS (CRONÓMETRO) ------------------
@st.cache_data()
def cargar_datos_trabajo():
    all_ranges = []
    mapa_indices = {}
    idx = 0
    
    for user, projects in WORK_PROJECTS.items():
        for p, info in projects.items():
            all_ranges.append(info["est"]); mapa_indices[(user, p, "est")] = idx; idx += 1
            all_ranges.append(info["time"]); mapa_indices[(user, p, "time")] = idx; idx += 1

    try:
        res = sheets_batch_get(st.secrets["sheet_id"], all_ranges)
    except Exception as e:
        st.error(f"Error Sheets: {e}")
        st.stop()

    values = res.get("valueRanges", [])
    def get_val(i, default=""):
        if i >= len(values): return default
        vr = values[i]; rows = vr.get("values", [])
        return rows[0][0] if rows and rows[0] else default

    data = {u: {"estado": {}, "tiempos": {}} for u in WORK_PROJECTS}
    inicio_dt = None
    proyecto_activo = None

    for user, projects in WORK_PROJECTS.items():
        for p in projects:
            idx_est = mapa_indices[(user, p, "est")]
            raw_est = get_val(idx_est)
            data[user]["estado"][p] = raw_est

            idx_time = mapa_indices[(user, p, "time")]
            raw_time = get_val(idx_time)
            secs = parse_time_cell_to_seconds(raw_time)
            data[user]["tiempos"][p] = segundos_a_hms(secs)

            if user == st.session_state.get("usuario_seleccionado") and str(raw_est).strip() != "":
                try:
                    inicio_dt = parse_datetime(raw_est)
                    proyecto_activo = p
                except:
                    pass
    
    if "usuario_seleccionado" in st.session_state:
        st.session_state["trabajo_activo"] = proyecto_activo
        st.session_state["trabajo_inicio_dt"] = inicio_dt

    return data

# ------------------ LÓGICA DE DATOS (TAREAS) ------------------
@st.cache_data(ttl=5) # Cache corto para reflejar cambios rápido
def fetch_tasks_from_sheet():
    """Lee las tareas de la hoja F. Trabajo (A2:B100)"""
    try:
        res = sheets_batch_get(st.secrets["sheet_id"], [RANGE_TAREAS])
        rows = res["valueRanges"][0].get("values", [])
        
        tasks = []
        for i, row in enumerate(rows):
            # Row index real (1-based) = i + 2 (porque empezamos en A2)
            row_idx = i + 2
            
            desc = row[0] if len(row) > 0 else ""
            status = row[1] if len(row) > 1 else "FALSE"
            
            if desc.strip(): # Solo agregar si tiene descripción
                is_done = (status.upper() == "TRUE")
                tasks.append({
                    "id": row_idx, # Guardamos la fila para editar luego
                    "desc": desc,
                    "done": is_done
                })
        return tasks
    except Exception as e:
        st.error(f"Error leyendo tareas: {e}")
        return []

def save_new_task(desc):
    """Agrega una tarea a la primera fila vacía."""
    # Leemos de nuevo para encontrar el hueco sin confiar en caché
    current_tasks = fetch_tasks_from_sheet()
    
    # Buscar el ID (fila) más alto ocupado
    max_row = 1 # Header es 1
    if current_tasks:
        max_row = max(t["id"] for t in current_tasks)
    
    next_row = max_row + 1
    
    # Escribir en esa fila
    range_desc = f"'{SHEET_TAREAS}'!A{next_row}"
    range_status = f"'{SHEET_TAREAS}'!B{next_row}"
    
    updates = [
        (range_desc, desc),
        (range_status, "FALSE")
    ]
    batch_write(updates)
    fetch_tasks_from_sheet.clear() # Invalidar caché

def update_task_status(row_id, is_done):
    range_status = f"'{SHEET_TAREAS}'!B{row_id}"
    val = "TRUE" if is_done else "FALSE"
    batch_write([(range_status, val)])
    fetch_tasks_from_sheet.clear()

def delete_task_row(row_id):
    range_all = f"'{SHEET_TAREAS}'!A{row_id}:B{row_id}"
    batch_write([(range_all, "")]) # Borrar contenido
    fetch_tasks_from_sheet.clear()

def batch_write(updates):
    try:
        sheets_batch_update(st.secrets["sheet_id"], updates)
        cargar_datos_trabajo.clear()
        fetch_tasks_from_sheet.clear()
    except Exception as e:
        st.error(f"Error escritura: {e}")

# ------------------ CALLBACKS CRONÓMETRO ------------------
def start_work_callback(usuario, proyecto):
    info = WORK_PROJECTS[usuario][proyecto]
    now_str = ahora_str()
    updates = [(info["est"], now_str)] + [
        (p_info["est"], "") for p, p_info in WORK_PROJECTS[usuario].items() if p != proyecto
    ]
    batch_write(updates)
    st.session_state["trabajo_activo"] = proyecto
    st.session_state["trabajo_inicio_dt"] = parse_datetime(now_str)
    pedir_rerun()

def stop_work_callback(usuario, proyecto):
    info = WORK_PROJECTS[usuario][proyecto]
    inicio = st.session_state.get("trabajo_inicio_dt")
    
    if inicio is None:
        try:
            res = sheets_batch_get(st.secrets["sheet_id"], [info["est"]])
            val = res["valueRanges"][0].get("values", [[""]])[0][0]
            inicio = parse_datetime(val)
        except:
            st.error("No se pudo detener: falta marca de inicio.")
            pedir_rerun()
            return

    fin = _argentina_now_global()
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
        time_cell = replace_row_in_range(info["time"], target_row)
        
        try:
            res = sheets_batch_get(st.secrets["sheet_id"], [time_cell])
            prev = res["valueRanges"][0].get("values", [[""]])[0][0]
        except: prev = ""
        
        new_secs = parse_time_cell_to_seconds(prev) + segs
        updates.append((time_cell, segundos_a_hms(new_secs)))

    updates.append((info["est"], ""))
    batch_write(updates)
    st.session_state["trabajo_activo"] = None
    st.session_state["trabajo_inicio_dt"] = None
    pedir_rerun()

# ------------------ UI TAREAS ------------------
def render_tasks_section(usuario):
    """Sección de tareas conectada a Sheets, solo para Facundo"""
    
    # RESTRICCIÓN: SOLO FACUNDO
    if usuario != "Facundo":
        return

    st.markdown("---")
    
    # Cargar tareas desde Sheets
    tasks = fetch_tasks_from_sheet()

    with st.expander("📋 Tareas y Pendientes (F. Trabajo)", expanded=True):
        # Input para nueva tarea
        c1, c2 = st.columns([3, 1])
        with c1:
            # Usamos un formulario para que el enter funcione mejor
            with st.form("new_task_form", clear_on_submit=True):
                new_task = st.text_input("Nueva tarea", placeholder="Escribí una tarea...")
                submitted = st.form_submit_button("Agregar")
                if submitted and new_task.strip():
                    save_new_task(new_task)
                    st.rerun()

        st.markdown("---")
        
        if not tasks:
            st.caption("No hay tareas pendientes en la hoja.")
        else:
            # Mostrar tareas
            for task in tasks:
                cols = st.columns([0.1, 0.8, 0.1])
                
                done = task["done"]
                row_id = task["id"]
                desc = task["desc"]
                
                label = f"~~{desc}~~" if done else desc
                
                with cols[0]:
                    # Checkbox
                    is_checked = st.checkbox("", value=done, key=f"chk_{row_id}")
                    if is_checked != done:
                        update_task_status(row_id, is_checked)
                        st.rerun()
                
                with cols[1]:
                    st.markdown(label)
                
                with cols[2]:
                    # Botón borrar
                    if st.button("🗑️", key=f"del_{row_id}"):
                        delete_task_row(row_id)
                        st.rerun()

# ------------------ MAIN APP ------------------
def main():
    st.set_page_config(page_title="Trabajo", page_icon="💼")
    cargar_estilos()

    if st.session_state.get("_do_rerun", False):
        st.session_state["_do_rerun"] = False
        st.rerun()

    if "usuario_seleccionado" not in st.session_state:
        st.error("Usuario no seleccionado.")
        st.stop()

    USUARIO_ACTUAL = st.session_state["usuario_seleccionado"]
    
    # Cargar Datos Cronómetro
    datos = cargar_datos_trabajo()
    mis_proyectos = WORK_PROJECTS.get(USUARIO_ACTUAL, {})
    
    active_project = st.session_state.get("trabajo_activo")
    inicio_dt = st.session_state.get("trabajo_inicio_dt")
    
    tiempo_anadido = 0
    if active_project and inicio_dt:
        tiempo_anadido = int((_argentina_now_global() - inicio_dt).total_seconds())

    # --- UI CRONÓMETRO ---
    st.title("💼 Espacio de Trabajo")

    for proyecto, info in mis_proyectos.items():
        base_hms = datos[USUARIO_ACTUAL]["tiempos"][proyecto]
        total_seg = hms_a_segundos(base_hms)
        
        en_curso = (active_project == proyecto)
        if en_curso:
            total_seg += max(0, tiempo_anadido)
            
        total_hms = segundos_a_hms(total_seg)
        badge = f'<div class="status-badge status-active">🟢 Trabajando...</div>' if en_curso else ''
        
        st.markdown(f"""
            <div class="work-card">
                <div class="work-title">{proyecto}</div>
                {badge}
                <div class="work-time">{total_hms}</div>
            </div>
        """, unsafe_allow_html=True)
        
        c1, c2, c3 = st.columns([1, 2, 1])
        with c2:
            if en_curso:
                st.button("⛔ DETENER", key=f"stop_{proyecto}", on_click=stop_work_callback, args=(USUARIO_ACTUAL, proyecto), use_container_width=True)
            else:
                disabled = (active_project is not None)
                st.button("▶ INICIAR", key=f"start_{proyecto}", on_click=start_work_callback, args=(USUARIO_ACTUAL, proyecto), disabled=disabled, use_container_width=True)

    # --- SECCIÓN TAREAS (F. Trabajo, Solo Facundo) ---
    render_tasks_section(USUARIO_ACTUAL)
    
    if active_project:
        time.sleep(10)
        st.rerun()

if __name__ == "__main__":
    main()