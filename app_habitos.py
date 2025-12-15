import streamlit as st
import gspread
from datetime import datetime
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
    # HÁBITOS DESDE SECRETS
    # -------------------------------------------------------------------
    def load_habits():
        try:
            habits = _gcp_secrets.get("habits", [])
            if isinstance(habits, list):
                return habits
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

        if 'active_habits_date' not in st.session_state or st.session_state.active_habits_date != today_str:
            st.session_state.active_habits_date = today_str
            pending = []

            if worksheet is None:
                st.session_state.todays_pending_habits = [h["name"] for h in st.session_state.habits]
                return

            try:
                all_dates = worksheet.col_values(1)
                date_row_index = all_dates.index(today_str)
                today_row = worksheet.row_values(date_row_index + 1)
                headers = worksheet.row_values(1)

                for habit in st.session_state.habits:
                    name = habit["name"]
                    is_pending = True

                    if name in headers:
                        col_idx = headers.index(name)
                        if col_idx < len(today_row) and today_row[col_idx].strip():
                            is_pending = False

                    if is_pending:
                        pending.append(name)

                st.session_state.todays_pending_habits = pending

            except ValueError:
                st.warning(f"La fecha de hoy ({today_str}) no está en la columna A.")
                st.session_state.todays_pending_habits = []
            except Exception as e:
                st.error(f"Error al leer la planificación: {e}")
                st.session_state.todays_pending_habits = [h["name"] for h in st.session_state.habits]

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

    setup_daily_state(sheet)

    # -------------------------
    #     GRUPOS
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

    # Si alguna acción marcó necesidad de rerun, ejecutar.
    if st.session_state.get("needs_rerun", False):
        st.session_state.needs_rerun = False
        st.rerun()

if __name__ == "__main__":
    run()