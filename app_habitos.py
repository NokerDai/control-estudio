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
# BLOQUEO POR CONTRASEÑA REMOVED
# ---------------------------------------------------------------
# Password check now handled in app.py

def run():
    st.set_page_config(
        page_title="Hábitos",
        page_icon="📅"
    )

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

    GOOGLE_SHEET_NAME = st.secrets["google_sheet_name"]
    WORKSHEET_NAME = st.secrets["worksheet_name"]
    BOUNDARY_COLUMN = st.secrets["boundary_column"]
    
    # -------------------------------------------------------------------
    # CONEXIÓN A GOOGLE SHEETS
    # -------------------------------------------------------------------
    @st.cache_resource
    def connect_to_google_sheets():
        try:
            # 1) Intentar desde secrets
            service_account_data = None
            sa = st.secrets["service_account"]
            if isinstance(sa, str):
                service_account_data = json.loads(sa)
            elif isinstance(sa, dict):
                service_account_data = sa

            if service_account_data:
                gc = gspread.service_account_from_dict(service_account_data)
                spreadsheet = gc.open(GOOGLE_SHEET_NAME)
                worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
                return worksheet
            
            return None

        except Exception as e:
            st.error(f"Error al conectar a Google Sheets: {e}")
            return None

    # -------------------------------------------------------------------
    # LOG DE RACHA 
    # -------------------------------------------------------------------
    # -------------------------------------------------------------------
    # HÁBITOS DESDE SECRETS
    # -------------------------------------------------------------------
    def load_habits():
        """Carga todos los hábitos."""
        try:
            raw_habits = st.secrets["habits"]
            if isinstance(raw_habits, list):
                st.session_state.all_habits = raw_habits
                return raw_habits
            st.error("El campo [gcp].habits en secrets no es una lista válida.")
            return []
        except Exception as e:
            st.error(f"Error al cargar hábitos desde secrets: {e}")
            return []

    # -------------------------------------------------------------------
    # CONFIGURACIÓN DEL ESTADO DIARIO (LÓGICA CORREGIDA)
    # -------------------------------------------------------------------
    def setup_daily_state(worksheet):
        today_str = get_argentina_date_str()
        
        # El resto de la lógica (hábitos del grid) se mantiene
        pending_habits_list = []
        if worksheet is not None:
            try:
                all_dates = worksheet.col_values(1)
                date_row_index = all_dates.index(today_str) if today_str in all_dates else -1
                
                if date_row_index != -1:
                    today_row = worksheet.row_values(date_row_index + 1)
                    headers = worksheet.row_values(1)
                    
                    for habit in st.session_state.all_habits:
                        name = habit["name"]

                        if name in headers:
                            col_idx = headers.index(name)
                            if col_idx >= len(today_row) or not today_row[col_idx].strip():
                                pending_habits_list.append(name)
                        else:
                            pending_habits_list.append(name)
            except:
                 pass
        
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
        st.session_state.all_habits = st.secrets["habits"]

    if 'all_habits' not in st.session_state:
        st.session_state.all_habits = st.secrets["habits"]

    setup_daily_state(sheet)

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