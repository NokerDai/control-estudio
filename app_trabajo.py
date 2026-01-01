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

def cargar_estilos():
    st.markdown("""
        <style>
        html, body, [class*="css"] { font-size: 18px !important; }
        h1 { font-size: 2.5rem !important; }
        h2 { font-size: 2rem !important; }
        h3 { font-size: 1.5rem !important; }

        /* Estilo de la tarjeta */
        .materia-card {
            background-color: #262730;
            border: 1px solid #464b5c;
            padding: 20px;
            border-radius: 15px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }
        .materia-title { font-size: 1.4rem; font-weight: bold; color: #ffffff; margin-bottom: 5px; }
        .info { font-size: 0.9rem; font-style: italic; color: #b0b0b0; margin-top: 4px; }
                
        /* EL TIEMPO */
        .materia-time { 
            font-size: 1.6rem; 
            font-weight: bold; 
            color: #00e676; 
            font-family: 'Courier New', monospace; 
            margin-bottom: 15px; 
        }

        .status-badge { display: inline-block; padding: 5px 10px; border-radius: 12px; font-size: 0.9rem; font-weight: bold; margin-bottom: 10px; }
        .status-active { background-color: rgba(0, 230, 118, 0.2); color: #00e676; border: 1px solid #00e676; }

        div.stButton > button { height: 3.5rem; font-size: 1.2rem !important; font-weight: bold !important; border-radius: 12px !important; }
        .materia-extra {
            font-size: 0.85rem;
            font-style: italic;
            color: #b0b0b0;
            margin-left: 6px;
        }
        </style>
    """, unsafe_allow_html=True)

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

# ------------------ RERUN HELPER ------------------
def pedir_rerun():
    st.session_state["_do_rerun"] = True

# ------------------ GOOGLE SHEETS SESSION ------------------
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
FILA_BASE = 3
FECHA_BASE = date(2026, 1, 1)
SHEET_FACUNDO = "F. Trabajo"
SHEET_MARCAS = "marcas"

def get_time_row():
    hoy = _argentina_now_global().date()
    delta = (hoy - FECHA_BASE).days
    return FILA_BASE + delta

TIME_ROW = get_time_row()
WEEK_RANGE = f"'{SHEET_MARCAS}'!R{TIME_ROW}"
RANGO_OBJ_REDES = f"'{SHEET_FACUNDO}'!F2"
RANGO_OBJ_TRABAJO = f"'{SHEET_FACUNDO}'!G2"

USERS = {
    "Facundo": {
        # Z10 para Redes, Z11 para Trabajo
        "Redes":   {"time": f"'{SHEET_FACUNDO}'!B{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!Z10"},
        "Trabajo": {"time": f"'{SHEET_FACUNDO}'!C{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!Z11"},
    }
}

# ------------------ CARGA UNIFICADA (cacheada) ------------------
@st.cache_data()
def cargar_datos_unificados():
    all_ranges = []
    mapa_indices = {"materias": {}, "extras": {}}
    idx = 0

    # --- Construir lista de ranges para materias (igual que antes) ---
    for user, materias in USERS.items():
        for m, info in materias.items():
            all_ranges.append(info["est"]); mapa_indices["materias"][(user, m, "est")] = idx; idx += 1
            all_ranges.append(info["time"]); mapa_indices["materias"][(user, m, "time")] = idx; idx += 1

    # Agregar rangos de objetivos
    all_ranges.append(RANGO_OBJ_REDES); mapa_indices["obj_redes"] = idx; idx += 1
    all_ranges.append(RANGO_OBJ_TRABAJO); mapa_indices["obj_trabajo"] = idx; idx += 1

    # --- Llamada única a Google Sheets ---
    try:
        res = sheets_batch_get(st.secrets["sheet_id"], all_ranges)
    except Exception as e:
        st.error(f"Error API Google Sheets: {e}")
        st.stop()

    values = res.get("valueRanges", [])
    def get_val(i, default=""):
        if i >= len(values): return default
        vr = values[i]
        rows = vr.get("values", [])
        if not rows: return default
        return rows[0][0] if rows[0] else default

    # --- Reconstruir estructura de usuarios como antes ---
    data_usuarios = {u: {"estado": {}, "tiempos": {}, "inicio_dt": None, "materia_activa": None} for u in USERS}
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

            if user == st.session_state.get("usuario_seleccionado") and str(raw_est).strip() != "":
                try:
                    inicio_dt = parse_datetime(raw_est)
                    materia_en_curso = m
                except Exception:
                    pass

    # --- Extraer los strings leídos en extras ---
    extras_res = {}
    for key, idx_pos in mapa_indices["extras"].items():
        extras_res[key] = get_val(idx_pos, "")

    # Obtener los objetivos
    obj_redes = parse_time_cell_to_seconds(get_val(mapa_indices["obj_redes"]))
    obj_trabajo = parse_time_cell_to_seconds(get_val(mapa_indices["obj_trabajo"]))

    # --- Guardar en session_state si corresponde (igual que antes) ---
    if "usuario_seleccionado" in st.session_state:
        st.session_state["materia_activa"] = materia_en_curso
        st.session_state["inicio_dt"] = inicio_dt

    return {
        "users_data": data_usuarios,
        "extras": extras_res,
        "obj_redes": obj_redes,
        "obj_trabajo": obj_trabajo
    }

def batch_write(updates):
    try:
        sheets_batch_update(st.secrets["sheet_id"], updates)
        cargar_datos_unificados.clear()
    except Exception as e:
        st.error(f"Error escribiendo Google Sheets: {e}")
        st.stop()

def start_materia_callback(usuario, materia):
    try:
        info = USERS[usuario][materia]
        now_str = ahora_str()
        updates = [(info["est"], now_str)] + [
            (m_datos["est"], "")
            for m_datos in USERS[usuario].values()
            if m_datos is not None and m_datos is not info
        ]
        batch_write(updates)
        st.session_state["materia_activa"] = materia
        st.session_state["inicio_dt"] = parse_datetime(now_str)
    except Exception as e:
        st.error(f"start_materia error: {e}")
    finally:
        pedir_rerun()

def stop_materia_callback(usuario, materia):
    try:
        info = USERS[usuario][materia]
        inicio = st.session_state.get("inicio_dt")
        prev_est = ""
        if inicio is None or st.session_state.get("materia_activa") != materia:
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
            try:
                res2 = sheets_batch_get(st.secrets["sheet_id"], [time_cell_for_row])
                vr2 = res2.get("valueRanges", [{}])[0]
                prev_raw = vr2.get("values", [[""]])[0][0] if vr2.get("values") else ""
            except:
                prev_raw = ""
            new_secs = parse_time_cell_to_seconds(prev_raw) + segs
            updates.append((time_cell_for_row, segundos_a_hms(new_secs)))

        updates.append((info["est"], ""))
        batch_write(updates)
        st.session_state["materia_activa"] = None
        st.session_state["inicio_dt"] = None
    except Exception as e:
        st.error(f"stop_materia error: {e}")
    finally:
        pedir_rerun()

def main():
    cargar_estilos()
    st.set_page_config(
        page_title="Trabajo",
        page_icon="💼",
    )

    if st.session_state.get("_do_rerun", False):
        st.session_state["_do_rerun"] = False
        st.rerun()

    try:
        params = st.query_params
    except Exception:
        params = st.experimental_get_query_params()

    if "usuario_seleccionado" not in st.session_state:
        def set_user_and_rerun(u):
            st.session_state["usuario_seleccionado"] = u
            st.rerun()

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

    # --- Carga de datos ---
    datos_globales = cargar_datos_unificados()
    datos = datos_globales["users_data"]
    obj_redes = datos_globales["obj_redes"]
    obj_trabajo = datos_globales["obj_trabajo"]
    obj_total = obj_redes + obj_trabajo

    USUARIO_ACTUAL = st.session_state["usuario_seleccionado"]

    materia_en_curso = st.session_state.get("materia_activa")
    inicio_dt = st.session_state.get("inicio_dt")

    if materia_en_curso is None:
        for m, est_raw in datos[USUARIO_ACTUAL]["estado"].items():
            if str(est_raw).strip() != "":
                try:
                    inicio_dt_sheet = parse_datetime(est_raw)
                    st.session_state["materia_activa"] = m
                    st.session_state["inicio_dt"] = inicio_dt_sheet
                    materia_en_curso = m
                    inicio_dt = inicio_dt_sheet
                except Exception:
                    pass
                break

    usuario_estudiando = materia_en_curso is not None

    # En la versión modificada MOSTRAMOS SÓLO el bloque "Hoy" arriba, y debajo las tarjetas individuales.
    placeholder_total = st.empty()
    placeholder_materias = {m: st.empty() for m in USERS[USUARIO_ACTUAL]}

    while True:
        tiempo_anadido_seg = 0
        if usuario_estudiando and inicio_dt is not None:
            tiempo_anadido_seg = int((_argentina_now_global() - inicio_dt).total_seconds())
        
        # Calcular métricas para la barra de progreso
        total_min = sum(hms_a_minutos(datos[USUARIO_ACTUAL]["tiempos"][m]) for m in USERS[USUARIO_ACTUAL]) + (tiempo_anadido_seg / 60)
        obj_min = obj_total / 60
        progreso_pct = min(total_min / max(1, obj_min), 1.0) * 100
        color_bar = "#00e676" if progreso_pct >= 90 else "#ffeb3b" if progreso_pct >= 50 else "#ff1744"
        total_hms = segundos_a_hms(int(total_min * 60))
        objetivo_hms = segundos_a_hms(obj_total)

        # --- Actualizar Placeholder Total (tarjeta Hoy) ---
        with placeholder_total.container():
            st.markdown(f"""
                <div style="background-color: #1e1e1e; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
                    <div style="font-size: 1.2rem; color: #aaa; margin-bottom: 5px;">Hoy</div>
                    <div style="width: 100%; font-size: 2.2rem; font-weight: bold; color: #fff; line-height: 1;">{total_hms}</div>
                    <div style="width:100%; background-color:#333; border-radius:10px; height:12px; margin: 15px 0;">
                        <div style="width:{progreso_pct}%; background-color:{color_bar}; height:100%; border-radius:10px; transition: width 0.5s;"></div>
                    </div>
                    <div style="display:flex; justify-content:space-between; color:#888;">
                        <div>Objetivo: {objetivo_hms}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

        # --- Mostrar tarjetas individuales para cada materia ---
        mis_materias = USERS[USUARIO_ACTUAL]
        for materia, info in mis_materias.items():
            base_seg = hms_a_segundos(datos[USUARIO_ACTUAL]["tiempos"][materia])
            tiempo_total_seg = base_seg
            en_curso = materia_en_curso == materia

            if en_curso:
                tiempo_total_seg += max(0, tiempo_anadido_seg)

            tiempo_total_hms = segundos_a_hms(tiempo_total_seg)
            info_trabajo = '<div class="info"> Si no hay trabajo en sí, tengo que usarlo para acompañar a papá o completar con Redes.</div>' if materia == 'Trabajo' else ''
            badge_html = '<div class="status-badge status-active">🟢 Trabajando...</div>' if en_curso else ''
            html_card = f"""<div class="materia-card"><div class="materia-title">{materia}{info_trabajo}</div>{badge_html}<div class="materia-time">{tiempo_total_hms}</div></div>"""

            with placeholder_materias[materia].container():
                st.markdown(html_card, unsafe_allow_html=True)

                key_start = sanitize_key(f"start_{USUARIO_ACTUAL}_{materia}")
                key_stop = sanitize_key(f"stop_{USUARIO_ACTUAL}_{materia}")
                key_disabled = sanitize_key(f"dis_{USUARIO_ACTUAL}_{materia}")

                cols = st.columns([1,1])
                with cols[0]:
                    if en_curso:
                        st.button(f"⛔ DETENER {materia[:14]}", key=key_stop, use_container_width=True,
                                  on_click=stop_materia_callback, args=(USUARIO_ACTUAL, materia))
                    else:
                        if materia_en_curso is None:
                            st.button("▶ INICIAR", key=key_start, use_container_width=True,
                                      on_click=start_materia_callback, args=(USUARIO_ACTUAL, materia))
                        else:
                            st.button("...", disabled=True, key=key_disabled, use_container_width=True)

                with cols[1]:
                    with st.expander("🛠️ Corregir tiempo manualmente"):
                        input_key = f"input_{sanitize_key(materia)}"
                        new_val = st.text_input("Tiempo (HH:MM:SS)", value=datos[USUARIO_ACTUAL]["tiempos"][materia], key=input_key)

                        def save_correction_callback(materia_key):
                            if st.session_state.get("materia_activa") is not None:
                                st.error("⛔ No podés corregir el tiempo mientras estás trabajando.")
                                pedir_rerun()
                                return

                            val = st.session_state.get(f"input_{sanitize_key(materia_key)}", "").strip()
                            if ":" not in val:
                                st.error("Formato inválido (debe ser HH:MM:SS)")
                                pedir_rerun()
                                return

                            try:
                                segs = hms_a_segundos(val)
                                hhmmss = segundos_a_hms(segs)
                                target_row = get_time_row()
                                time_cell_for_row = replace_row_in_range(USERS[USUARIO_ACTUAL][materia_key]["time"], target_row)
                                batch_write([(time_cell_for_row, hhmmss)])
                                st.success("Tiempo corregido correctamente.")
                            except Exception as e:
                                st.error(f"Error al corregir el tiempo: {e}")
                            finally:
                                pedir_rerun()

                        if en_curso or usuario_estudiando:
                            st.info("⛔ No podés corregir el tiempo mientras estás trabajando.")
                        else:
                            if st.button("Guardar Corrección", key=f"save_{sanitize_key(materia)}", on_click=save_correction_callback, args=(materia,)):
                                pass
                            
        # Si no hay nadie estudiando, este código sigue parándose aquí igual que antes
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
