import streamlit as st
import app_estudio
import app_habitos
import app_idiomas 
# Importamos la función para obtener el ID de sesión, esencial para el bloqueo.
try:
    from streamlit.runtime.scriptrunner import get_script_run_ctx
except ImportError:
    # Fallback si no se encuentra la dependencia (versiones antiguas o entornos limitados)
    def get_script_run_ctx():
        return None

# ---------------------------------------------------------
# BLOQUEO DE SESIONES (Global State - ¡CUIDADO! Solo un proceso)
# ---------------------------------------------------------
# Usuarios con restricción de una sesión única
RESTRICTED_USERS = ["iván", "facundo"]

# Diccionario global para el control de sesiones (Clave: usuario, Valor: session_id)
# **ESTO ES UN GLOBAL SHARED STATE QUE SÓLO FUNCIONA EN ENTORNOS SINGLE-THREAD.**
ACTIVE_USERS_LOCK = {} 

def get_current_session_id():
    """Obtiene el ID único de la sesión de Streamlit actual."""
    try:
        ctx = get_script_run_ctx()
        return ctx.session_id if ctx else "NO_SESSION_ID"
    except Exception:
        return "FALLBACK_ID"

def is_user_restricted_and_active(username, current_session_id):
    """Verifica si el usuario está restringido y ya activo en OTRA sesión."""
    if username not in RESTRICTED_USERS:
        return False 
        
    # Si el usuario está en el lock Y el ID de sesión es diferente al actual, está bloqueado.
    if username in ACTIVE_USERS_LOCK and ACTIVE_USERS_LOCK[username] != current_session_id:
        return True 
        
    return False

def register_user_session(username, current_session_id):
    """Registra la sesión actual para un usuario restringido."""
    if username in RESTRICTED_USERS:
        ACTIVE_USERS_LOCK[username] = current_session_id
        
def unregister_user_session(current_session_id):
    """Quita el lock asociado al session_id actual, útil para el logout/cambio."""
    global ACTIVE_USERS_LOCK
    
    # Buscamos y eliminamos cualquier entrada con este session_id
    users_to_remove = [user for user, session_id in ACTIVE_USERS_LOCK.items() if session_id == current_session_id]
    for user in users_to_remove:
        del ACTIVE_USERS_LOCK[user]

# ---------------------------------------------------------
# CÓDIGO ORIGINAL CONTINÚA
# ---------------------------------------------------------

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
# ===> NUEVO ESTADO PARA EL USUARIO SELECCIONADO <===
if "usuario_seleccionado" not in st.session_state:
    st.session_state.usuario_seleccionado = None 


# ---------------------------------------------------------
# LÓGICA DE UNREGISTER/LOGOUT (NUEVO)
# ---------------------------------------------------------
if st.session_state.usuario_seleccionado is not None:
    st.sidebar.markdown("---")
    # Botón explícito para desloguear y liberar el lock
    if st.sidebar.button("🚪 Desloguear / Cambiar Usuario", use_container_width=True):
        # 1. Des-registrar antes de limpiar el estado
        unregister_user_session(get_current_session_id())
        # 2. Limpiar estado de sesión
        st.session_state.usuario_seleccionado = None
        st.session_state.current_page = "estudio" # Vuelve a la página de selección
        st.rerun()

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
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")
    st.stop()
    
# ---------------------------------------------------------
# SELECCIÓN DE USUARIO (MODIFICADO para bloqueo)
# ---------------------------------------------------------

if st.session_state.usuario_seleccionado is None:
    st.title("Selección de Usuario")
    
    # Obtener lista de usuarios de app_estudio.py
    try:
        users_options = list(app_estudio.USERS.keys())
    except AttributeError:
        # Fallback si USERS no está cargado/definido en app_estudio
        users_options = RESTRICTED_USERS + ["otro"] 

    selected = st.selectbox(
        "¿Quién sos?",
        options=["Seleccionar..."] + users_options,
        index=0,
        key="user_select_box"
    )
    
    if selected != "Seleccionar...":
        current_id = get_current_session_id()
        
        if is_user_restricted_and_active(selected, current_id):
            st.error(f"❌ El usuario **{selected}** ya tiene una sesión activa en otra pestaña o navegador.")
            # No hacemos nada más, st.session_state.usuario_seleccionado sigue siendo None
        else:
            # Si no está bloqueado, registramos la sesión y procedemos
            # Primero, liberamos el lock actual si existía por si el usuario estaba en otra sesión restringida y refrescó
            unregister_user_session(current_id) 
            
            register_user_session(selected, current_id)
            st.session_state.usuario_seleccionado = selected
            st.rerun()
            
    st.stop() # Detener la ejecución si no hay usuario seleccionado o si está bloqueado.
    
# Si ya hay un usuario seleccionado (y no fue bloqueado), aseguramos que el lock esté activo 
# en cada rerun (para el caso de refresh de página o interacción).
if st.session_state.usuario_seleccionado in RESTRICTED_USERS:
    register_user_session(st.session_state.usuario_seleccionado, get_current_session_id())


# ---------------------------------------------------------
# NAVEGACIÓN EN SIDEBAR
# ---------------------------------------------------------

st.sidebar.header(f"Hola, {st.session_state.usuario_seleccionado}!")

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
    app_idiomas.main()

# 3. Por defecto (o si eligió "estudio"), mostramos Estudio
else:
    app_estudio.main()