import streamlit as st
import feedparser
import requests
import urllib.parse
import json
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
import time

# --- CONFIGURACIÓN DE NOTICIAS ---
COUNTRIES = {
    "Argentina": {"gl": "AR", "hl": "es-419", "ceid": "AR:es-419"},
    "United States": {"gl": "US", "hl": "en-US", "ceid": "US:en"},
    "Germany": {"gl": "DE", "hl": "de-DE", "ceid": "DE:de"},
    "China": {"gl": "CN", "hl": "zh-CN", "ceid": "CN:zh-CN"},
}

TOPICS = {
    "Economía / Negocios": "BUSINESS",
    "Ciencia": "SCIENCE",
    "Tecnología": "TECHNOLOGY",
}

translator = GoogleTranslator(source="auto", target="es")

# --- FUNCIONES DE INDEC (DRIVE) ---

@st.cache_data(ttl=60) # Bajamos a 60 segundos para pruebas
def obtener_calendario_indec():
    """Descarga el JSON del calendario desde Google Drive."""
    try:
        id_drive = st.secrets["DRIVE_FILE_ID"]
        # TRUCO: Agregamos un timestamp a la URL para que Google no nos de una versión cacheada
        timestamp = int(time.time())
        url = f"https://drive.google.com/uc?export=download&id={id_drive}&t={timestamp}"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"No se pudo obtener el calendario de INDEC: {e}")
        return None

def mostrar_alerta_indec():
    """Muestra información si hoy hay publicaciones en INDEC."""
    datos = obtener_calendario_indec()
    if not datos:
        return

    # 1. Fecha actual Argentina (UTC-3)
    utc_now = datetime.now(timezone.utc)
    arg_time = utc_now - timedelta(hours=3)
    hoy = arg_time.strftime("%Y-%m-%d")
    hoy_indec = arg_time.strftime("%Y%m%d")  # formato para el link

    publicaciones = datos.get("publicaciones", [])

    publicaciones_hoy = [
        p for p in publicaciones
        if p.get("fecha", "").strip() == hoy
    ]

    if publicaciones_hoy:
        link_calendario = (
            f"https://www.indec.gob.ar/indec/web/Calendario-Fecha-{hoy_indec}"
        )

        for pub in publicaciones_hoy:
            st.info(
                f"📅 **INDEC**: {pub['indicador']}\n\n"
                f"🔗 [Ver calendario INDEC]({link_calendario})"
            )

        st.divider()

# --- FUNCIONES DE NOTICIAS ---

@st.cache_data(ttl=120)
def fetch_feed(url: str):
    return feedparser.parse(url)

@st.cache_data(ttl=3600)
def translate_to_spanish(text: str) -> str:
    try:
        return translator.translate(text)
    except Exception:
        return text

def build_feed_url(country_key: str, query: str = "", topic: str | None = None) -> str:
    cfg = COUNTRIES[country_key]
    params = f"hl={cfg['hl']}&gl={cfg['gl']}&ceid={cfg['ceid']}"
    if query.strip():
        q_enc = urllib.parse.quote(query)
        return f"https://news.google.com/rss/search?q={q_enc}&{params}"
    if topic:
        return f"https://news.google.com/rss/headlines/section/topic/{topic}?{params}"
    return f"https://news.google.com/rss?{params}"

def resolve_url(url: str, timeout: int = 6) -> str:
    try:
        r = requests.head(url, allow_redirects=True, timeout=timeout)
        return r.url
    except Exception:
        try:
            r = requests.get(url, allow_redirects=True, timeout=timeout)
            return r.url
        except Exception:
            return url

# --- APP PRINCIPAL ---

def main():
    st.set_page_config(
        page_title="Noticias", 
        page_icon="📰"
    )

    # 1. INDEC arriba de todo
    mostrar_alerta_indec()

    # 2. BARRA LATERAL
    with st.sidebar:
        country = st.selectbox("País", list(COUNTRIES.keys()))
        topic_label = st.selectbox("Tema", list(TOPICS.keys()))
        topic_id = TOPICS[topic_label]

        query = st.text_input("Buscar (opcional)", "")
        n_articles = st.slider("Cantidad de noticias", 5, 50, 15)
        
        st.write("---")
        translate_titles = st.checkbox("Traducir títulos al español", False)
        resolve_links = st.checkbox("Resolver enlaces finales", True)

    # 3. CARGA DE NOTICIAS
    feed_url = build_feed_url(country, query, topic_id)
    parsed = fetch_feed(feed_url)

    if parsed.bozo:
        st.error("No se pudo cargar el feed de noticias.")
        return

    entries = parsed.entries[:n_articles]

    if not entries:
        st.info("No hay noticias para mostrar.")
        return

    # 4. RENDERIZADO
    for entry in entries:
        title_orig = entry.get("title", "Sin título")
        summary = entry.get("summary", "")
        link = entry.get("link", "")
        pub_date = entry.get("published", "")

        if translate_titles:
            title_es = translate_to_spanish(title_orig)
            title_display = f"{title_es}\n\n*({title_orig})*"
        else:
            title_display = title_orig

        f_link = resolve_url(link) if resolve_links and link else link

        st.markdown(f"### [{title_display}]({f_link})")
        if pub_date:
            st.caption(f"📅 {pub_date}")
        st.write(summary, unsafe_allow_html=True)
        st.divider()

if __name__ == "__main__":
    main()