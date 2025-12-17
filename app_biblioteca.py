import streamlit as st
import json
import io
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# === CONFIGURACIÓN Y CONEXIÓN ===
SCOPES = ['https://www.googleapis.com/auth/drive']

@st.cache_resource
def get_drive_service():
    """
    Crea el servicio de Drive, manejando la posibilidad de que
    st.secrets['service_account'] sea un string JSON en lugar de un diccionario.
    """
    try:
        creds_data = st.secrets["service_account"]
        
        # Paso clave: Intentar parsear el string JSON a un diccionario si es necesario.
        if isinstance(creds_data, str):
            creds_dict = json.loads(creds_data)
        elif isinstance(creds_data, dict):
            creds_dict = creds_data
        else:
            raise TypeError("st.secrets['service_account'] no es un string ni un diccionario.")
        
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=SCOPES
        )
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Error al conectar con Google Drive. Revisa el formato de service_account en secrets: {e}")
        return None

def get_user_file_id():
    """Devuelve el ID del archivo JSON según el usuario logueado (Facundo o Iván)."""
    usuario = st.session_state.get("usuario_seleccionado")
    
    if not usuario:
        return None
        
    # Mapeo simple de usuarios a claves de secrets
    key_map = {
        "Facundo": "facundo",
        "Iván": "ivan",
        "Ivan": "ivan"
    }
    
    user_key = key_map.get(usuario)
    
    if user_key and "biblioteca_files" in st.secrets:
        return st.secrets["biblioteca_files"].get(user_key)
    
    return None

# === FUNCIONES DE DATOS (CRUD) ===

def load_library_data(file_id):
    """Descarga y lee el JSON desde Drive."""
    service = get_drive_service()
    if not service or not file_id:
        return []

    try:
        request = service.files().get_media(fileId=file_id)
        downloader = request.execute() 
        
        content_str = downloader.decode('utf-8')
        if not content_str.strip():
             return []
            
        return json.loads(content_str)
    except Exception:
        return []

def save_library_data(file_id, data):
    """Sube el JSON actualizado a Drive."""
    service = get_drive_service()
    if not service or not file_id:
        return False

    try:
        json_str = json.dumps(data, indent=4, ensure_ascii=False)
        media_body = MediaIoBaseUpload(
            io.BytesIO(json_str.encode('utf-8')), 
            mimetype='application/json',
            resumable=True
        )
        
        service.files().update(
            fileId=file_id,
            media_body=media_body
        ).execute()
        return True
    except Exception as e:
        st.error(f"Error al guardar los datos en Drive: {e}")
        return False

# === INTERFAZ PRINCIPAL (Sin cambios en la lógica de UI) ===

def main():
    st.title("📚 Biblioteca")

    # 1. Validar Usuario y Archivo
    usuario = st.session_state.get("usuario_seleccionado")
    if not usuario:
        st.warning("Por favor, selecciona un usuario en el inicio para acceder a la biblioteca.")
        return

    file_id = get_user_file_id()
    if not file_id:
        st.error(f"Error de configuración: No hay ID de archivo para el usuario '{usuario}'.")
        return

    # 2. Gestión del Estado y Carga de Datos
    session_key = f"lib_data_{usuario}"
    
    if session_key not in st.session_state:
        with st.spinner(f"Cargando biblioteca personal de {usuario}..."):
            st.session_state[session_key] = load_library_data(file_id)
    
    data = st.session_state[session_key]

    # --- FORMULARIO DE ALTA ---
    st.markdown(f"**Biblioteca de:** **{usuario}**")
    with st.expander("📖 Registrar Nueva Lectura", expanded=False):
        with st.form("form_alta_libro", clear_on_submit=True):
            col_a, col_b = st.columns(2)
            
            with col_a:
                titulo = st.text_input("Título del Libro")
                autor = st.text_input("Autor(es)")
            
            with col_b:
                cats = ["Filosofía", "Psicología", "Economía", "Espiritualidad", "Ficción"]
                categoria = st.selectbox("Categoría", cats)
                imagen = st.text_input("URL de portada (Opcional)", placeholder="https://...")

            btn_guardar = st.form_submit_button("Guardar Lectura")

            if btn_guardar:
                if titulo and autor:
                    nuevo_libro = {
                        "id": int(datetime.now().timestamp()),
                        "fecha": datetime.now().strftime("%Y-%m-%d"),
                        "titulo": titulo,
                        "autor": autor,
                        "categoria": categoria,
                        "imagen": imagen if imagen else ""
                    }
                    
                    data.insert(0, nuevo_libro)
                    st.session_state[session_key] = data
                    
                    with st.spinner("Guardando en Drive..."):
                        if save_library_data(file_id, data):
                            st.toast(f"✅ Libro '{titulo}' guardado.")
                            st.rerun() 
                        else:
                            st.error("Error al guardar en la nube. Revisa los permisos de Drive.")
                else:
                    st.warning("El Título y el Autor son obligatorios.")

    # --- VISUALIZACIÓN ---
    st.divider()
    
    if not data:
        st.info("Aún no tienes lecturas registradas en tu biblioteca.")
        return

    # Filtros y Métricas
    col_filter, col_metric = st.columns([3, 1])
    with col_filter:
        cat_filter = st.selectbox("Filtrar por categoría:", ["Todas"] + sorted(list(set(d["categoria"] for d in data))))
    with col_metric:
        st.metric("Total Registros", len(data))

    # Filtrar datos
    display_data = data
    if cat_filter != "Todas":
        display_data = [d for d in data if d["categoria"] == cat_filter]

    # Renderizar Grid
    cols = st.columns(3)
    for i, libro in enumerate(display_data):
        with cols[i % 3]:
            with st.container(border=True):
                img_url = libro.get("imagen")
                if img_url:
                    st.image(img_url, use_column_width=True)
                
                st.subheader(libro["titulo"])
                st.caption(f"✍️ {libro['autor']}")
                st.caption(f"📅 {libro['fecha']} | 🏷️ {libro['categoria']}")