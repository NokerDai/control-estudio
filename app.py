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
    
# Definimos los usuarios principales para la lógica de quién espía a quién
FACUNDO = "Facundo"
IVAN = "Iván"
ADMIN_PASSWORD_KEY = "password" # Clave del secret

# -------------------------------------------------------------
# LÓGICA DINÁMICA DE USUARIOS
# -------------------------------------------------------------

# El usuario logueado por defecto es Iván (usuario estándar no autenticado)
st.session_state.current_user = IVAN
st.session_state.otro_usuario_nombre = FACUNDO
st.session_state.otro_usuario_current_page = "estudio" # Estado a simular para el otro usuario

# Si está autenticado, es Facundo
if st.session_state.authenticated:
    st.session_state.current_user = FACUNDO
    st.session_state.otro_usuario_nombre = IVAN
    # Aquí podríamos cargar el estado real de Iván si existiera una base de datos.
    st.session_state.otro_usuario_current_page = "idiomas" # Ejemplo: Simular que Iván está en Idiomas
elif not st.session_state.authenticated:
    # Si no está autenticado, es Iván, y espía a Facundo
    st.session_state.current_user = IVAN
    st.session_state.otro_usuario_nombre = FACUNDO
    st.session_state.otro_usuario_current_page = "estudio" # Ejemplo: Simular que Facundo está en Estudio

# ---------------------------------------------------------
# LÓGICA DE LOGIN (Solo si hay ?password en la URL)
# ---------------------------------------------------------
query_params = st.query_params

# Si la URL tiene ?password Y aún no estamos logueados:
if "password" in query_params and not st.session_state.authenticated:
    st.title("🔒 Acceso Administrativo")
    password_input = st.text_input("Contraseña:", type="password")
    
    if st.button("Entrar"):
        # Verificamos contra los secrets 
        if password_input == st.secrets[ADMIN_PASSWORD_KEY]:
            st.session_state.authenticated = True
            st.session_state.pw_correct = True 
            # El usuario pasa a ser Facundo (el admin) y debe ver a Iván
            st.session_state.current_user = FACUNDO
            st.session_state.otro_usuario_nombre = IVAN 
            st.session_state.current_page = "estudio" 
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")
    
    st.stop()

# ---------------------------------------------------------
# BARRA LATERAL (Lógica de Navegación PROPIA)
# ---------------------------------------------------------

st.sidebar.header(f"Navegación de **{st.session_state.current_user}**")

# --- Botón para ir a ESTUDIO ---
if st.session_state.current_page != "estudio":
    if st.sidebar.button("📚 Estudio", use_container_width=True):
        st.session_state.current_page = "estudio"
        st.rerun()

# --- Botón para ir a IDIOMAS ---
if st.session_state.current_page != "idiomas":
    if st.sidebar.button("🌎 Idiomas", use_container_width=True):
        st.session_state.current_page = "idiomas"
        st.rerun()

# Lógica solo para usuarios Autenticados (Facundo)
if st.session_state.authenticated:
    
    # Botón para ir a HÁBITOS
    if st.session_state.current_page != "habitos":
        if st.sidebar.button("📅 Hábitos", use_container_width=True):
            st.session_state.current_page = "habitos"
            st.rerun()

# ---------------------------------------------------------
# VISTA DEL OTRO USUARIO (Visible para TODOS)
# ---------------------------------------------------------

st.sidebar.markdown("---") 

otro_usuario = st.session_state.otro_usuario_nombre 
st.sidebar.header(f"Vista de **{otro_usuario}**")

# === Lógica de visualización de páginas (Solo lectura) ===
otro_usuario_page = st.session_state.otro_usuario_current_page

# 1. Estudio 
if otro_usuario_page == "estudio":
    st.sidebar.success(f"📚 Estudio (Activo)")
else:
    st.sidebar.info("📚 Estudio")
    
# 2. Idiomas 
if otro_usuario_page == "idiomas":
    st.sidebar.success(f"🌎 Idiomas (Activo)")
else:
    st.sidebar.info("🌎 Idiomas")

# 3. Hábitos (SOLO visible si el usuario actual está autenticado)
# Solo Facundo (autenticado) puede ver la actividad de Hábitos (en este caso, la de Iván)
if st.session_state.authenticated:
    # Comprobamos si el otro usuario (Iván) está "viendo" su página de hábitos
    if otro_usuario_page == "habitos":
        st.sidebar.success(f"📅 Hábitos (Activo)")
    else:
        st.sidebar.info("📅 Hábitos")
else:
    # Ocultamos la información de Hábitos al usuario Iván
    st.sidebar.caption("🔒 Hábitos (Solo visible para administrador)")


# ---------------------------------------------------------
# ROUTER (Decide qué app mostrar)
# ---------------------------------------------------------

# 1. Si eligió "habitos" Y está autenticado (Facundo), mostramos Hábitos
if st.session_state.current_page == "habitos" and st.session_state.authenticated:
    st.session_state.pw_correct = True
    app_habitos.run()

# 2. Si eligió "idiomas" (Autenticado o no), mostramos Idiomas
elif st.session_state.current_page == "idiomas":
    app_idiomas.main() 

# 3. En cualquier otro caso (Estudio)
else:
    app_estudio.main()