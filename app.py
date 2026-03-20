import streamlit as st
import time
import app_estudio
import app_habitos
import app_biblioteca
import app_noticias

# 1. Configuración global
st.set_page_config(
    page_title="Estudio", 
    page_icon="📖", 
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 2. Inicialización de Estado de Sesión
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "current_page" not in st.session_state:
    st.session_state.current_page = "estudio" 
if "usuario_seleccionado" not in st.session_state:
    st.session_state.usuario_seleccionado = None
if "auto_login_done" not in st.session_state:
    st.session_state.auto_login_done = False
if "switching_user" not in st.session_state:
    st.session_state.switching_user = False

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

# Auto-ingreso automático (Solo ocurre en la primera carga)
if not st.session_state.auto_login_done and st.session_state.usuario_seleccionado is None:
    st.session_state.auto_login_done = True # Marcamos para que no vuelva a forzar el ingreso si cierran sesión
    if "password" in query_params:
        handle_user_login("Facundo")
    else:
        # Cualquier otra URL (sin parámetros o con cualquier cosa que no sea password) va a Iván
        handle_user_login("Iván")

USUARIO_ACTUAL = st.session_state.get("usuario_seleccionado")

# ---------------------------------------------------------
# PANTALLA DE CARGA (TRANSICIÓN)
# ---------------------------------------------------------
if st.session_state.get("switching_user", False):
    st.title("⏳ Cambiando de usuario...")
    st.markdown("---")
    st.warning("**Atención:** Nunca usar la aplicación en dos dispositivos a la vez.", icon="⚠️")
    
    # Pausa de 1.5 segundos para que se alcance a leer el cartel
    time.sleep(1.5) 
    
    # Lógica para alternar el usuario directamente
    nuevo_usuario = "Iván" if USUARIO_ACTUAL == "Facundo" else "Facundo"
    st.session_state.usuario_seleccionado = nuevo_usuario
    st.session_state.switching_user = False
    st.rerun()

# ---------------------------------------------------------
# BOTÓN EN LA BARRA LATERAL (DISPARADOR)
# ---------------------------------------------------------
# Botón para salir/cambiar de usuario
if USUARIO_ACTUAL is not None:
    if st.sidebar.button("🚪 Cambiar Usuario", use_container_width=True):
        # 1. Mostramos el mensaje directamente en la barra lateral
        st.sidebar.warning("⚠️ **Atención:** Nunca usar la aplicación en dos dispositivos a la vez.", icon="🚫")
        
        # 2. Hacemos la pausa de 1 segundo para que se lea
        time.sleep(1)
        
        # 3. Alternamos el usuario directamente
        nuevo_usuario = "Iván" if USUARIO_ACTUAL == "Facundo" else "Facundo"
        st.session_state.usuario_seleccionado = nuevo_usuario
        st.session_state.current_page = "estudio"
        
        if len(st.query_params) > 0:
            st.query_params.clear()
            
        # 4. Recargamos la aplicación
        st.rerun()

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

    # --- El cartel de advertencia ---
    st.markdown("---") # Una línea divisoria para separar
    st.warning("⚠️ **Atención:** Nunca usar la aplicación en dos dispositivos a la vez.", icon="🚫")

    st.stop() 

# ---------------------------------------------------------
# NAVEGACIÓN EN SIDEBAR
# ---------------------------------------------------------

# Variable estricta para permisos de administrador:
is_admin = (st.session_state.usuario_seleccionado == "Facundo") and st.session_state.authenticated

# --- Botón para ir a ESTUDIO ---
if st.session_state.current_page != "estudio":
    if st.sidebar.button("📖 Estudio", use_container_width=True):
        st.session_state.current_page = "estudio"
        st.rerun()

# --- Botón para ir a HÁBITOS ---
if is_admin and st.session_state.current_page != "habitos":
    if st.sidebar.button("📅 Hábitos", use_container_width=True):
        st.session_state.current_page = "habitos"
        st.rerun()

# Lógica estricta para usuarios Autenticados (Facundo)
# if is_admin:
    # --- Botón para ir a NOTICIAS ---
    # if st.session_state.current_page != "noticias":
    #     if st.sidebar.button("📰 Noticias", use_container_width=True):
    #         st.session_state.current_page = "noticias"
    #         st.rerun()
    
    # --- Botón para ir a BIBLIOTECA ---
    # if st.session_state.current_page != "biblioteca":
    #     if st.sidebar.button("📚 Biblioteca", use_container_width=True):
    #         st.session_state.current_page = "biblioteca"
    #         st.rerun()

# --------------------------------------------------------
# ROUTER (Decide qué app mostrar)
# --------------------------------------------------------

if st.session_state.current_page == "habitos":
    if not is_admin:
        if st.session_state.usuario_seleccionado != "Facundo":
            st.error("Solo Facundo tiene permisos para acceder a esta sección.")
            st.stop()
        else:
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
    if not is_admin:
        if st.session_state.usuario_seleccionado != "Facundo":
            st.error("Solo Facundo tiene permisos para acceder a esta sección.")
            st.stop()
        else:
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
    if not is_admin:
        if st.session_state.usuario_seleccionado != "Facundo":
            st.error("Solo Facundo tiene permisos para acceder a esta sección.")
            st.stop()
        else:
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
