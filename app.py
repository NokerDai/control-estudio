# app.py - Control de Estudio con persistencia Persona en 'marcas'
import json
from google.oauth2 import service_account
import streamlit as st
from googleapiclient.discovery import build
from datetime import datetime, date
from zoneinfo import ZoneInfo

# ---------------------------
# Config Streamlit
# ---------------------------
st.set_page_config(page_title="Control de Estudio (persistente)", page_icon="⏳", layout="centered")

# ---------------------------
# Carga credenciales
# ---------------------------
try:
    key_dict = json.loads(st.secrets["textkey"])
    creds = service_account.Credentials.from_service_account_info(
        key_dict,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
except KeyError:
    st.error("Error: Falta configurar el secreto 'textkey' en Streamlit secrets.")
    st.stop()

service = build("sheets", "v4", credentials=creds)
sheet = service.spreadsheets()

# ---------------------------
# Timezone / helpers de tiempo
# ---------------------------
TZ = ZoneInfo("America/Argentina/Cordoba")

def ahora_str():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

def parse_datetime(s):
    if not s or str(s).strip() == "":
        raise ValueError("Marca vacía")
    s = str(s).strip().lstrip("'")
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S%z")
        return dt.astimezone(TZ)
    except:
        pass
    dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    return dt.replace(tzinfo=TZ)

# ---------------------------
# Fila dinámica según fecha
# ---------------------------
FILA_BASE = 170
FECHA_BASE = date(2025, 12, 2)  # fila 170 = 02/12/2025

def fila_para_fecha(fecha_actual):
    delta = (fecha_actual - FECHA_BASE).days
    return FILA_BASE + delta

hoy = date.today()
TIME_ROW = fila_para_fecha(hoy)
MARCAS_ROW = 2  # fila fija para timestamps (est)

# ---------------------------
# Hojas y columnas (ajustar si querés)
# ---------------------------
SHEET_FACUNDO = "F. Economía"
SHEET_IVAN = "I. Física"
SHEET_MARCAS = "marcas"

# Columnas donde se escribirán los pesos diarios (en 'marcas')
PESOS_COLS = {"Facundo": "H", "Iván": "I"}  # cambiar si querés otras columnas

# Columnas para guardar estado persistente por persona en 'marcas' fila TIME_ROW
# (Ajustá si preferís otras columnas)
STATE_COLS = {
    "Facundo": {
        "precio_puntos": "J",
        "puntos": "K",
        "pesos_acumulados": "L",
        "canje_del_dia": "M",
        "puntos_canjeados_hoy": "N",
    },
    "Iván": {
        "precio_puntos": "J",
        "puntos": "K",
        "pesos_acumulados": "L",
        "canje_del_dia": "M",
        "puntos_canjeados_hoy": "N",
    }
}

# ---------------------------
# Clase Persona
# ---------------------------
class Persona:
    def __init__(self, nombre):
        self.nombre = nombre
        self.precio_puntos = 180.0
        self.max_puntos = 360
        self.min_puntos = 180
        self.max_canje_valor = 1000.0
        self.puntos = 0               # puntos = minutos
        self.puntos_canjeados_hoy = 0
        self.pesos_acumulados = 0.0
        self.canje_del_dia = 0.0

    def max_canje(self, pesos_a_canjear):
        espacio = self.max_canje_valor - self.canje_del_dia
        if espacio <= 0: return 0.0
        return round(min(pesos_a_canjear, espacio), 2)

    def pasar_dia(self):
        """Convierte puntos(minutos) -> pesos permitidos según tasa y tope diario."""
        tasa = 500.0 / self.precio_puntos
        pesos_obtenidos = round(self.puntos * tasa, 2)
        pesos_permitidos = self.max_canje(pesos_obtenidos)

        # acumular permitidos
        self.pesos_acumulados = round(self.pesos_acumulados + pesos_permitidos, 2)
        self.canje_del_dia += pesos_permitidos

        pesos_no_canjeados = round(pesos_obtenidos - pesos_permitidos, 2)

        # puntos remanentes = pesos_no_canjeados / tasa (minutos)
        if pesos_no_canjeados > 0:
            puntos_restantes = pesos_no_canjeados / tasa
            self.puntos = int(round(puntos_restantes))
        else:
            self.puntos = 0

        # ajustar precio_puntos (lógica simple)
        if self.canje_del_dia < 500:
            dec = max((self.precio_puntos - self.puntos_canjeados_hoy) * 0.1, 10)
            self.precio_puntos = max(self.precio_puntos - dec, self.min_puntos)
        elif self.canje_del_dia > 500:
            inc = max((self.puntos_canjeados_hoy - self.precio_puntos) * 0.3, 10)
            self.precio_puntos = min(self.precio_puntos + inc, self.max_puntos)

        pesos_permitidos = round(pesos_permitidos, 2)
        return pesos_permitidos, pesos_no_canjeados

# ---------------------------
# Mapeo materias (rutas dinámicas por TIME_ROW)
# ---------------------------
USERS = {
    "Iván": {
        "Física":   {"time": f"'{SHEET_IVAN}'!B{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!F{MARCAS_ROW}"},
        "Análisis": {"time": f"'{SHEET_IVAN}'!C{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!G{MARCAS_ROW}"},
    },
    "Facundo": {
        "Matemática para Economistas 1": {"time": f"'{SHEET_FACUNDO}'!B{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!B{MARCAS_ROW}"},
        "Matemática para Economistas 2": {"time": f"'{SHEET_FACUNDO}'!C{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!C{MARCAS_ROW}"},
        "Macroeconomía 1":               {"time": f"'{SHEET_FACUNDO}'!D{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!D{MARCAS_ROW}"},
        "Historia":                      {"time": f"'{SHEET_FACUNDO}'!E{TIME_ROW}", "est": f"'{SHEET_MARCAS}'!E{MARCAS_ROW}"},
    }
}

# ---------------------------
# Funciones de tiempo / conversión
# ---------------------------
def hms_a_segundos(hms):
    if hms is None: return 0
    s = str(hms).strip().lstrip("'")
    if s == "": return 0
    parts = s.split(":")
    try:
        parts = [int(p) for p in parts]
    except:
        return 0
    if len(parts) == 3:
        h, m, sec = parts
    elif len(parts) == 2:
        h, m, sec = 0, parts[0], parts[1]
    else:
        return 0
    return h*3600 + m*60 + sec

def segundos_a_hms(seg):
    h = seg // 3600
    m = (seg % 3600) // 60
    s = seg % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def hms_a_fraction(hms):
    total = hms_a_segundos(hms)
    return total / 86400.0

# ---------------------------
# LECTURA / ESCRITURA Google Sheets
# ---------------------------
def cargar_todo():
    sheet_id = st.secrets["sheet_id"]
    ranges = []
    for user, materias in USERS.items():
        for m, info in materias.items():
            ranges.append(info["est"])
            ranges.append(info["time"])
    res = sheet.values().batchGet(spreadsheetId=sheet_id, ranges=ranges, valueRenderOption="FORMATTED_VALUE").execute()
    values = res.get("valueRanges", [])
    data = {u: {"estado": {}, "tiempos": {}} for u in USERS}
    idx = 0
    for user, materias in USERS.items():
        for materia, info in materias.items():
            est_val = ""
            time_val = "00:00:00"
            if idx < len(values):
                v = values[idx].get("values", [[]])
                est_val = v[0][0] if v and v[0] else ""
            est_val = str(est_val).lstrip("'")
            idx += 1
            if idx < len(values):
                v = values[idx].get("values", [[]])
                time_val = v[0][0] if v and v[0] else "00:00:00"
            time_val = str(time_val).lstrip("'")
            idx += 1
            data[user]["estado"][materia] = est_val
            data[user]["tiempos"][materia] = time_val
    return data

def batch_write(updates):
    """
    updates: list of (range, value). value can be:
      - float (duración como fracción de día o pesos)
      - string (timestamp para 'est')
    """
    sheet_id = st.secrets["sheet_id"]
    body = {"valueInputOption": "USER_ENTERED", "data": [{"range": r, "values": [[v]]} for r, v in updates]}
    sheet.values().batchUpdate(spreadsheetId=sheet_id, body=body).execute()

def limpiar_estudiando(materias):
    updates = [(datos["est"], "") for materia, datos in materias.items()]
    batch_write(updates)

# ---------------------------
# Persistencia Persona en 'marcas'
# ---------------------------
def cargar_personas():
    personas = {}
    sheet_id = st.secrets["sheet_id"]
    for nombre in ["Facundo", "Iván"]:
        cols = STATE_COLS[nombre]
        ranges = [f"'{SHEET_MARCAS}'!{c}{TIME_ROW}" for c in cols.values()]
        res = sheet.values().batchGet(spreadsheetId=sheet_id, ranges=ranges, valueRenderOption="FORMATTED_VALUE").execute()
        vals = res.get("valueRanges", [])
        p = Persona(nombre)
        # Valores defensivos: si no hay valor en la celda, usar valores por defecto
        try:
            p.precio_puntos = float(vals[0].get("values", [["180"]])[0][0])
        except:
            p.precio_puntos = 180.0
        try:
            p.puntos = int(float(vals[1].get("values", [["0"]])[0][0]))
        except:
            p.puntos = 0
        try:
            p.pesos_acumulados = float(vals[2].get("values", [["0"]])[0][0])
        except:
            p.pesos_acumulados = 0.0
        try:
            p.canje_del_dia = float(vals[3].get("values", [["0"]])[0][0])
        except:
            p.canje_del_dia = 0.0
        try:
            p.puntos_canjeados_hoy = int(float(vals[4].get("values", [["0"]])[0][0]))
        except:
            p.puntos_canjeados_hoy = 0
        personas[nombre] = p
    return personas

def guardar_estado(personas):
    updates = []
    for nombre, p in personas.items():
        cols = STATE_COLS[nombre]
        updates.extend([
            (f"'{SHEET_MARCAS}'!{cols['precio_puntos']}{TIME_ROW}", p.precio_puntos),
            (f"'{SHEET_MARCAS}'!{cols['puntos']}{TIME_ROW}", p.puntos),
            (f"'{SHEET_MARCAS}'!{cols['pesos_acumulados']}{TIME_ROW}", p.pesos_acumulados),
            (f"'{SHEET_MARCAS}'!{cols['canje_del_dia']}{TIME_ROW}", p.canje_del_dia),
            (f"'{SHEET_MARCAS}'!{cols['puntos_canjeados_hoy']}{TIME_ROW}", p.puntos_canjeados_hoy),
        ])
    if updates:
        batch_write(updates)

# ---------------------------
# Registrar pesos diarios (llama a Persona.pasar_dia y persiste)
# ---------------------------
def registrar_pesos_diarios(datos, personas):
    updates = []
    registros = {}
    for nombre, persona in personas.items():
        materias = USERS[nombre]
        total_seg = 0
        for materia, info in materias.items():
            total_seg += hms_a_segundos(datos[nombre]["tiempos"][materia])
        minutos = total_seg // 60
        persona.puntos += int(minutos)  # 1 punto = 1 minuto
        pesos_permitidos, pesos_no = persona.pasar_dia()
        # escribir pesos diarios en 'marcas'
        col = PESOS_COLS[nombre]
        rango = f"'{SHEET_MARCAS}'!{col}{TIME_ROW}"
        updates.append((rango, pesos_permitidos))
        registros[nombre] = {"minutos": minutos, "pesos_registrados": pesos_permitidos, "pesos_no_canjeados": pesos_no}
    if updates:
        batch_write(updates)
    # luego persistir el estado actualizado de las personas
    guardar_estado(personas)
    return registros

# ---------------------------
# UI: selección de usuario
# ---------------------------
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

USUARIO_ACTUAL = st.session_state["usuario_seleccionado"]

if st.sidebar.button("Cerrar sesión / Cambiar usuario"):
    del st.session_state["usuario_seleccionado"]
    st.rerun()

# ---------------------------
# Cargar datos y personas
# ---------------------------
datos = cargar_todo()
personas = cargar_personas()  # reconstruyo Persona desde 'marcas'

# ---------------------------
# Título y botones globales
# ---------------------------
st.title("⏳ Control de Estudio (persistente)")

if st.button("🔄 Actualizar tiempos"):
    st.rerun()

# Registrar pesos del día (para ambos)
if st.button("Registrar pesos del día"):
    with st.spinner("Registrando pesos..."):
        registros = registrar_pesos_diarios(datos, personas)
    st.success("Pesos registrados en 'marcas'.")
    for nombre, info in registros.items():
        st.write(f"{nombre}: minutos={info['minutos']}, pesos_registrados={info['pesos_registrados']}, no_canjeados={info['pesos_no_canjeados']}")

# ---------------------------
# Panels: usuario actual (control) y otro (solo lectura)
# ---------------------------
otro = "Iván" if USUARIO_ACTUAL == "Facundo" else "Facundo"
colA, colB = st.columns(2)

with colA:
    st.subheader(f"👤 {USUARIO_ACTUAL}")
    mis_materias = USERS[USUARIO_ACTUAL]

    # detectar materia en curso
    materia_en_curso = None
    for m, info in mis_materias.items():
        if datos[USUARIO_ACTUAL]["estado"][m].strip() != "":
            materia_en_curso = m
            break

    for materia, info in mis_materias.items():
        est_raw = datos[USUARIO_ACTUAL]["estado"][materia]
        tiempo_acum = datos[USUARIO_ACTUAL]["tiempos"][materia]

        box = st.container()
        with box:
            st.markdown(f"**{materia}**")

            tiempo_anadido_seg = 0
            if est_raw.strip() != "":
                inicio = parse_datetime(est_raw)
                tiempo_anadido_seg = int((datetime.now(TZ) - inicio).total_seconds())

            tiempo_acum_seg = hms_a_segundos(tiempo_acum)
            tiempo_total = tiempo_acum_seg + max(0, tiempo_anadido_seg)
            tiempo_total_hms = segundos_a_hms(tiempo_total)

            st.write(f"🕒 Total: **{tiempo_total_hms}**")

            if est_raw.strip() != "":
                st.caption(f"Base: {tiempo_acum} | En proceso: +{segundos_a_hms(tiempo_anadido_seg)}")
                st.markdown("🟢 **Estudiando**")
            else:
                st.markdown("⚪")

            b1, b2, _ = st.columns([0.2, 0.2, 0.6])

            # Si esta materia está en curso -> mostrar botón detener
            if materia_en_curso == materia:
                with b1:
                    if st.button("⛔", key=f"det_{materia}", help="Detener estudio"):
                        inicio = parse_datetime(est_raw)
                        diff_total_seconds = (datetime.now(TZ) - inicio).total_seconds()
                        diff = int(max(0, diff_total_seconds))

                        total_prev = hms_a_segundos(tiempo_acum)
                        nuevo_total = total_prev + diff

                        # escribimos duración como fracción para que Sheets sea Duración
                        batch_write([
                            (info["time"], hms_a_fraction(segundos_a_hms(nuevo_total))),
                            (info["est"], "")
                        ])
                        st.rerun()
                continue

            # Si otra materia está en curso -> no mostrar botones
            if materia_en_curso is not None:
                continue

            # ▶ Empezar
            with b1:
                if st.button("▶", key=f"est_{materia}", help="Comenzar a estudiar"):
                    limpiar_estudiando(mis_materias)
                    batch_write([(info["est"], ahora_str())])
                    st.rerun()

            # ✏️ Editar manual
            with b2:
                if st.button("✏️", key=f"manual_{materia}", help="Poner tiempo manual", on_click=lambda m=materia: st.session_state.__setitem__(f"show_manual_{m}", True)):
                    pass

            if st.session_state.get(f"show_manual_{materia}", False):
                nuevo = st.text_input(f"Tiempo para {materia} (HH:MM:SS):", key=f"in_{materia}")
                if st.button("Guardar", key=f"save_{materia}"):
                    try:
                        # validar
                        hms_a_segundos(nuevo)
                        batch_write([(info["time"], hms_a_fraction(nuevo))])
                        st.session_state[f"show_manual_{materia}"] = False
                        st.rerun()
                    except Exception:
                        st.error("Formato inválido (usar HH:MM:SS)")

with colB:
    st.subheader(f"👤 {otro}")

    otras = USERS[otro]

    for materia, info in otras.items():
        est_raw = datos[otro]["estado"][materia]
        tiempo = datos[otro]["tiempos"][materia]

        box = st.container()
        with box:
            st.markdown(f"**{materia}**")

            tiempo_anadido_seg = 0
            if est_raw.strip() != "":
                inicio = parse_datetime(est_raw)
                tiempo_anadido_seg = int((datetime.now(TZ) - inicio).total_seconds())

            tiempo_acum_seg = hms_a_segundos(tiempo)
            tiempo_total = tiempo_acum_seg + max(0, tiempo_anadido_seg)
            tiempo_total_hms = segundos_a_hms(tiempo_total)

            st.write(f"🕒 Total: **{tiempo_total_hms}**")

            if est_raw.strip() != "":
                st.caption(f"Base: {tiempo} | En proceso: +{segundos_a_hms(tiempo_anadido_seg)}")
                st.markdown("🟢 **Estudiando**")
            else:
                st.markdown("⚪")

# ---------------------------
# Fin app
# ---------------------------
