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
# VISTA DEL OTRO USUARIO (Ahora con botones para navegar)
# ---------------------------------------------------------

st.sidebar.markdown("---") 

otro_usuario = st.session_state.otro_usuario_nombre 
st.sidebar.header(f"Vista de **{otro_usuario}**")

# === Helper para crear la navegación de solo lectura ===
def render_other_user_nav(page_name, icon):
    # La página destino tendrá un prefijo 'otro_' para diferenciarla en el router
    target_page = f"otro_{page_name}"
    label = f"{icon} {page_name.capitalize()}"
    
    # Define si el otro usuario está 'activo' en esta página para poner el checkmark
    otro_usuario_page = st.session_state.otro_usuario_current_page

    # 1. Si el usuario actual está VIENDO esta página del otro
    if st.session_state.current_page == target_page:
        st.sidebar.success(f"{label} (Viendo)")
    
    # 2. Si el usuario actual NO está viendo la página, mostramos el botón
    else:
        # Añadir un indicador visual si el otro usuario está en esta página
        display_label = label
        if otro_usuario_page == page_name:
            display_label = f"✅ {label}"
        
        if st.sidebar.button(display_label, key=f"btn_otro_{page_name}", use_container_width=True):
            st.session_state.current_page = target_page
            st.rerun()

# 1. Estudio (Visible y navegable para cualquiera)
render_other_user_nav("estudio", "📚")
    
# 2. Idiomas (Visible y navegable para cualquiera)
render_other_user_nav("idiomas", "🌎")

# 3. Hábitos (SOLO visible y navegable si el usuario actual está autenticado)
if st.session_state.authenticated:
    render_other_user_nav("habitos", "📅")
else:
    st.sidebar.caption(f"🔒 Hábitos (Solo visible para Facundo)")


# ---------------------------------------------------------
# ROUTER (Decide qué app mostrar)
# ---------------------------------------------------------

current_page = st.session_state.current_page

# 1. NAVEGACIÓN PROPIA

# Si eligió "habitos" Y está autenticado (Facundo), mostramos Hábitos
if current_page == "habitos" and st.session_state.authenticated:
    st.session_state.pw_correct = True
    app_habitos.run()
    
# Si eligió "idiomas" (Autenticado o no), mostramos Idiomas propio
elif current_page == "idiomas":
    app_idiomas.main() 

# 2. NAVEGACIÓN DEL OTRO USUARIO (Vistas de solo lectura)

# Si eligió ver los Hábitos del otro Y está autenticado
elif current_page == "otro_habitos" and st.session_state.authenticated:
    st.title(f"👀 Vista de {st.session_state.otro_usuario_nombre} - Hábitos")
    st.warning("⚠️ Esta es una vista de **solo lectura** del progreso de hábitos.")
    st.info("Aquí iría el contenido de `app_habitos.run()` en modo visualización.")
    
# Si eligió ver los Idiomas del otro
elif current_page == "otro_idiomas":
    st.title(f"👀 Vista de {st.session_state.otro_usuario_nombre} - Idiomas")
    st.warning("⚠️ Esta es una vista de **solo lectura** del progreso de idiomas.")
    st.info("Aquí iría el contenido de `app_idiomas.main()` en modo visualización.")

# Si eligió ver el Estudio del otro
elif current_page == "otro_estudio":
    st.title(f"👀 Vista de {st.session_state.otro_usuario_nombre} - Estudio")
    st.warning("⚠️ Esta es una vista de **solo lectura** del progreso de estudio.")
    st.info("Aquí iría el contenido de `app_estudio.main()` en modo visualización.")
    
# 3. En cualquier otro caso (Estudio propio)
else: # current_page == "estudio"
    app_estudio.main()