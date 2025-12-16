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
            # ===> AÑADIR ESTA LÍNEA <===
            st.session_state.usuario_seleccionado = "Facundo" 
            # Volvemos a la página de inicio (Estudio) pero ya autenticados
            st.session_state.current_page = "estudio" 
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")
    
    # Detenemos la ejecución aquí para que no cargue nada más hasta loguearse
    st.stop()

# ---------------------------------------------------------
# BARRA LATERAL (Lógica de Navegación)
# ---------------------------------------------------------

# Navegación siempre visible para todos los usuarios
st.sidebar.header("Navegación")

# --- Botón para ir a ESTUDIO ---
# Solo se muestra si NO estamos en la página "estudio"
if st.session_state.current_page != "estudio":
    if st.sidebar.button("📚 Estudio", use_container_width=True):
        st.session_state.current_page = "estudio"
        st.rerun()

# --- Botón para ir a IDIOMAS (NUEVO BLOQUE) ---
# Solo se muestra si NO estamos en la página "idiomas"
if st.session_state.current_page != "idiomas":
    if st.sidebar.button("🌎 Idiomas", use_container_width=True):
        st.session_state.current_page = "idiomas"
        st.rerun()

# Lógica solo para usuarios Autenticados
if st.session_state.authenticated:
    
    # Botón para ir a HÁBITOS
    # Solo se muestra si NO estamos en la página "habitos"
    if st.session_state.current_page != "habitos":
        if st.sidebar.button("📅 Hábitos", use_container_width=True):
            st.session_state.current_page = "habitos"
            st.rerun()

# ---------------------------------------------------------
# ROUTER (Decide qué app mostrar)
# ---------------------------------------------------------

# 1. Si eligió "habitos" Y está autenticado, mostramos Hábitos
if st.session_state.current_page == "habitos" and st.session_state.authenticated:
    # Nos aseguramos que app_habitos sepa que ya pasamos la seguridad
    st.session_state.pw_correct = True
    app_habitos.run()

# 2. Si eligió "idiomas" (Autenticado o no), mostramos Idiomas
elif st.session_state.current_page == "idiomas":
    # El archivo app_idiomas.py no requiere autenticación
    app_idiomas.main() 

# 3. En cualquier otro caso (Usuario normal, Admin que eligió Estudio), mostramos Estudio
else: # st.session_state.current_page == "estudio"
    app_estudio.main()