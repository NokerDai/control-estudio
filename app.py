import streamlit as st
import app_estudio
import app_habitos
import app_idiomas 
import app_biblioteca
import app_noticias
from datetime import datetime
try:
    # Necesitamos el ID de la sesión para el loc
    from streamlit.runtime.scriptrunner import get_script_run_ctx
except ImportError:
    def get_script_run_ctx():
        return None

def get_current_session_id():
    """Obtiene el ID único de la sesión de Streamlit actual."""
    try:
        ctx = get_script_run_ctx()
        return ctx.session_id if ctx else "NO_SESSION_ID"
    except Exception:
        # Fallback con timestamp si no se puede obtener un ID fijo.
        return f"FALLBACK_ID_{datetime.now().timestamp()}" 

# Usuarios que requieren lock en Sheets
RESTRICTED_USERS = ["Facundo", "Iván"]

# ---------------------------------------------------------
# CÓDIGO ORIGINAL CONTINÚA
# ---------------------------------------------------------

# 1. Configuración global (Siempre va primero)
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
# ===> ESTADO PARA EL USUARIO SELECCIONADO <===
if "usuario_seleccionado" not in st.session_state:
    st.session_state.usuario_seleccionado = None 

SESSION_ID = get_current_session_id() 


# ---------------------------------------------------------
# LÓGICA DE UNREGISTER/LOGOUT (MODIFICADA para liberar lock en Sheets)
# ---------------------------------------------------------
USUARIO_ACTUAL = st.session_state.get("usuario_seleccionado")

def handle_user_login(selected_user):
    current_id = SESSION_ID
    
    if selected_user in RESTRICTED_USERS:
        # Lógica de restricción de sesión usando Google Sheets
        current_lock_value = app_estudio.get_user_lock_status(selected_user)
        
        is_locked_by_other = False
        if current_lock_value != "":
            if current_lock_value != current_id:
                is_locked_by_other = True

        # === LÓGICA DE FORZAR DESLOGUEO ===
        # Paso 2: Si la bandera de forzado está activa (desde el click del botón), procedemos al desbloqueo.
        if st.session_state.get(f"force_unlock_{selected_user}", False):
            st.session_state.pop(f"force_unlock_{selected_user}") # Limpiamos la bandera
            
            if app_estudio.set_user_lock_status(selected_user, ""):
                st.toast(f"🚨 Lock forzado y liberado para {selected_user}. ¡Intenta iniciar sesión ahora!")
                st.rerun() 
                return True # Detiene la ejecución actual
            else:
                st.error("Error al forzar la liberación del lock en Sheets.")
                return False

        # Paso 1: Si está bloqueado por otro, mostramos el error y el botón de forzado.
        if is_locked_by_other:
            # Usamos columnas para colocar el mensaje de error y el botón uno al lado del otro.
            col_err, col_btn = st.columns([0.65, 0.35])

            with col_err:
                st.error(f"❌ El usuario **{selected_user}** ya tiene una sesión activa en otra parte. Debe desloguearse primero.")
            
            with col_btn:
                # El nuevo botón "Error" / Forzar deslogueo
                # on_click establece una bandera en session_state y fuerza un rerun para ejecutar el Paso 2.
                if st.button(
                    "⚠️ Error", 
                    key=f"force_unlock_btn_{selected_user}",
                    help="Usa esto si la otra sesión está congelada y no puede desloguearse.",
                    use_container_width=True,
                    on_click=lambda: st.session_state.update({f"force_unlock_{selected_user}": True})
                ):
                    pass

            return False # Bloquear el login y detener el proceso en este punto
        # =========================================
        else:
            # Si no está bloqueado, procede a tomar el lock
            # 1. Tomar/Revalidar el lock en Google Sheets
            if app_estudio.set_user_lock_status(selected_user, current_id):
                st.toast(f"✅ Lock de sesión tomado/revalidado para {selected_user}.")
            else:
                st.error("Error al intentar tomar el lock de sesión. Intenta de nuevo.")
                return False
    
    # 2. Proceder con el login local (para todos los usuarios)
    st.session_state.usuario_seleccionado = selected_user
    st.rerun()
    return True

# ---------------------------------------------------------
# LÓGICA DE LOGIN (Solo si hay ?password en la URL)
# ---------------------------------------------------------
query_params = st.query_params

if USUARIO_ACTUAL is not None:
    # Botón explícito para desloguear y liberar el lock
    if st.sidebar.button("🚪 Desloguear", use_container_width=True):
        if USUARIO_ACTUAL in RESTRICTED_USERS:
            # 1. Liberar el lock en Google Sheets
            if app_estudio.set_user_lock_status(USUARIO_ACTUAL, ""):
                st.toast(f"🔒 Lock de {USUARIO_ACTUAL} liberado en Sheets.")
            else:
                st.warning("⚠️ Error al liberar el lock de sesión en Sheets.")
            
        # 2. Limpiar estado de sesión local
        st.session_state.usuario_seleccionado = None
        st.session_state.current_page = "estudio"

        if len(query_params) > 0:
            st.query_params.clear()

        st.rerun()

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
    if st.session_state.usuario_seleccionado is None:
        handle_user_login("Facundo")
    
    st.stop()
    
# Check for direct user login via URL params
if "ivan" in query_params and st.session_state.usuario_seleccionado is None:
    handle_user_login("Iván")

# ---------------------------------------------------------
# SELECCIÓN DE USUARIO (MODIFICADO: Botones de acceso directo)
# ---------------------------------------------------------

if st.session_state.usuario_seleccionado is None:
    st.title("Selección de Usuario")
    
    # --- Interfaz con Botones ---
    col1, col2 = st.columns(2)
    
    with col1:
        # Se llama a handle_user_login al presionar
        if st.button("👤 Facundo", key="btn_facundo", use_container_width=True):
            handle_user_login("Facundo")

    with col2:
        # Se llama a handle_user_login al presionar
        if st.button("👤 Iván", key="btn_ivan", use_container_width=True):
            handle_user_login("Iván")

    st.stop() 

# ---------------------------------------------------------
# RE-VALIDACIÓN DEL LOCK EN CADA RERUN (Para usuarios restringidos)
# ---------------------------------------------------------
# Si el usuario es restringido y ya está logueado, verificamos que el lock en Sheets
# siga siendo el de esta sesión (SESSION_ID).
if USUARIO_ACTUAL in RESTRICTED_USERS:
    current_lock_value = app_estudio.get_user_lock_status(USUARIO_ACTUAL)
    
    if current_lock_value != SESSION_ID:
        # Esto significa que el lock fue liberado o tomado por otra sesión.
        
        # 1. Liberar el lock en Sheets si por alguna razón esta sesión aún lo tenía
        if current_lock_value == SESSION_ID:
            app_estudio.set_user_lock_status(USUARIO_ACTUAL, "")

        # 2. Desloguear esta sesión por seguridad
        st.session_state.usuario_seleccionado = None
        st.session_state.current_page = "estudio" 
        st.warning(f"⚠️ Sesión de **{USUARIO_ACTUAL}** invalidada. El lock de Sheets fue modificado externamente.")
        st.rerun()

# ---------------------------------------------------------
# NAVEGACIÓN EN SIDEBAR
# ---------------------------------------------------------

# --- Botón para ir a ESTUDIO ---
# Solo se muestra si NO estamos en la página "estudio"
if st.session_state.current_page != "estudio":
    if st.sidebar.button("📖 Estudio", use_container_width=True):
        st.session_state.current_page = "estudio"
        st.rerun()

# --- Botón para ir a IDIOMAS ---
# Solo se muestra si NO estamos en la página "idiomas"
if st.session_state.current_page != "idiomas":
    if st.sidebar.button("🌎 Idiomas", use_container_width=True):
        st.session_state.current_page = "idiomas"
        st.rerun()

# Lógica solo para usuarios Autenticados
if st.session_state.authenticated:
    
    # Botón para ir a BIBLIOTECA ---
    # Solo se muestra si NO estamos en la página "biblioteca" y está autenticado
    if st.session_state.current_page != "biblioteca":
        if st.sidebar.button("📚 Biblioteca", use_container_width=True):
            st.session_state.current_page = "biblioteca"
            st.rerun()
    
    # --- Botón para ir a NOTICIAS ---
    # Solo se muestra si NO estamos en la página "noticias" y está autenticado
    if st.session_state.current_page != "noticias":
        if st.sidebar.button("📰 Noticias", use_container_width=True):
            st.session_state.current_page = "noticias"
            st.rerun()
    
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

# 3. Si eligió "biblioteca" Y está autenticado, mostramos Biblioteca
elif st.session_state.current_page == "biblioteca" and st.session_state.authenticated:
    app_biblioteca.main()

# 4. Si eligió "noticias" Y está autenticado, mostramos Noticias
elif st.session_state.current_page == "noticias" and st.session_state.authenticated:
    app_noticias.main()

# 4. Por defecto (o si eligió "estudio"), mostramos Estudio
else:
    app_estudio.main()