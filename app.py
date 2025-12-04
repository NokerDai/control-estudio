import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime
from datetime import timedelta, date
from zoneinfo import ZoneInfo

# -------------------------------------------------------------------
# CONFIGURACIÓN
# -------------------------------------------------------------------
st.set_page_config(page_title="Registro de tiempos", layout="centered")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEET_MARCAS = "marcas"
SHEET_APP = "app"

USUARIO_ACTUAL = st.secrets["usuario"]

TZ = ZoneInfo("America/Argentina/Cordoba")
ahora = datetime.now(TZ)
hoy = ahora.date()

# -------------------------------------------------------------------
# CÁLCULO DE FILA SEGÚN FECHA
# -------------------------------------------------------------------
def fila_para_fecha(fecha: date) -> int:
    inicio = date(2024, 6, 16)
    return (fecha - inicio).days + 2

TIME_ROW = fila_para_fecha(hoy)

# -------------------------------------------------------------------
# CONEXIÓN A GOOGLE SHEETS
# -------------------------------------------------------------------
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"], scopes=SCOPES
)

service = build("sheets", "v4", credentials=creds)
sheet = service.spreadsheets().values()

SID = st.secrets["sheet_id"]

# -------------------------------------------------------------------
# CARGA DE DATOS APP
# -------------------------------------------------------------------
def cargar_todo():
    try:
        res = sheet.batchGet(
            spreadsheetId=SID,
            ranges=[
                f"'{SHEET_APP}'!A1:A1000",
                f"'{SHEET_APP}'!B1:B1000",
                f"'{SHEET_APP}'!C1:C1000",
                f"'{SHEET_APP}'!D1:D1000",
                f"'{SHEET_APP}'!E1:E1000",
            ],
            valueRenderOption="UNFORMATTED_VALUE"
        ).execute()

        vr = res.get("valueRanges", [{}]*5)
        return {
            "materias": [x[0] for x in vr[0].get("values", []) if x],
            "areas":    [x[0] for x in vr[1].get("values", []) if x],
            "procesos": [x[0] for x in vr[2].get("values", []) if x],
            "secciones":[x[0] for x in vr[3].get("values", []) if x],
            "tags":     [x[0] for x in vr[4].get("values", []) if x]
        }
    except Exception:
        return {"materias":[],"areas":[],"procesos":[],"secciones":[],"tags":[]}


# -------------------------------------------------------------------
# CARGA DE RESUMEN (valor por minuto + total del día)
# -------------------------------------------------------------------
def cargar_resumen_marcas():
    ranges = [
        f"'{SHEET_MARCAS}'!C{TIME_ROW}",  # per_min Facundo
        f"'{SHEET_MARCAS}'!B{TIME_ROW}",  # per_min Iván
        f"'{SHEET_MARCAS}'!E{TIME_ROW}",  # total Facundo
        f"'{SHEET_MARCAS}'!D{TIME_ROW}",  # total Iván
    ]
    try:
        res = sheet.batchGet(
            spreadsheetId=SID, ranges=ranges,
            valueRenderOption="FORMATTED_VALUE"
        ).execute()
        vr = res.get("valueRanges", [{}]*4)
    except Exception:
        vr = [{}]*4

    def get(i):
        try:
            return vr[i].get("values", [[""]])[0][0]
        except:
            return ""

    return {
        "Facundo": {
            "per_min": get(0),
            "total":   get(2),
        },
        "Iván": {
            "per_min": get(1),
            "total":   get(3),
        },
    }

# -------------------------------------------------------------------
# CARGA INICIAL
# -------------------------------------------------------------------
datos = cargar_todo()
resumen_marcas = cargar_resumen_marcas()

# -------------------------------------------------------------------
# INTERFAZ
# -------------------------------------------------------------------
st.title("⏱ Registro de tiempos")
st.subheader(f"👤 {USUARIO_ACTUAL}")

# Mostrar valores económicos
try:
    per_min = resumen_marcas[USUARIO_ACTUAL]["per_min"]
    total   = resumen_marcas[USUARIO_ACTUAL]["total"]
    st.markdown(f"**${per_min} por minuto | ${total} total**")
except Exception:
    st.markdown("**$— por minuto | $— total**")

# -------------------------------------------------------------------
# FORMULARIO DE REGISTRO
# -------------------------------------------------------------------
st.write("### Registrar actividad")

materia = st.selectbox("Materia", datos["materias"])
area = st.selectbox("Área", datos["areas"])
proceso = st.selectbox("Proceso", datos["procesos"])
seccion = st.selectbox("Sección", datos["secciones"])
tag = st.selectbox("Tag", datos["tags"])

duracion = st.number_input("Duración (minutos)", min_value=1, max_value=600, step=1)

if st.button("Guardar"):
    timestamp = datetime.now(TZ).strftime("%H:%M:%S")

    fila = TIME_ROW
    rango = f"'{SHEET_APP}'!G{fila}:L{fila}"

    valores = [[
        hoy.strftime("%Y-%m-%d"),
        timestamp,
        USUARIO_ACTUAL,
        materia,
        area,
        proceso,
        seccion,
        tag,
        duracion,
    ]]

    try:
        sheet.update(
            spreadsheetId=SID,
            range=rango,
            valueInputOption="USER_ENTERED",
            body={"values": valores}
        ).execute()
        st.success("Registro guardado correctamente.")
    except Exception as e:
        st.error("Error al guardar.")
        st.write(e)
