import streamlit as st
import app_estudio
import app_habitos
import app_idiomas

# 1. Configuración global (Siempre va primero)
st.set_page_config(
    page_title="Estudio", 
    page_icon="⏳", 
    layout="centered"
)

# 2. Inicialización de Estado de Sesión
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "current_page" not in st.session_state:
    st.session_state.current_page = "estudio"

# ---------------------------------------------------------
# LÓGICA DE LOGIN (Solo si hay ?password en la URL)
# ---------------------------------------------------------
query_params = st.query_params

# Si la URL tiene ?password Y aún no estamos logueados:
if "password" in query_params and not st.session_state.authenticated:
    st.title("🔒 Acceso Administrativo")
    password_input = st.text_input("Contraseña:", type="password")
    
    if st.button("Entrar"):
        # Verificamos contra los secrets (asumiendo que están en [auth] password)
        if password_input == st.secrets["password"]:
            st.session_state.authenticated = True
            # Bypass para que app_habitos no pida password de nuevo
            st.session_state.pw_correct = True 
            # ===> Borramos el parámetro de la URL después del login
            del query_params["password"] 
            st.query_params(**query_params)
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")

# ---------------------------------------------------------
# BARRA LATERAL (Navegación)
# ---------------------------------------------------------

if st.session_state.authenticated:
    st.sidebar.markdown(f"#### Usuario: **{app_estudio.USUARIO_ACTUAL}**")

# Botón para ir a ESTUDIO
if st.session_state.current_page != "estudio":
    if st.sidebar.button("⏳ Ir a Estudio", use_container_width=True):
        st.session_state.current_page = "estudio"
        st.rerun()

# Botón para ir a IDIOMAS
if st.session_state.current_page != "idiomas":
    if st.sidebar.button("🗣️ Ir a Idiomas", use_container_width=True):
        st.session_state.current_page = "idiomas"
        st.rerun()

# Botón para ir a HÁBITOS (Solo si está autenticado)
if st.session_state.authenticated:
    if st.session_state.current_page != "habitos":
        if st.sidebar.button("📅 Ir a Hábitos", use_container_width=True):
            st.session_state.current_page = "habitos"
            st.rerun()

# ---------------------------------------------------------
# ROUTER (Decide qué app mostrar)
# ---------------------------------------------------------

# Si eligió "habitos" Y está autenticado, mostramos Hábitos
if st.session_state.current_page == "habitos" and st.session_state.authenticated:
    # Nos aseguramos que app_habitos sepa que ya pasamos la seguridad
    st.session_state.pw_correct = True
    app_habitos.run()
    
# Si eligió "idiomas", mostramos Idiomas
elif st.session_state.current_page == "idiomas":
    app_idiomas.main()

# Si eligió "estudio" (o es el default), mostramos Estudio
elif st.session_state.current_page == "estudio":
    app_estudio.main()