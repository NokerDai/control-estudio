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
    try:
        creds_data = st.secrets["service_account"]
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
        st.error(f"Error al conectar con Drive: {e}")
        return None

def get_user_file_id():
    usuario = st.session_state.get("usuario_seleccionado")
    if not usuario: return None
    key_map = {"Facundo": "facundo", "Iván": "ivan", "Ivan": "ivan"}
    user_key = key_map.get(usuario)
    if user_key and "biblioteca_files" in st.secrets:
        return st.secrets["biblioteca_files"].get(user_key)
    return None

# === FUNCIONES DE DATOS ===
def load_library_data(file_id):
    service = get_drive_service()
    if not service or not file_id: return []
    try:
        request = service.files().get_media(fileId=file_id)
        downloader = request.execute() 
        content_str = downloader.decode('utf-8')
        return json.loads(content_str) if content_str.strip() else []
    except Exception: return []

def save_library_data(file_id, data):
    service = get_drive_service()
    if not service or not file_id: return False
    try:
        json_str = json.dumps(data, indent=4, ensure_ascii=False)
        media_body = MediaIoBaseUpload(io.BytesIO(json_str.encode('utf-8')), mimetype='application/json', resumable=True)
        service.files().update(fileId=file_id, media_body=media_body).execute()
        return True
    except Exception as e:
        st.error(f"Error al guardar: {e}")
        return False

# === INTERFAZ PRINCIPAL ===
def main():
    st.title("📚 Biblioteca")

    usuario = st.session_state.get("usuario_seleccionado")
    if not usuario:
        st.warning("Por favor, selecciona un usuario en el inicio.")
        return

    file_id = get_user_file_id()
    if not file_id:
        st.error(f"Error: No se encontró ID de archivo para {usuario}.")
        return

    session_key = f"lib_data_{usuario}"
    if session_key not in st.session_state:
        with st.spinner("Cargando biblioteca..."):
            st.session_state[session_key] = load_library_data(file_id)
    
    data = st.session_state[session_key]

    # --- FORMULARIO DE ALTA ---
    with st.expander("Registrar Lectura", expanded=False):
        with st.form("form_alta_libro", clear_on_submit=True):
            col_a, col_b = st.columns(2)
            with col_a:
                titulo = st.text_input("Título del Libro")
                autor = st.text_input("Autor(es)")
            with col_b:
                opciones_base = ["Filosofía", "Psicología", "Economía", "Espiritualidad", "Ficción", "Desarrollo Personal", "Ciencia"]
                existentes = set()
                for d in data:
                    cats = d.get("categoria", [])
                    if isinstance(cats, list): existentes.update(cats)
                    else: existentes.add(cats)
                
                todas_opciones = sorted(list(set(opciones_base) | existentes))
                categorias = st.multiselect("Categorías", todas_opciones)
                imagen = st.text_input("URL de portada (Opcional)")

            if st.form_submit_button("Guardar Lectura"):
                if titulo and autor and categorias:
                    nuevo_libro = {
                        "id": int(datetime.now().timestamp()),
                        "fecha": datetime.now().strftime("%Y-%m-%d"),
                        "titulo": titulo,
                        "autor": autor,
                        "categoria": categorias,
                        "imagen": imagen if imagen else ""
                    }
                    data.insert(0, nuevo_libro)
                    if save_library_data(file_id, data):
                        st.session_state[session_key] = data
                        st.toast(f"✅ '{titulo}' guardado.")
                        st.rerun()
                else:
                    st.warning("Completa Título, Autor y al menos una Categoría.")

    st.divider()
    if not data:
        st.info("No hay registros.")
        return

    # --- NUEVO: BARRA DE BÚSQUEDA Y FILTROS ---
    search_query = st.text_input("🔍 Buscar por título o autor", "").lower()

    todas_las_cats = set()
    for d in data:
        c = d.get("categoria", [])
        if isinstance(c, list): todas_las_cats.update(c)
        else: todas_las_cats.add(c)

    col_filter, col_metric = st.columns([3, 1])
    with col_filter:
        cat_filter = st.selectbox("Filtrar por categoría:", ["Todas"] + sorted(list(todas_las_cats)))
    with col_metric:
        # La métrica se actualizará según el resultado del filtrado
        count_placeholder = st.empty()

    # --- LÓGICA DE FILTRADO COMBINADA ---
    display_data = []
    for d in data:
        # 1. Filtro por Texto (Título o Autor)
        match_search = (
            search_query in d.get("titulo", "").lower() or 
            search_query in d.get("autor", "").lower()
        )
        
        # 2. Filtro por Categoría
        cats = d.get("categoria", [])
        if cat_filter == "Todas":
            match_cat = True
        else:
            match_cat = (cat_filter in cats) if isinstance(cats, list) else (cat_filter == cats)
        
        if match_search and match_cat:
            display_data.append(d)

    count_placeholder.metric("Libros", len(display_data))

    # --- GRID DE LIBROS ---
    if not display_data:
        st.info("No se encontraron libros con esos criterios.")
    else:
        cols = st.columns(3)
        for i, libro in enumerate(display_data):
            with cols[i % 3]:
                with st.container(border=True):
                    if libro.get("imagen"):
                        st.image(libro["imagen"], use_column_width=True)
                    
                    st.subheader(libro["titulo"])
                    st.write(f"**{libro['autor']}**")
                    
                    cats = libro.get("categoria", [])
                    txt_cats = ", ".join(cats) if isinstance(cats, list) else cats
                    st.caption(f"📅 {libro['fecha']}")
                    st.caption(f"🏷️ {txt_cats}")

if __name__ == "__main__":
    main()