import json
from google.oauth2 import service_account
import streamlit as st
from googleapiclient.discovery import build
from datetime import datetime

# ==============================
# CONFIGURACIÓN DE CREDENCIALES
# ==============================
# Carga las credenciales desde los secretos de Streamlit (st.secrets["textkey"])
try:
    key_dict = json.loads(st.secrets["textkey"])
    creds = service_account.Credentials.from_service_account_info(
        key_dict,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
except KeyError:
    st.error("Error: Falta configurar el secreto 'textkey' en Streamlit Cloud.")
    st.stop()


# -------------------------
# CONFIGURACIÓN GOOGLE SHEETS
# -------------------------
SHEET_ID = "1KPdcnRlSjY-4xEUcZO194lwAnlNKx1UaElyDTeczo5Y"
NOMBRE_HOJA = "Código"


# ==============================
# SELECCIÓN DE USUARIO (USO DE SESSION STATE)
# ==============================
if "usuario_seleccionado" not in st.session_state:
    st.title("¿Quién sos? 👤")
    col_u1, col_u2 = st.columns(2)
    
    with col_u1:
        if st.button("Soy Facundo", use_container_width=True):
            st.session_state["usuario_seleccionado"] = "Facundo"
            st.rerun()
            
    with col_u2:
        if st.button("Soy Iván", use_container_width=True):
            st.session_state["usuario_seleccionado"] = "Iván"
            st.rerun()
            
    st.stop()

# Asignamos la variable principal
USUARIO_ACTUAL = st.session_state["usuario_seleccionado"]

# Agregamos un botón para cambiar de usuario
if st.sidebar.button("Cerrar sesión / Cambiar usuario"):
    del st.session_state["usuario_seleccionado"]
    st.rerun()

service = build("sheets", "v4", credentials=creds)
sheet = service.spreadsheets()


# ==============================
# MAPEO DE MATERIAS
# ==============================
USERS = {
    "Iván": {
        "Física":   {"est": f"{NOMBRE_HOJA}!C4", "time": f"{NOMBRE_HOJA}!D4"},
        "Álgebra":  {"est": f"{NOMBRE_HOJA}!C5", "time": f"{NOMBRE_HOJA}!D5"},
        "Análisis": {"est": f"{NOMBRE_HOJA}!C6", "time": f"{NOMBRE_HOJA}!D6"},
    },
    "Facundo": {
        "Economía":   {"est": f"{NOMBRE_HOJA}!G4", "time": f"{NOMBRE_HOJA}!H4"},
        "Matemática": {"est": f"{NOMBRE_HOJA}!G5", "time": f"{NOMBRE_HOJA}!H5"},
        "Historia":   {"est": f"{NOMBRE_HOJA}!G6", "time": f"{NOMBRE_HOJA}!H6"},
    }
}


# ==============================
# FUNCIONES DE TIEMPO
# ==============================
def ahora_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def parse_datetime(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")

def hms_a_segundos(hms):
    # Maneja el caso de hms vacío o None, aunque la hoja debería tener 00:00:00
    if not hms or hms.strip() == "":
        return 0
    h, m, s = hms.split(":")
    return int(h)*3600 + int(m)*60 + int(s)

def segundos_a_hms(seg):
    h = seg // 3600
    m = (seg % 3600) // 60
    s = seg % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


# ==============================
# FUNCIONES DE CALLBACK PARA EVITAR ERRORES (FIX)
# ==============================
def enable_manual_input(materia_key):
    """Habilita el input manual. Usa una clave distinta a la del botón."""
    st.session_state[f"show_manual_{materia_key}"] = True


# ==============================
# LECTURA ÚNICA (EVITA RATE LIMIT)
# ==============================
def cargar_todo():
    ranges = []
    for user, materias in USERS.items():
        for m, info in materias.items():
            ranges.append(info["est"])
            ranges.append(info["time"])

    res = sheet.values().batchGet(
        spreadsheetId=SHEET_ID,
        ranges=ranges,
        valueRenderOption="FORMATTED_VALUE"
    ).execute()

    values = res.get("valueRanges", [])

    data = {u: {"estado": {}, "tiempos": {}} for u in USERS}

    idx = 0
    for user, materias in USERS.items():
        for materia, info in materias.items():

            # estado (hora o vacío)
            est_val = values[idx].get("values", [[]])
            est_val = est_val[0][0] if est_val and est_val[0] else ""
            idx += 1

            # tiempo acumulado
            time_val = values[idx].get("values", [[]])
            time_val = time_val[0][0] if time_val and time_val[0] else "00:00:00"
            idx += 1

            data[user]["estado"][materia] = est_val
            data[user]["tiempos"][materia] = time_val

    return data


# ==============================
# ESCRITURAS OPTIMIZADAS
# ==============================
def batch_write(updates):
    """
    updates = [(range, value), (range, value), ...]
    """
    body = {
        "valueInputOption": "RAW",
        "data": [
            {"range": r, "values": [[v]]}
            for r, v in updates
        ]
    }
    sheet.values().batchUpdate(
        spreadsheetId=SHEET_ID,
        body=body
    ).execute()


def limpiar_estudiando(materias):
    updates = []
    for datos in materias.values():
        updates.append((datos["est"], ""))
    batch_write(updates)


# ==============================
# INTERFAZ
# ==============================
st.title("⏳ Control de Estudio")

datos = cargar_todo()

if st.button("🔄 Actualizar tiempos"):
    st.rerun()

otro = "Iván" if USUARIO_ACTUAL == "Facundo" else "Facundo"

colA, colB = st.columns(2)


# ==============================
# PANEL USUARIO ACTUAL (editable)
# ==============================
with colA:
    st.subheader(f"👤 {USUARIO_ACTUAL}")
    mis_materias = USERS[USUARIO_ACTUAL]

    for materia, info in mis_materias.items():

        est_raw = datos[USUARIO_ACTUAL]["estado"][materia]  # hora o ""
        tiempo_acum = datos[USUARIO_ACTUAL]["tiempos"][materia]

        box = st.container()
        with box:

            st.markdown(f"**{materia}**")
            
            # --- Lógica de cálculo de tiempo proyectado (NUEVO) ---
            tiempo_anadido_seg = 0
            if est_raw.strip() != "":
                inicio = parse_datetime(est_raw)
                # El tiempo añadido es la diferencia entre ahora y la hora de inicio
                tiempo_anadido_seg = int((datetime.now() - inicio).total_seconds())

            tiempo_acum_seg = hms_a_segundos(tiempo_acum)
            tiempo_total_proyectado_seg = tiempo_acum_seg + tiempo_anadido_seg
            tiempo_total_proyectado_hms = segundos_a_hms(tiempo_total_proyectado_seg)
            # --------------------------------------------------------

            # Display: Acumulado
            st.write(f"🕒 Acumulado: {tiempo_acum}")
            
            # Display: Proyectado (solo si está estudiando)
            if tiempo_anadido_seg > 0:
                tiempo_anadido_hms = segundos_a_hms(tiempo_anadido_seg)
                st.markdown(f"**⏳ En proceso:** +{tiempo_anadido_hms} (Total: **{tiempo_total_proyectado_hms}**)")

            b1, b2, _ = st.columns([0.2, 0.2, 0.6])

            # ======================
            # DETENER
            # ======================
            if est_raw.strip() != "":
                with b1:
                    if st.button("⛔", key=f"det_{materia}", help="Detener estudio"):
                        inicio = parse_datetime(est_raw)
                        fin = datetime.now()
                        diff = int((fin - inicio).total_seconds())

                        total_prev = hms_a_segundos(tiempo_acum)
                        nuevo_total = total_prev + diff

                        batch_write([
                            (info["time"], segundos_a_hms(nuevo_total)),
                            (info["est"], "")
                        ])

                        st.rerun()

            # ======================
            # ESTUDIAR
            # ======================
            else:
                with b1:
                    if st.button("▶", key=f"est_{materia}", help="Comenzar a estudiar"):
                        limpiar_estudiando(mis_materias)
                        batch_write([
                            (info["est"], ahora_str())
                        ])
                        st.rerun()

            # ======================
            # TIEMPO MANUAL (✏️)
            # ======================
            with b2:
                if st.button(
                    "✏️", 
                    key=f"manual_{materia}", 
                    help="Poner tiempo manual",
                    on_click=enable_manual_input, 
                    args=[materia]
                ):
                    pass 

            if st.session_state.get(f"show_manual_{materia}", False):
                nuevo = st.text_input(f"Tiempo para {materia} (HH:MM:SS):", key=f"in_{materia}")
                
                if st.button("Guardar", key=f"save_{materia}"):
                    try:
                        hms_a_segundos(nuevo)
                        batch_write([(info["time"], nuevo)])
                        
                        st.session_state[f"show_manual_{materia}"] = False
                        st.rerun()
                    except:
                        st.error("Formato inválido (usar HH:MM:SS)")


# ==============================
# PANEL OTRO USUARIO (solo lectura)
# ==============================
with colB:
    st.subheader(f"👤 {otro}")

    otras = USERS[otro]

    for materia, info in otras.items():
        est_raw = datos[otro]["estado"][materia]
        tiempo = datos[otro]["tiempos"][materia] # tiempo acumulado

        box = st.container()
        with box:
            st.markdown(f"**{materia}**")

            # --- Lógica de cálculo de tiempo proyectado (NUEVO) ---
            tiempo_anadido_seg = 0
            if est_raw.strip() != "":
                inicio = parse_datetime(est_raw)
                # El tiempo añadido es la diferencia entre ahora y la hora de inicio
                tiempo_anadido_seg = int((datetime.now() - inicio).total_seconds())

            tiempo_acum_seg = hms_a_segundos(tiempo)
            tiempo_total_proyectado_seg = tiempo_acum_seg + tiempo_anadido_seg
            tiempo_total_proyectado_hms = segundos_a_hms(tiempo_total_proyectado_seg)
            # --------------------------------------------------------

            # Display: Acumulado
            st.write(f"🕒 Acumulado: {tiempo}")
            
            # Display: Proyectado (solo si está estudiando)
            if tiempo_anadido_seg > 0:
                tiempo_anadido_hms = segundos_a_hms(tiempo_anadido_seg)
                st.markdown(f"**⏳ En proceso:** +{tiempo_anadido_hms} (Total: **{tiempo_total_proyectado_hms}**)")

            if est_raw.strip() != "":
                st.markdown("🟢 Estudiando")
            else:
                st.markdown("⚪")
