import streamlit as st
import app_estudio
import app_habitos
import app_idiomas # <--- ¡NUEVO!

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
# BARRA LATERAL (Visible si estás Autenticado O en una página pública)
# ---------------------------------------------------------
# La navegación se muestra si estás autenticado o si ya seleccionaste un usuario
# para poder alternar entre estudio e idiomas.

# Definimos si mostramos la barra lateral
show_sidebar = st.session_state.authenticated or ("usuario_seleccionado" in st.session_state)

if show_sidebar:
    st.sidebar.header("Navegación")

    # Botón para ir a ESTUDIO
    if st.session_state.current_page != "estudio":
        if st.sidebar.button("📚 Ir a Estudio", use_container_width=True):
            st.session_state.current_page = "estudio"
            st.rerun()

    # Botón para ir a IDIOMAS (¡NUEVO!)
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
    
# Si eligió "idiomas", mostramos Idiomas (¡NUEVO!)
elif st.session_state.current_page == "idiomas":
    # Le pasamos la lógica de tiempo al módulo de idiomas
    # Para esto, app_idiomas debe importar la lógica de app_estudio
    app_idiomas.main()

# En cualquier otro caso (Usuario normal o Admin que eligió Estudio), mostramos Estudio
else:
    app_estudio.main()