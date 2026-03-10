import streamlit as st
import app_estudio
import app_habitos
import app_biblioteca
import app_noticias

# 1. Configuración global
st.set_page_config(
    page_title="Selector de Usuario", 
    page_icon="⏳", 
    layout="centered"
)

# 2. Inicialización de Estado de Sesión
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "current_page" not in st.session_state:
    st.session_state.current_page = "estudio" 
if "usuario_seleccionado" not in st.session_state:
    st.session_state.usuario_seleccionado = None

query_params = st.query_params

# Si tiene el parámetro password, autenticamos globalmente
if "password" in query_params:
    st.session_state.authenticated = True

# ---------------------------------------------------------
# LÓGICA DE SELECCIÓN DE USUARIO (SIN LOCKS)
# ---------------------------------------------------------
def handle_user_login(selected_user):
    st.session_state.usuario_seleccionado = selected_user
    st.rerun()

USUARIO_ACTUAL = st.session_state.get("usuario_seleccionado")

# Botón para salir/cambiar de usuario
if USUARIO_ACTUAL is not None:
    if st.sidebar.button("🚪 Cambiar Usuario", use_container_width=True):
        st.session_state.usuario_seleccionado = None
        st.session_state.current_page = "estudio"
        if len(query_params) > 0:
            st.query_params.clear()
        st.rerun()

# Auto-ingreso mediante parámetros en la URL
if "password" in query_params and st.session_state.usuario_seleccionado is None:
    handle_user_login("Facundo")
    
if "ivan" in query_params and st.session_state.usuario_seleccionado is None:
    handle_user_login("Iván")

# ---------------------------------------------------------
# SELECCIÓN DE USUARIO (INTERFAZ)
# ---------------------------------------------------------
if st.session_state.usuario_seleccionado is None:
    st.title("Selección de Usuario")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("👤 Facundo", key="btn_facundo", use_container_width=True):
            handle_user_login("Facundo")

    with col2:
        if st.button("👤 Iván", key="btn_ivan", use_container_width=True):
            handle_user_login("Iván")

    st.stop() 

# ---------------------------------------------------------
# NAVEGACIÓN EN SIDEBAR
# ---------------------------------------------------------

# --- Botón para ir a ESTUDIO ---
if st.session_state.current_page != "estudio":
    if st.sidebar.button("📖 Estudio", use_container_width=True):
        st.session_state.current_page = "estudio"
        st.rerun()

# --- Botón para ir a HÁBITOS ---
show_habitos = st.session_state.authenticated or ("password" in query_params)

if show_habitos and st.session_state.current_page != "habitos":
    if st.sidebar.button("📅 Hábitos", use_container_width=True):
        st.session_state.current_page = "habitos"
        st.rerun()

# Lógica solo para usuarios Autenticados
show_other_pages = st.session_state.authenticated or ("password" in query_params)

if show_other_pages:
    # --- Botón para ir a NOTICIAS ---
    if st.session_state.current_page != "noticias":
        if st.sidebar.button("📰 Noticias", use_container_width=True):
            st.session_state.current_page = "noticias"
            st.rerun()
    
    # --- Botón para ir a BIBLIOTECA ---
    if st.session_state.current_page != "biblioteca":
        if st.sidebar.button("📚 Biblioteca", use_container_width=True):
            st.session_state.current_page = "biblioteca"
            st.rerun()

# --------------------------------------------------------
# ROUTER (Decide qué app mostrar)
# --------------------------------------------------------

if st.session_state.current_page == "habitos":
    if not st.session_state.authenticated:
        password_input = st.text_input("Contraseña:", type="password")
        if st.button("Entrar"):
            if password_input == st.secrets["password"]:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")
        st.stop()
    app_habitos.run()

elif st.session_state.current_page == "biblioteca":
    if not st.session_state.authenticated:
        password_input = st.text_input("Contraseña:", type="password")
        if st.button("Entrar"):
            if password_input == st.secrets["password"]:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")
        st.stop()
    app_biblioteca.main()

elif st.session_state.current_page == "noticias":
    if not st.session_state.authenticated:
        password_input = st.text_input("Contraseña:", type="password")
        if st.button("Entrar"):
            if password_input == st.secrets["password"]:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")
        st.stop()
    app_noticias.main()

else:
    app_estudio.main()
