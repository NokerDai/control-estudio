import streamlit as st
import base64
from googleapiclient.discovery import build
from google.oauth2 import service_account

st.set_page_config(page_title="Fe", page_icon="📄")

# ------------------------------
# VALIDAR LOGIN
# ------------------------------
if "usuario_seleccionado" not in st.session_state:
    st.error("No hay usuario activo. Volvé al inicio.")
    st.stop()

usuario = st.session_state["usuario_seleccionado"]
otro = "Iván" if usuario == "Facundo" else "Facundo"

# ------------------------------
# CONFIGURAR GOOGLE DRIVE
# ------------------------------
try:
    key_dict = json.loads(st.secrets["textkey"])
    creds = service_account.Credentials.from_service_account_info(
        key_dict,
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
except KeyError:
    st.error("Error: falta secreto textkey")
    st.stop()

drive_service = build("drive", "v3", credentials=creds)

# IDs de los archivos markdown (poner los tuyos)
FILE_ID_FACUNDO = st.secrets["fe"]["facundo_md"]
FILE_ID_IVAN = st.secrets["fe"]["ivan_md"]

def leer_md(file_id):
    req = drive_service.files().get_media(fileId=file_id)
    data = req.execute()
    return data.decode("utf-8")

# Leer texto correspondiente
md_facundo = leer_md(FILE_ID_FACUNDO)
md_ivan = leer_md(FILE_ID_IVAN)

texto_izq = md_facundo if usuario == "Facundo" else md_ivan
texto_der = md_ivan if usuario == "Facundo" else md_facundo

# ------------------------------
# UI
# ------------------------------
st.title("📄 Fe")

col1, col2 = st.columns(2)

with col1:
    st.subheader(usuario)
    st.markdown(texto_izq)

with col2:
    st.subheader(otro)
    st.markdown(texto_der)

if st.button("Volver"):
    st.switch_page("app.py")
