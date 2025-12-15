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
        if ZoneInfo is not None:
            return datetime.now(ZoneInfo('America/Argentina/Buenos_Aires'))
        if 'pytz' in globals() and pytz is not None:
            return datetime.now(pytz.timezone('America/Argentina/Buenos_Aires'))
        return datetime.now()

    def get_argentina_time_str():
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
    
    # *** SECRETS GENERALIZADOS PARA EL HÁBITO DE RACHA (SOLO EL NOMBRE DEL HÁBITO) ***
    STREAK_HABIT_NAME = _gcp_secrets.get("streak_habit_name", "No Fap")
    
    # Calculamos el nombre de la columna de racha basado en el nombre del hábito.
    STREAK_COLUMN_NAME = f"Racha {STREAK_HABIT_NAME}"

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
    # LECTURA ESPECÍFICA DE RACHA
    # -------------------------------------------------------------------
    def get_yesterdays_streak(worksheet, streak_column):
        """Lee el número de racha de la columna 'streak_column' del día anterior."""
        if worksheet is None: return 0

        # Calcular la fecha de ayer
        yesterday_dt = _argentina_now_global().date() - timedelta(days=1)
        yesterday_str = f"{yesterday_dt.day:02d}/{yesterday_dt.month:02d}"

        try:
            # 1. Obtener los encabezados y la columna de la racha
            headers = worksheet.row_values(1)
            if streak_column not in headers:
                # Si la columna no existe, la racha es 0
                return 0 

            streak_col_index = headers.index(streak_column) + 1 

            # 2. Encontrar la fila de ayer
            all_dates = worksheet.col_values(1)
            if yesterday_str not in all_dates:
                return 0 

            yesterday_row_index = all_dates.index(yesterday_str) + 1 

            # 3. Leer el valor de la celda de la racha de ayer
            streak_val = worksheet.cell(yesterday_row_index, streak_col_index).value

            try:
                # Si es un número, lo retornamos, si no, retornamos 0
                return int(streak_val) if streak_val else 0
            except ValueError:
                return 0 

        except Exception:
            return 0
            
    # -------------------------------------------------------------------
    # LOG DE RACHA 
    # -------------------------------------------------------------------
    def log_habit_streak(habit_name, streak_column_name, worksheet):
        """Calcula new_streak = yesterday_streak + 1 y actualiza las dos celdas."""
        try:
            if worksheet is None: return

            today_str = get_argentina_date_str()
            time_str = get_argentina_time_str()
            
            # Usar la columna de la racha genérica
            current_streak = get_yesterdays_streak(worksheet, streak_column_name) 
            new_streak = current_streak + 1

            # 1. Encontrar la fila de hoy
            all_dates = worksheet.col_values(1)
            if today_str not in all_dates:
                st.error(f"La fecha de hoy ({today_str}) no está en la columna A. ¡Esto es un problema de planificación!")
                return
            date_row = all_dates.index(today_str) + 1

            # 2. Encontrar/Crear la columna de Racha (STREAK_COLUMN_NAME) y actualizar con el número
            headers = worksheet.row_values(1)
            if streak_column_name in headers:
                streak_col_idx = headers.index(streak_column_name) + 1
            else:
                # Si no existe, la creamos al final
                streak_col_idx = len(headers) + 1
                worksheet.update_cell(1, streak_col_idx, streak_column_name)
                headers = worksheet.row_values(1) # Re-obtener headers
            
            worksheet.update_cell(date_row, streak_col_idx, new_streak)

            # 3. Encontrar/Crear la columna del Hábito (STREAK_HABIT_NAME) y actualizar con el tiempo (marca)
            if habit_name in headers:
                habit_col_idx = headers.index(habit_name) + 1
            else:
                # Usar la lógica de log_habit_grid para encontrar la posición (antes de BOUNDARY_COLUMN)
                if BOUNDARY_COLUMN in headers:
                    boundary = headers.index(BOUNDARY_COLUMN)
                    habit_col_idx = boundary + 1 
                else:
                    habit_col_idx = len(headers) + 1 
                
                worksheet.update_cell(1, habit_col_idx, habit_name)
                headers = worksheet.row_values(1) 

            if habit_name in headers:
                 habit_col_idx = headers.index(habit_name) + 1
                 worksheet.update_cell(date_row, habit_col_idx, time_str)
            else:
                st.error(f"Error interno: No se pudo encontrar la columna para el hábito '{habit_name}'.")

            # 4. Actualizar el estado local
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
                # Retornar la lista filtrada para el loop de la UI (solo hábitos grupales, excluyendo el de racha)
                return [h for h in raw_habits if h["name"] != STREAK_HABIT_NAME]
            st.error("El campo [gcp].habits en secrets no es una lista válida.")
            return []
        except Exception as e:
            st.error(f"Error al cargar hábitos desde secrets: {e}")
            return []

    # -------------------------------------------------------------------
    # LOG A GOOGLE SHEETS
    # -------------------------------------------------------------------
    def setup_daily_state(worksheet):
        today_str = get_argentina_date_str()
        
        streak_habit_completed_today = False
        current_streak = 0
        pending_habits_list = []

        if worksheet is not None:
            try:
                # 1. Leer racha de ayer
                current_streak = get_yesterdays_streak(worksheet, STREAK_COLUMN_NAME)
                
                all_dates = worksheet.col_values(1)
                date_row_index = all_dates.index(today_str) if today_str in all_dates else -1
                
                if date_row_index != -1:
                    today_row = worksheet.row_values(date_row_index + 1)
                    headers = worksheet.row_values(1)
                    
                    # 2. Verificar si el hábito de racha ya está completado hoy (marca de tiempo)
                    if STREAK_HABIT_NAME in headers:
                        col_idx = headers.index(STREAK_HABIT_NAME)
                        if col_idx < len(today_row) and today_row[col_idx].strip():
                            streak_habit_completed_today = True
                            
                            # Si está completado, leer el número de racha guardado hoy (valor de HOY)
                            if STREAK_COLUMN_NAME in headers:
                                streak_col_idx = headers.index(STREAK_COLUMN_NAME)
                                if streak_col_idx < len(today_row) and today_row[streak_col_idx].strip():
                                    try:
                                        current_streak = int(today_row[streak_col_idx])
                                    except:
                                        pass
                    
                    # 3. Determinar el resto de hábitos pendientes
                    for habit in st.session_state.all_habits:
                        name = habit["name"]
                        if name == STREAK_HABIT_NAME:
                            continue 

                        if name in headers:
                            col_idx = headers.index(name)
                            # Si no hay valor o está vacío, es pendiente
                            if col_idx >= len(today_row) or not today_row[col_idx].strip():
                                pending_habits_list.append(name)
                        else:
                            pending_habits_list.append(name)

            except ValueError:
                st.warning(f"La fecha de hoy ({today_str}) no está en la columna A. No se puede cargar el estado de hábitos.")
            except Exception as e:
                st.error(f"Error al leer la planificación: {e}")

        # Guardar el estado del hábito de racha
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

                if habit_name in headers:
                    col = headers.index(habit_name) + 1
                else:
                    # insertar antes de boundary
                    if BOUNDARY_COLUMN in headers:
                        boundary = headers.index(BOUNDARY_COLUMN)
                        col = None
                        for idx in range(1, boundary + 1):
                            if idx - 1 >= len(headers) or not headers[idx - 1].strip():
                                col = idx
                                break
                        if col is None:
                            col = boundary
                    else:
                        col = len(headers) + 1

                time_str = get_argentina_time_str()
                worksheet.update_cell(date_row, col, time_str)

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
        st.session_state.all_habits = _gcp_secrets.get("habits", []) # Fallback

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
    STREAK_GOAL = 90 # Objetivo de la barra de progreso (ajustable)
    streak_pct = min(streak / STREAK_GOAL, 1.0) * 100
    
    status_text = f"✅ ¡Completado hoy! Racha: {streak} días." if completed else f"⏳ Pendiente. Racha actual: {streak} días."
    
    st.markdown(f"## {HABIT_NAME}")
    st.markdown(f"""
        <div style="background-color: #262730; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
            <div style="font-size: 1.1rem; color: #aaa; margin-bottom: 8px;">{status_text}</div>
            <div style="width:100%; background-color:#444; border-radius:10px; height:12px;">
                <div style="width:{streak_pct}%; background-color:#ff9800; height:100%; border-radius:10px;"></div>
            </div>
            <div style="display:flex; justify-content:space-between; font-size:0.8rem; color:#888; margin-top:5px;">
                <span>{streak} días</span>
                <span>Objetivo: {STREAK_GOAL} días</span>
            </div>
        </div>
    """, unsafe_allow_html=True)

    if not completed:
        st.button(
            f"✅ Marcar {HABIT_NAME} (Día {streak + 1})",
            key="habit_streak_log",
            on_click=log_habit_streak,
            args=(HABIT_NAME, STREAK_COLUMN_NAME, sheet),
            use_container_width=True
        )
    else:
        st.info("Ya has marcado " + HABIT_NAME + " hoy.")
        
    st.markdown("---") # Separador visual


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