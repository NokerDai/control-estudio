import streamlit as st
import app_estudio
import app_habitos

# 1. Configuración global de la página (Debe ir primero y una sola vez)
st.set_page_config(
    page_title="Estudio", 
    page_icon="⏳", 
    layout="centered"
)

# 2. Lógica de Enrutamiento
# Verificamos los parámetros de la URL (ej: ?habits o ?habitos)
query_params = st.query_params

if "habits" in query_params or "habitos" in query_params:
    # Si la URL tiene ?habits, ejecutamos la app de hábitos
    app_habitos.run()
else:
    # Por defecto (sin parámetros), ejecutamos la app de estudio
    app_estudio.main()