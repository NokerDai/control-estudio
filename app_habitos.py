import streamlit as st
import gspread
from datetime import datetime, timedelta
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

import json

# ---------------------------------------------------------------
# BLOQUEO POR CONTRASEÑA
# ---------------------------------------------------------------
def check_password():
    """Devuelve True si la contraseña es correcta."""

    # 1) Si ya está logueado, no pedirla de nuevo
    if "pw_correct" in st.session_state and st.session_state.pw_correct:
        return True

    # 2) Interfaz normal de contraseña
    st.title("🔒 Acceso protegido")
    password = st.text_input("Contraseña:", type="password")
    if st.button("Entrar"):
        if password == st.secrets["auth"]["password"]:
            st.session_state.pw_correct = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")

    return False

def run():
    # Si la contraseña no es correcta → NO seguir cargando la app
    if not check_password():
        st.stop()

    # -------------------------------------------------------------------
    # ZONA HORARIA ARGENTINA
    # -------------------------------------------------------------------
    def _argentina_now_global():
        # Unificado a Córdoba para ser consistente con app_estudio.py
        if ZoneInfo is not None:
            return datetime.now(ZoneInfo('America/Argentina/Cordoba'))
        if 'pytz' in globals() and pytz is not None:
            return datetime.now(pytz.timezone('America/Argentina/Cordoba'))
        return datetime.now()

    def get_argentina_time_str():
        # Función para obtener la hora actual (no usada para el log, solo informativa)
        return _argentina_now_global().strftime('%H:%M:%S')

    def get_argentina_date_str():
        dt = _argentina_now_global()
        return f"{dt.day:02d}/{dt.month:02d}"

    # -------------------------------------------------------------------
    # CONFIG DESDE SECRETS
    # -------------------------------------------------------------------
    _gcp_secrets = st.secrets.get("gcp", {}) if hasattr(st, "secrets") else {}

    GOOGLE_SHEET_NAME = _gcp_secrets.get("google_sheet_name", "Tiempo de Estudio")
    WORKSHEET_NAME = _gcp_secrets.get("worksheet_name", "F. Extra")
    BOUNDARY_COLUMN = _gcp_secrets.get("boundary_column", "Extracurricular")
    
    STREAK_HABIT_NAME = _gcp_secrets.get("streak_habit_name")
    
    # -------------------------------------------------------------------
    # CONEXIÓN A GOOGLE SHEETS
    # -------------------------------------------------------------------
    @st.cache_resource
    def connect_to_google_sheets():
        try:
            # 1) Intentar desde secrets
            service_account_data = None
            if "service_account" in _gcp_secrets:
                sa = _gcp_secrets["service_account"]
                if isinstance(sa, str):
                    service_account_data = json.loads(sa)
                elif isinstance(sa, dict):
                    service_account_data = sa

            if service_account_data:
                gc = gspread.service_account_from_dict(service_account_data)
                spreadsheet = gc.open(GOOGLE_SHEET_NAME)
                worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
                return worksheet

            st.warning("No hay credenciales en secrets. Agregá [gcp].service_account.")
            return None

        except Exception as e:
            st.error(f"Error al conectar a Google Sheets: {e}")
            return None

    # -------------------------------------------------------------------
    # LECTURA ESPECÍFICA DE RACHA (PARA EL CÁLCULO DE LA NUEVA RACHA)
    # Lee el valor del HÁBITO de AYER
    # -------------------------------------------------------------------
    def get_yesterdays_streak(worksheet, habit_name):
        """Lee el número de racha (que está en la columna del hábito) del día anterior."""
        if worksheet is None: 
            st.error("DEBUG RACHA: Worksheet es None.")
            return 0

        yesterday_dt = _argentina_now_global().date() - timedelta(days=1)
        yesterday_str = f"{yesterday_dt.day:02d}/{yesterday_dt.month:02d}"
        
        st.info(f"DEBUG AYER: Buscando racha de ayer: {yesterday_str} en columna '{habit_name}'")

        try:
            headers = worksheet.row_values(1)
            if habit_name not in headers:
                st.warning(f"DEBUG AYER: Columna de Hábito '{habit_name}' no encontrada. Retorna 0.")
                return 0 

            streak_col_index = headers.index(habit_name) + 1 

            all_dates = worksheet.col_values(1)
            if yesterday_str not in all_dates:
                st.warning(f"DEBUG AYER: Fecha de ayer '{yesterday_str}' no encontrada en Col A. Retorna 0.")
                return 0 

            yesterday_row_index = all_dates.index(yesterday_str) + 1 

            streak_val = worksheet.cell(yesterday_row_index, streak_col_index).value
            
            st.info(f"DEBUG AYER: Valor crudo leído de celda ({yesterday_row_index}, {streak_col_index}): '{streak_val}'")

            if streak_val:
                try:
                    stripped_val = streak_val.strip()
                    if not stripped_val: return 0
                        
                    final_streak = int(stripped_val)
                    st.success(f"DEBUG AYER: Conversión exitosa. Racha de ayer: {final_streak}")
                    return final_streak
                except ValueError:
                    st.error(f"DEBUG AYER: ERROR: ValueError al convertir '{stripped_val}' a int. Retorna 0.")
                    return 0
            else:
                st.warning("DEBUG AYER: Celda de racha de ayer vacía o None. Retorna 0.")
                return 0

        except Exception as e:
            st.error(f"DEBUG AYER: Error general en lectura de racha ({e.__class__.__name__}): {e}")
            return 0
            
    # -------------------------------------------------------------------
    # LOG DE RACHA 
    # -------------------------------------------------------------------
    def log_habit_streak(habit_name, worksheet):
        """Calcula new_streak = yesterday_streak + 1 y actualiza la celda del hábito con el número de racha."""
        try:
            if worksheet is None: return

            today_str = get_argentina_date_str()
            
            # Obtiene la racha de AYER para la base del cálculo de HOY
            current_streak = get_yesterdays_streak(worksheet, habit_name) 
            new_streak = current_streak + 1

            st.info(f"DEBUG LOG: Racha de ayer: {current_streak}. Nueva racha a registrar HOY: {new_streak}")

            # 1. Encontrar la fila de hoy
            all_dates = worksheet.col_values(1)
            if today_str not in all_dates:
                st.error(f"La fecha de hoy ({today_str}) no está en la columna A.")
                return
            date_row = all_dates.index(today_str) + 1

            # 2. Encontrar/Crear la columna del Hábito/Racha
            headers = worksheet.row_values(1)
            if habit_name in headers:
                habit_col_idx = headers.index(habit_name) + 1
            else:
                # Lógica para encontrar el índice (Boundary)
                if BOUNDARY_COLUMN in headers:
                    boundary = headers.index(BOUNDARY_COLUMN)
                    habit_col_idx = boundary + 1 
                else:
                    habit_col_idx = len(headers) + 1 
                
                worksheet.update_cell(1, habit_col_idx, habit_name)
                headers = worksheet.row_values(1) 

            # 3. Actualizar la celda del Hábito con el número de la NUEVA RACHA
            if habit_name in headers:
                 habit_col_idx = headers.index(habit_name) + 1
                 worksheet.update_cell(date_row, habit_col_idx, new_streak)
                 st.success(f"DEBUG LOG: Valor {new_streak} registrado con éxito en celda ({date_row}, {habit_col_idx}).")
            else:
                st.error(f"Error interno: No se pudo encontrar la columna para el hábito '{habit_name}'.")

            st.session_state.needs_rerun = True

        except Exception as e:
            st.error(f"Error al registrar la racha: {e}")


    # -------------------------------------------------------------------
    # HÁBITOS DESDE SECRETS
    # -------------------------------------------------------------------
    def load_habits():
        """Carga todos los hábitos, pero filtra el hábito de racha para el grid."""
        try:
            raw_habits = _gcp_secrets.get("habits", [])
            if isinstance(raw_habits, list):
                st.session_state.all_habits = raw_habits
                return [h for h in raw_habits if h["name"] != STREAK_HABIT_NAME]
            st.error("El campo [gcp].habits en secrets no es una lista válida.")
            return []
        except Exception as e:
            st.error(f"Error al cargar hábitos desde secrets: {e}")
            return []

    # -------------------------------------------------------------------
    # CONFIGURACIÓN DEL ESTADO DIARIO (LÓGICA CORREGIDA)
    # Prioridad: 1. Leer HOY. 2. Leer AYER (para el botón).
    # -------------------------------------------------------------------
    def setup_daily_state(worksheet):
        today_str = get_argentina_date_str()
        
        streak_habit_completed_today = False
        current_streak = 0
        
        # 1. Intentar establecer la racha A PARTIR DE HOY (el valor registrado)
        if worksheet is not None:
            try:
                all_dates = worksheet.col_values(1)
                date_row_index = all_dates.index(today_str) if today_str in all_dates else -1
                
                if date_row_index != -1:
                    today_row = worksheet.row_values(date_row_index + 1)
                    headers = worksheet.row_values(1)
                    
                    if STREAK_HABIT_NAME in headers:
                        col_idx = headers.index(STREAK_HABIT_NAME)
                        
                        if col_idx < len(today_row) and today_row[col_idx].strip():
                            value_today_str = today_row[col_idx].strip()
                            
                            st.info(f"DEBUG ESTADO: Valor HOY leído: '{value_today_str}'")

                            try:
                                value_today = int(value_today_str)
                                
                                if value_today > 0:
                                    streak_habit_completed_today = True
                                    # Si HOY tiene un valor > 0, ese es el current_streak a mostrar
                                    current_streak = value_today
                                    st.success(f"DEBUG ESTADO: Racha a mostrar (valor de HOY): {current_streak}")
                                else:
                                    st.warning("DEBUG ESTADO: Valor HOY es 0 o vacío. Usando racha de AYER.")
                            except:
                                # Si no es un número (ej. "n/a" o texto), lo consideramos completo
                                streak_habit_completed_today = True
                                st.error("DEBUG ESTADO: Valor HOY no es número (bloqueando botón).")
                        else:
                            st.warning("DEBUG ESTADO: Celda de HOY vacía. Usando racha de AYER.")
                            
                # 2. Si HOY no está completado, obtenemos la racha de AYER para la visualización del botón
                if not streak_habit_completed_today:
                    current_streak = get_yesterdays_streak(worksheet, STREAK_HABIT_NAME)
                    st.info(f"DEBUG ESTADO: Hábito pendiente. Racha base para botón (valor de AYER): {current_streak}")

            except ValueError:
                st.warning(f"La fecha de hoy ({today_str}) no está en la columna A.")
            except Exception as e:
                st.error(f"Error al leer la planificación: {e}")

        # El resto de la lógica (hábitos del grid) se mantiene
        pending_habits_list = []
        if worksheet is not None:
            # Lógica para determinar el resto de hábitos pendientes
            try:
                all_dates = worksheet.col_values(1)
                date_row_index = all_dates.index(today_str) if today_str in all_dates else -1
                
                if date_row_index != -1:
                    today_row = worksheet.row_values(date_row_index + 1)
                    headers = worksheet.row_values(1)
                    
                    for habit in st.session_state.all_habits:
                        name = habit["name"]
                        if name == STREAK_HABIT_NAME:
                            continue 

                        if name in headers:
                            col_idx = headers.index(name)
                            if col_idx >= len(today_row) or not today_row[col_idx].strip():
                                pending_habits_list.append(name)
                        else:
                            pending_habits_list.append(name)
            except:
                 pass
        
        st.session_state.streak_habit_info = {
            "habit_name": STREAK_HABIT_NAME,
            "is_completed": streak_habit_completed_today,
            "current_streak": current_streak
        }
        st.session_state.todays_pending_habits = pending_habits_list


    def log_habit_grid(habit_name, worksheet):
        try:
            if worksheet is not None:
                today_str = get_argentina_date_str()
                all_dates = worksheet.col_values(1)
                date_row = all_dates.index(today_str) + 1
                headers = worksheet.row_values(1)

                log_value = 1 

                if habit_name in headers:
                    col = headers.index(habit_name) + 1
                else:
                    if BOUNDARY_COLUMN in headers:
                        boundary = headers.index(BOUNDARY_COLUMN)
                        col = None
                        for idx in range(1, boundary + 1):
                            if idx - 1 >= len(headers) or not headers[idx - 1].strip():
                                col = idx
                                break
                        if col is None:
                            col = boundary + 1
                    else:
                        col = len(headers) + 1
                
                worksheet.update_cell(date_row, col, log_value)

                if habit_name not in headers:
                    worksheet.update_cell(1, col, habit_name)

            if habit_name in st.session_state.todays_pending_habits:
                st.session_state.todays_pending_habits.remove(habit_name)

            st.session_state.needs_rerun = True

        except Exception as e:
            st.error(f"Error al registrar el hábito: {e}")

    # -------------------------------------------------------------------
    # UI PRINCIPAL
    # -------------------------------------------------------------------
    st.title("📅 Hábitos Básicos")

    sheet = connect_to_google_sheets()

    # Cargar hábitos desde secrets
    if 'habits' not in st.session_state:
        st.session_state.habits = load_habits()
        st.session_state.all_habits = _gcp_secrets.get("habits", [])

    if 'all_habits' not in st.session_state:
        st.session_state.all_habits = _gcp_secrets.get("habits", [])

    setup_daily_state(sheet)

    # Obtener el estado del hábito de racha
    streak_info = st.session_state.streak_habit_info
    HABIT_NAME = streak_info["habit_name"]
    streak = streak_info["current_streak"]
    completed = streak_info["is_completed"]
    
    # -------------------------
    #     HÁBITO DE RACHA
    # -------------------------
    STREAK_GOAL = 30 # Objetivo de la barra de progreso (ajustable)
    streak_pct = min(streak / STREAK_GOAL, 1.0) * 100
    
    status_text = f"{HABIT_NAME} - Día {streak} 🔥"
    
    st.markdown(f"""
        <div style="background-color: #262730; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
            <div style="font-size: 1.1rem; color: #aaa; margin-bottom: 8px;">{status_text}</div>
            <div style="width:100%; background-color:#444; border-radius:10px; height:12px;">
                <div style="width:{streak_pct}%; background-color:#ff9800; height:100%; border-radius:10px;"></div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    if not completed:
        st.button(
            f"✅ Marcar {HABIT_NAME} (Día {streak + 1})",
            key="habit_streak_log",
            on_click=log_habit_streak,
            args=(HABIT_NAME, sheet), 
            use_container_width=True
        )


    # -------------------------
    #     GRUPOS DE HÁBITOS
    # -------------------------
    pending = st.session_state.get("todays_pending_habits", [])

    grouped = {1: [], 2: [], 3: []}
    for h in st.session_state.habits: 
        if h["name"] in pending:
            grouped[h["group"]].append(h["name"])

    for group_num, names in grouped.items():
        title = "Mañana" if group_num == 1 else "Tarde" if group_num == 2 else "Noche"
        with st.expander(title, expanded=True):
            cols = st.columns(3)
            for i, habit_name in enumerate(names):
                cols[i % 3].button(
                    habit_name,
                    key=f"habit_{group_num}_{i}",
                    on_click=log_habit_grid,
                    args=(habit_name, sheet),
                    use_container_width=True
                )

    if st.session_state.get("needs_rerun", False):
        st.session_state.needs_rerun = False
        st.rerun()

if __name__ == "__main__":
    run()