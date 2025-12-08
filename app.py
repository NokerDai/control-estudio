# -------------------------------------------------------------
#   STREAMLIT - SISTEMA OPTIMIZADO DE LECTURA/ESCRITURA GOOGLE SHEETS
#   PARTE 1/?? — IMPORTS, CONFIG, HELPERS Y LECTURA OPTIMIZADA
# -------------------------------------------------------------

import streamlit as st
import requests
import json
from datetime import datetime, timedelta, timezone
import pytz

# -------------------------------------------------------------
# CONFIG STREAMLIT
# -------------------------------------------------------------
st.set_page_config(page_title="Seguimiento de Tiempos", layout="wide")

# -------------------------------------------------------------
# CONSTANTES
# -------------------------------------------------------------
TIME_ROW = 170   # fila base
SHEET_FACUNDO = "Facundo"
SHEET_IVAN = "Iván"
SHEET_MARCAS = "marcas"

# -------------------------------------------------------------
# USUARIOS (estructura original conservada)
# -------------------------------------------------------------
USERS = {
    "Facundo": {
        "Tecnología": {"est_col": "B", "time_col": "C"},
        "Historia":   {"est_col": "D", "time_col": "E"},
        "Economía":   {"est_col": "F", "time_col": "G"},
        "Física":     {"est_col": "H", "time_col": "I"},
    },
    "Iván": {
        "Biología":   {"est_col": "B", "time_col": "C"},
        "Filosofía":  {"est_col": "D", "time_col": "E"},
    }
}

# -------------------------------------------------------------
# SESIÓN HTTP REUTILIZADA (cacheada)
# -------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def get_sheets_session():
    s = requests.Session()
    return s

# -------------------------------------------------------------
# AUTENTICACIÓN
# -------------------------------------------------------------
def get_access_token():
    try:
        token_data = st.secrets["gcloud_service_account"]
    except Exception as e:
        st.error("❌ No se encontró la clave de servicio en st.secrets.")
        st.stop()

    auth_url = "https://oauth2.googleapis.com/token"
    auth_payload = {
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": token_data["assertion"]
    }

    r = requests.post(auth_url, data=auth_payload)
    if r.status_code != 200:
        st.error("❌ Error autenticando con Google: " + r.text)
        st.stop()
    return r.json()["access_token"]

# -------------------------------------------------------------
# HELPERS PARA RANGES
# -------------------------------------------------------------
def col_letter_to_index(col):
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch.upper()) - ord('A')) + 1
    return n

def col_index_to_letter(idx):
    result = ""
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        result = chr(rem + 65) + result
    return result

def next_col(col):
    return col_index_to_letter(col_letter_to_index(col) + 1)

# -------------------------------------------------------------
# HELPERS DE TIEMPO
# -------------------------------------------------------------
def parse_time_cell_to_seconds(val):
    """
    Acepta formatos: "H:MM:SS", "MM:SS", número, vacío, etc.
    """
    if not val:
        return 0
    v = str(val).strip()

    # ¿ya número?
    try:
        if ":" not in v:
            return int(float(v))
    except:
        pass

    # Parse H:M:S
    parts = v.split(":")
    if len(parts) == 3:
        try:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + int(s)
        except:
            return 0
    if len(parts) == 2:
        try:
            m, s = parts
            return int(m) * 60 + int(s)
        except:
            return 0

    return 0

def segundos_a_hms(seg):
    seg = int(seg)
    h = seg // 3600
    seg %= 3600
    m = seg // 60
    s = seg % 60
    return f"{h}:{m:02d}:{s:02d}"

def hms_a_minutos(hms_str):
    if not hms_str:
        return 0.0
    try:
        parts = hms_str.split(":")
        if len(parts) != 3:
            return 0.0
        h, m, s = map(int, parts)
        return h * 60 + m + (s / 60.0)
    except:
        return 0.0

# -------------------------------------------------------------
# PARSER DE DATETIME PARA ESTADOS
# -------------------------------------------------------------
def parse_datetime(dt_str):
    if not dt_str:
        raise ValueError("empty dt_str")
    from dateutil import parser
    dt = parser.parse(dt_str)
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=timezone.utc).astimezone(pytz.timezone("America/Argentina/Buenos_Aires"))
    else:
        dt = dt.astimezone(pytz.timezone("America/Argentina/Buenos_Aires"))
    return dt

def _argentina_now_global():
    return datetime.now(pytz.timezone("America/Argentina/Buenos_Aires"))

# -------------------------------------------------------------
# GOOGLE SHEETS CALLS (batchGet / batchUpdate)
# -------------------------------------------------------------
def sheets_batch_get(spreadsheet_id, ranges):
    access_token = get_access_token()
    session = get_sheets_session()

    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values:batchGet"

    # armar query string
    params = "&".join([f"ranges={r}" for r in ranges])
    full_url = f"{url}?{params}"

    r = session.get(full_url, headers={"Authorization": f"Bearer {access_token}"})
    if r.status_code != 200:
        raise RuntimeError(f"batchGet error: {r.text}")
    return r.json()

def sheets_batch_update(spreadsheet_id, data):
    access_token = get_access_token()
    session = get_sheets_session()

    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}:batchUpdate"
    r = session.post(url, headers={
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }, data=json.dumps(data))

    if r.status_code != 200:
        raise RuntimeError(f"batchUpdate error: {r.text}")
    return r.json()

# -------------------------------------------------------------
# NUEVA LECTURA OPTIMIZADA (UNA SOLA VEZ POR RERUN - CACHE)
# -------------------------------------------------------------
@st.cache_data(ttl=30, show_spinner=False)
def cargar_todo_cached(sheet_id, time_row):
    """
    Lee datos en **3 batchGet** (una por hoja), en lugar de decenas de llamadas individuales.
    Devuelve:
      - data: estructura con estado/tiempos por usuario/materia
      - resumen_marcas: per_min y objetivos
    """

    # 3 lecturas grandes
    ranges = [
        f"'{SHEET_FACUNDO}'!B{time_row}:Z{time_row}",
        f"'{SHEET_IVAN}'!B{time_row}:Z{time_row}",
        f"'{SHEET_MARCAS}'!B{time_row}:Z{time_row}",
    ]

    try:
        res = sheets_batch_get(sheet_id, ranges)
    except Exception as e:
        raise RuntimeError(f"❌ Error leyendo Google Sheets (batchGet): {e}")

    # valueRanges alineados con "ranges"
    vr = res.get("valueRanges", [])

    fac_vals   = vr[0].get("values", [[""]])[0] if len(vr) > 0 else [""]
    iv_vals    = vr[1].get("values", [[""]])[0] if len(vr) > 1 else [""]
    marcas_vals = vr[2].get("values", [[""]])[0] if len(vr) > 2 else [""]

    data = {u: {"estado": {}, "tiempos": {}} for u in USERS}

    # -------------------------
    # MAPEO FACUNDO
    # -------------------------
    # Usamos los offsets de la definición original de las columnas
    for materia, info in USERS["Facundo"].items():
        est_col = info["est_col"]
        time_col = info["time_col"]
        idx_est = col_letter_to_index(est_col) - 2  # restamos 2 porque B=col2 → index 0
        idx_time = col_letter_to_index(time_col) - 2

        est_val = fac_vals[idx_est] if idx_est < len(fac_vals) else ""
        time_raw = fac_vals[idx_time] if idx_time < len(fac_vals) else ""

        data["Facundo"]["estado"][materia] = est_val or ""
        data["Facundo"]["tiempos"][materia] = segundos_a_hms(parse_time_cell_to_seconds(time_raw))

    # -------------------------
    # MAPEO IVÁN
    # -------------------------
    for materia, info in USERS["Iván"].items():
        est_col = info["est_col"]
        time_col = info["time_col"]
        idx_est = col_letter_to_index(est_col) - 2
        idx_time = col_letter_to_index(time_col) - 2

        est_val = iv_vals[idx_est] if idx_est < len(iv_vals) else ""
        time_raw = iv_vals[idx_time] if idx_time < len(iv_vals) else ""

        data["Iván"]["estado"][materia] = est_val or ""
        data["Iván"]["tiempos"][materia] = segundos_a_hms(parse_time_cell_to_seconds(time_raw))

    # -------------------------
    # MARCAS Y OBJETIVOS
    # -------------------------
    # Ajusta aquí según columnas reales:
    resumen_marcas = {
        "Facundo": {"per_min": 0},
        "Iván": {"per_min": 0},
        "objetivos": {"Facundo": 0, "Iván": 0},
    }

    try: resumen_marcas["Facundo"]["per_min"] = float(marcas_vals[1])
    except: pass
    try: resumen_marcas["Iván"]["per_min"] = float(marcas_vals[2])
    except: pass
    try: resumen_marcas["objetivos"]["Facundo"] = float(marcas_vals[3])
    except: pass
    try: resumen_marcas["objetivos"]["Iván"] = float(marcas_vals[4])
    except: pass

    return data, resumen_marcas

# -------------------------------------------------------------
# WRAPPER PARA USAR EN EL RESTO DEL CÓDIGO
# -------------------------------------------------------------
def cargar_todo():
    try:
        data, resumen = cargar_todo_cached(st.secrets["sheet_id"], TIME_ROW)
        st.session_state["last_cargar_todo"] = {"data": data, "resumen": resumen, "time_row": TIME_ROW}
        return data
    except Exception as e:
        st.error(f"❌ Error en cargar_todo optimizado: {e}")
        st.stop()

# -------------------------
# Escritura en Google Sheets (values:batchUpdate)
# -------------------------
def sheets_values_batch_update(spreadsheet_id, payload):
    """
    payload = {
      "valueInputOption": "USER_ENTERED",
      "data": [{"range": "Hoja!A1", "values": [["valor"]]}, ...]
    }
    """
    access_token = get_access_token()
    session = get_sheets_session()
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values:batchUpdate"
    r = session.post(url, headers={
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }, data=json.dumps(payload))

    if r.status_code not in (200, 201):
        raise RuntimeError(f"values:batchUpdate error: {r.status_code} {r.text}")
    return r.json()

def batch_write(updates):
    """
    updates: list of (range_str, value)
    Escribe todos los updates en UNA llamada a values:batchUpdate.
    """
    if not updates:
        return None
    data = {
        "valueInputOption": "USER_ENTERED",
        "data": []
    }
    for rng, val in updates:
        # mantener valor como string dentro de una celda
        data["data"].append({"range": rng, "values": [[val]]})
    return sheets_values_batch_update(st.secrets["sheet_id"], data)

# -------------------------
# Utiles para construir ranges (mantener compatibilidad con layout)
# -------------------------
def cell_range(sheet_name, col, row):
    return f"'{sheet_name}'!{col}{row}"

def replace_row_in_range(range_str, new_row):
    # si range_str es como 'Hoja'!B170 -> reemplaza el número final
    import re
    return re.sub(r'(\d+)(\s*$)', str(new_row), range_str)

# -------------------------
# Limpiar marcas de "estudiando" para un diccionario de materias
# -------------------------
def limpiar_estudiando(materias):
    updates = []
    for materia, info in materias.items():
        # info debe contener 'est_range' o 'est_col'
        est_col = info.get("est_col")
        if not est_col:
            continue
        rng = cell_range(SHEET_MARCAS, est_col, TIME_ROW) if info.get("sheet") == SHEET_MARCAS else cell_range(info.get("sheet", SHEET_FACUNDO), est_col, TIME_ROW)
        updates.append((rng, ""))
    if updates:
        batch_write(updates)

# -------------------------
# Calcular métricas (usa datos ya cargados por cargar_todo_cached)
# -------------------------
def calcular_metricas(usuario, datos_local=None, resumen_local=None):
    """
    Devuelve:
      total_money, per_min, objetivo_minutos, total_minutos, progreso_money_actual
    """
    datos_local = datos_local or st.session_state.get("last_cargar_todo", {}).get("data", {})
    resumen_local = resumen_local or st.session_state.get("last_cargar_todo", {}).get("resumen", {})

    per_min = parse_float_or_zero(resumen_local.get(usuario, {}).get("per_min", 0))
    objetivo_min = resumen_local.get("objetivos", {}).get(usuario, 0.0)

    total_min = 0.0
    progreso_money_actual = 0.0
    last_progreso_minutes = 0.0

    for materia, meta in USERS[usuario].items():
        base_min = hms_a_minutos(datos_local[usuario]["tiempos"].get(materia, "00:00:00"))
        est_raw = datos_local[usuario]["estado"].get(materia, "")
        progreso_min = 0.0
        if str(est_raw).strip() != "":
            try:
                inicio = parse_datetime(est_raw)
                progreso_min = max(0.0, (_argentina_now_global() - inicio).total_seconds() / 60.0)
                last_progreso_minutes = progreso_min
            except Exception:
                progreso_min = 0.0
        total_min += base_min + progreso_min

    total_money = total_min * per_min
    progreso_money_actual = last_progreso_minutes * per_min

    return total_money, per_min, objetivo_min, total_min, progreso_money_actual

# -------------------------
# Función que acumula tiempo manual (usada por corrección o procesos)
# -------------------------
def acumular_tiempo_por_segmento(info, p_inicio, p_fin):
    """
    info: dict con keys 'time_col' y 'sheet' (opcional)
    p_inicio, p_fin: datetime timezone-aware
    """
    segs = int((p_fin - p_inicio).total_seconds())
    # target row según p_inicio
    target_row = TIME_ROW + (p_inicio.date() - datetime.now(pytz.timezone("America/Argentina/Buenos_Aires")).date()).days
    # construir range para la celda time de ese día usando columna de la materia
    time_col = info.get("time_col")
    sheet = info.get("sheet", SHEET_FACUNDO)
    time_cell = cell_range(sheet, time_col, target_row)
    # leer valor previo (intentamos evitar lectura adicional: obtener desde session_state si está)
    prev_raw = ""
    # intentamos encontrar en cache: last_cargar_todo no tiene filas por día distintas, así que leemos la celda
    try:
        resp = sheets_batch_get(st.secrets["sheet_id"], [time_cell])
        vr = resp.get("valueRanges", [{}])[0]
        prev_raw = vr.get("values", [[""]])[0][0] if vr.get("values") else ""
    except Exception:
        prev_raw = ""
    prev_secs = parse_time_cell_to_seconds(prev_raw)
    new_secs = prev_secs + segs
    return time_cell, segundos_a_hms(new_secs)

# -------------------------
# Manejo de START / STOP (UI actions)
# -------------------------
def start_materia(usuario, materia):
    info = USERS[usuario][materia]
    # limpiar otras marcas del usuario
    # construir ranges para limpiar: asumimos que est_col apunta a la columna de est en TIME_ROW
    updates = []
    for m, inf in USERS[usuario].items():
        est_col = inf.get("est_col")
        sheet = inf.get("sheet", SHEET_FACUNDO)
        if est_col:
            updates.append((cell_range(sheet, est_col, TIME_ROW), ""))
    # poner marca actual en la materia seleccionada
    est_col_sel = info.get("est_col")
    sheet_sel = info.get("sheet", SHEET_FACUNDO)
    updates.append((cell_range(sheet_sel, est_col_sel, TIME_ROW), _argentina_now_global().isoformat(sep=" ", timespec="seconds")))
    batch_write(updates)
    # invalidar cache para forzar recarga la próxima render (si quieres mantener cache por ttl, puedes omitirl)
    try:
        st.cache_data.clear()
    except Exception:
        pass

def stop_materia(usuario, materia):
    info = USERS[usuario][materia]
    # leer marca de inicio desde la celda correspondiente en sheets (o desde cache si lo tienes)
    est_col = info.get("est_col")
    sheet = info.get("sheet", SHEET_FACUNDO)
    est_cell = cell_range(sheet, est_col, TIME_ROW)
    try:
        resp = sheets_batch_get(st.secrets["sheet_id"], [est_cell])
        vr = resp.get("valueRanges", [{}])[0]
        est_raw = vr.get("values", [[""]])[0][0] if vr.get("values") else ""
    except Exception:
        est_raw = ""

    if not est_raw or str(est_raw).strip() == "":
        # nada que hacer
        return

    try:
        inicio = parse_datetime(est_raw)
    except Exception:
        # limpiar por seguridad
        batch_write([(est_cell, "")])
        return

    fin = _argentina_now_global()
    if fin <= inicio:
        # limpiar marca y salir
        batch_write([(est_cell, "")])
        return

    # manejar cruzar medianoche: dividir en segmentos
    midnight = datetime.combine(inicio.date() + timedelta(days=1), datetime.min.time())
    midnight = pytz.timezone("America/Argentina/Buenos_Aires").localize(midnight)
    partes = []
    if inicio.date() == fin.date():
        partes.append((inicio, fin))
    else:
        partes.append((inicio, midnight))
        partes.append((midnight, fin))

    updates = []
    for p_inicio, p_fin in partes:
        time_cell, new_hms = acumular_tiempo_por_segmento(info, p_inicio, p_fin)
        updates.append((time_cell, new_hms))

    # limpiar marca de inicio
    updates.append((est_cell, ""))

    # escribir todo junto
    batch_write(updates)
    # intentar invalidar cache local para que próxima carga traiga datos actualizados
    try:
        st.cache_data.clear()
    except Exception:
        pass

# -------------------------
# UI Principal (simplificada)
# -------------------------
def ui_principal():
    st.title("Tiempo de Estudio — Optimizado")
    # seleccionar usuario
    if "usuario_seleccionado" not in st.session_state:
        col1, col2 = st.columns(2)
        with col1:
            if st.button("👤 Facundo", use_container_width=True):
                st.session_state["usuario_seleccionado"] = "Facundo"
                st.rerun()
        with col2:
            if st.button("👤 Iván", use_container_width=True):
                st.session_state["usuario_seleccionado"] = "Iván"
                st.rerun()
        st.stop()

    usuario = st.session_state["usuario_seleccionado"]

    # cargar datos (cacheados)
    datos = cargar_todo()  # ya guarda en st.session_state['last_cargar_todo']
    resumen = st.session_state.get("last_cargar_todo", {}).get("resumen", {})

    # métricas rápidas
    total_money, per_min, objetivo_min, total_min, progreso_money = calcular_metricas(usuario, datos, resumen)

    st.metric(label=f"{usuario} — Total (min)", value=f"{int(total_min)} min", delta=f"${total_money:.2f}")
    st.write(f"Tarifa por minuto: ${per_min:.2f}  ·  Objetivo (min): {objetivo_min}")

    # Listado de materias con botones
    st.subheader("Materias")
    materia_en_curso = None
    for m, info in USERS[usuario].items():
        est_val = datos[usuario]["estado"].get(m, "")
        tiempo_acum = datos[usuario]["tiempos"].get(m, "00:00:00")
        en_curso = str(est_val).strip() != ""
        cols = st.columns([3,1])
        with cols[0]:
            st.markdown(f"**{m}** — {tiempo_acum} {'(estudiando)' if en_curso else ''}")
        with cols[1]:
            if en_curso:
                if st.button(f"⛔ Detener", key=f"stop_{usuario}_{m}"):
                    stop_materia(usuario, m)
                    st.rerun()
            else:
                if st.button(f"▶ Start", key=f"start_{usuario}_{m}"):
                    start_materia(usuario, m)
                    st.rerun()

        # Expander corrección manual
        with st.expander(f"Corregir tiempo — {m}"):
            new_val = st.text_input("Tiempo (HH:MM:SS)", value=tiempo_acum, key=f"input_{usuario}_{m}")
            if st.button("Guardar corrección", key=f"save_{usuario}_{m}"):
                # escribir directamente en la celda time de TIME_ROW
                time_col = info.get("time_col")
                sheet = info.get("sheet", SHEET_FACUNDO)
                target = cell_range(sheet, time_col, TIME_ROW)
                batch_write([(target, new_val)])
                # limpiar cache y recargar
                try:
                    st.cache_data.clear()
                except:
                    pass
                st.rerun()

# -------------------------
# Helpers pequenos
# -------------------------
def parse_float_or_zero(s):
    try:
        return float(str(s).replace(",", "."))
    except:
        return 0.0

AUTOREFRESH_INTERVAL_DEFAULT = 180_000  # 5 minutos en ms
AUTOREFRESH_INTERVAL_ACTIVE = 120_000    # 1 minuto cuando hay actividad (opcional)
MIN_SECONDS_BETWEEN_FORCED_RELOADS = 5  # para evitar loops (segundos)

def should_autorefresh():
    """
    Decide si inyectamos st_autorefresh con menor intervalo (actividad) o mayor (inactivo).
    También evita refrescar si el último refresh fue muy reciente.
    """
    last = st.session_state.get("_last_refresh_ts", 0)
    now = time.time()
    if now - last < MIN_SECONDS_BETWEEN_FORCED_RELOADS:
        return None  # bloquear refresh inmediato

    # Si hay datos en cache, chequear si alguien está estudiando
    last_data = st.session_state.get("last_cargar_todo", {}).get("data", {})
    activo = False
    for udata in last_data.values():
        for v in udata.get("estado", {}).values():
            if str(v).strip() != "":
                activo = True
                break
        if activo:
            break

    # actualizar timestamp de intento
    st.session_state["_last_refresh_ts"] = now

    return AUTOREFRESH_INTERVAL_ACTIVE if activo else AUTOREFRESH_INTERVAL_DEFAULT

# -------------------------
# Widget bridge JS (opcional)
# -------------------------
def inject_widget_bridge(total_hms, money, progress_pct, week_val, goal_str, other_total_hms="00:00:00", other_money=0.0, other_progress=0):
    """
    Injerta un pequeño script que, si existe window.AndroidBridge, llama a updateWidgetData(...)
    Mantener height=0 para no afectar layout.
    """
    js_code = f"""
    <script>
        if (window.AndroidBridge && typeof window.AndroidBridge.updateWidgetData === 'function') {{
            try {{
                window.AndroidBridge.updateWidgetData(
                    "{total_hms}",
                    {money},
                    {int(progress_pct)},
                    {week_val},
                    "{goal_str}",
                    "{other_total_hms}",
                    {other_money},
                    {int(other_progress)}
                );
            }} catch(e) {{
                console.warn("Widget bridge error", e);
            }}
        }}
    </script>
    """
    import streamlit.components.v1 as components
    components.html(js_code, height=0)

# -------------------------
# Visual helpers
# -------------------------
def progress_bar_html(pct, color="#00e676", height_px=12):
    pct = max(0, min(100, float(pct)))
    return f"""
    <div style="width:100%; background-color:#333; border-radius:8px; height:{height_px}px;">
       <div style="width:{pct}%; background-color:{color}; height:100%; border-radius:8px;"></div>
    </div>
    """

def money_str(val):
    try:
        return f"${float(val):.2f}"
    except:
        return "$0.00"

# -------------------------
# Tips de configuración (mostrar como expander)
# -------------------------
def render_tips():
    with st.expander("🛠️ Tips de configuración y dónde ajustar columnas"):
        st.markdown("""
        - Si tu layout cambia (columnas diferentes), ajusta `USERS` en la PARTE 1 para que `est_col` y `time_col`
          correspondan a las columnas correctas.
        - TIME_ROW define la fila base donde guardas los acumulados por día. Cámbialo si tu fila base varía.
        - `cargar_todo_cached` agrega un TTL de 30s: modifícalo si necesitas más/menos latencia.
        - Reduce `AUTOREFRESH_INTERVAL_DEFAULT` si quieres que la app sea más reactiva pero a costo de más consultas.
        - Si tienes muchos usuarios/clientes, considera mover agregaciones a un endpoint servidor (Cloud Function).
        """)

# -------------------------
# Main consolidado
# -------------------------
def main():
    # CSS liviano (puedes extender)
    st.markdown("""
    <style>
      .title-compact { font-size: 1.8rem; font-weight:700; margin-bottom:6px; }
      .muted { color:#999; font-size:0.9rem; }
      .card { background:#111; padding:12px; border-radius:10px; margin-bottom:10px; }
    </style>
    """, unsafe_allow_html=True)

    # manejar autorefresh inteligente
    chosen_interval = should_autorefresh()
    if chosen_interval:
        try:
            # st_autorefresh requiere import local (evitar en top-level si no se usa)
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=chosen_interval, key="smart_autorefresh")
        except Exception:
            # si no está disponible, no es crítico
            pass

    # UI principal (llama a ui_principal definido en PARTE 2)
    ui_principal()

    # Mostrar tips
    render_tips()

    # Si quieres inyectar datos al widget Android (opcional), puedes hacerlo al final:
    try:
        usuario = st.session_state.get("usuario_seleccionado")
        if usuario:
            datos = st.session_state.get("last_cargar_todo", {}).get("data", {})
            resumen = st.session_state.get("last_cargar_todo", {}).get("resumen", {})
            if datos and resumen:
                total_money, per_min, objetivo_min, total_min, progreso_money = calcular_metricas(usuario, datos, resumen)
                goal_str = f"{int(objetivo_min)} min | {money_str(per_min * objetivo_min)}"
                inject_widget_bridge(segundos_a_hms(int(total_min*60)), total_money, (total_money / max(1, per_min*objetivo_min))*100 if per_min*objetivo_min else 0, 0.0, goal_str)
    except Exception:
        pass

# -------------------------
# Ejecutar main y manejo de errores
# -------------------------
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        st.error(f"Error crítico: {e}")
        # limpiar estado sensible y forzar recarga suave
        try:
            st.session_state.clear()
        except:
            pass
        st.rerun()

