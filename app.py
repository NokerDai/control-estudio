import streamlit as st
import app_estudio
import app_habitos

# 1. Configuración global (Siempre va primero)
st.set_page_config(
    page_title="Gestión Personal", 
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
        if password_input == st.secrets["auth"]["password"]:
            st.session_state.authenticated = True
            # Bypass para que app_habitos no pida password de nuevo
            st.session_state.pw_correct = True 
            # Volvemos a la página de inicio (Estudio) pero ya autenticados
            st.session_state.current_page = "estudio" 
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")
    
    # Detenemos la ejecución aquí para que no cargue nada más hasta loguearse
    st.stop()

# ---------------------------------------------------------
# BARRA LATERAL (Solo visible si estás Autenticado)
# ---------------------------------------------------------
if st.session_state.authenticated:
    st.sidebar.header("Navegación")
    
    # Botón para ir a ESTUDIO
    if st.sidebar.button("📚 Ir a Estudio", use_container_width=True):
        st.session_state.current_page = "estudio"
        st.rerun()

    # Botón para ir a HÁBITOS
    if st.sidebar.button("📅 Ir a Hábitos", use_container_width=True):
        st.session_state.current_page = "habitos"
        st.rerun()

    st.sidebar.markdown("---")
    if st.sidebar.button("🔒 Salir / Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.current_page = "estudio"
        st.rerun()

# ---------------------------------------------------------
# ROUTER (Decide qué app mostrar)
# ---------------------------------------------------------

# Si eligió "habitos" Y está autenticado, mostramos Hábitos
if st.session_state.current_page == "habitos" and st.session_state.authenticated:
    # Nos aseguramos que app_habitos sepa que ya pasamos la seguridad
    st.session_state.pw_correct = True
    app_habitos.run()

# En cualquier otro caso (Usuario normal o Admin que eligió Estudio), mostramos Estudio
else:
    app_estudio.main()