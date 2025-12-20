import streamlit as st
import feedparser
import requests
import urllib.parse
from datetime import datetime
from bs4 import BeautifulSoup

st.set_page_config(page_title="Visualizador Google News", layout="wide")

COUNTRIES = {
    "Argentina": {"gl": "AR", "hl": "es-419", "ceid": "AR:es-419"},
    "United States": {"gl": "US", "hl": "en-US", "ceid": "US:en"},
    "Germany": {"gl": "DE", "hl": "de-DE", "ceid": "DE:de"},
    "China": {"gl": "CN", "hl": "zh-CN", "ceid": "CN:zh-CN"},
}

st.title("Visualizador de Google News (RSS)")
st.markdown("Selecciona país, busca por palabra clave (opcional) y carga titulares desde Google News.")

# Sidebar controls
with st.sidebar:
    country = st.selectbox("País", list(COUNTRIES.keys()), index=0)
    q = st.text_input("Buscar (dejar vacío para Top headlines)", "")
    n_articles = st.slider("Número de artículos a mostrar", 5, 50, 15)
    fetch_images = st.checkbox("Extraer imágenes (puede ser lento)", value=False)
    resolve_redirects = st.checkbox("Resolver enlaces finales (sigue redirecciones)", value=True)
    st.markdown("---")
    st.markdown("Cómo funciona:")
    st.markdown("- Usa el RSS oficial de `news.google.com` con parámetros `hl`, `gl`, `ceid`.")
    st.markdown("- Si pides búsqueda, usa `rss/search?q=...`. (Parámetros documentados por servicios de agregación.)")
    st.markdown("")

@st.cache_data(ttl=120)
def fetch_feed(url):
    return feedparser.parse(url)

def build_feed_url(country_key, query=""):
    cfg = COUNTRIES[country_key]
    hl = cfg["hl"]
    gl = cfg["gl"]
    ceid = cfg["ceid"]
    if query and query.strip():
        q_enc = urllib.parse.quote(query)
        return f"https://news.google.com/rss/search?q={q_enc}&hl={hl}&gl={gl}&ceid={ceid}"
    else:
        return f"https://news.google.com/rss?hl={hl}&gl={gl}&ceid={ceid}"

def resolve_url(url, timeout=6):
    # intenta seguir redirecciones para obtener la URL final
    try:
        r = requests.head(url, allow_redirects=True, timeout=timeout)
        return r.url
    except Exception:
        try:
            r = requests.get(url, allow_redirects=True, timeout=timeout)
            return r.url
        except Exception:
            return url

def extract_og_image(article_url, timeout=6):
    try:
        r = requests.get(article_url, timeout=timeout, headers={"User-Agent":"Mozilla/5.0"})
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        og = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name":"og:image"})
        if og and og.get("content"):
            return og["content"]
        # fallback: first <img>
        img = soup.find("img")
        if img and img.get("src"):
            return img["src"]
    except Exception:
        return None
    return None

# Build and fetch
feed_url = build_feed_url(country, q)
st.sidebar.code(feed_url)
st.write(f"Obteniendo feed: **{country}** — {'búsqueda: '+q if q else 'top headlines'}")

parsed = fetch_feed(feed_url)

if parsed.bozo:
    st.error("Error al parsear el feed RSS. Posible bloqueo o cambio en parámetros.")
    st.stop()

entries = parsed.entries[:n_articles]

if not entries:
    st.info("No se encontraron artículos.")
    st.stop()

# Display articles
for entry in entries:
    title = entry.get("title", "Sin título")
    summary = entry.get("summary", "") or entry.get("description", "")
    published = entry.get("published", entry.get("pubDate", ""))
    try:
        # formatea fecha si está disponible
        if published:
            published_parsed = entry.get("published_parsed")
            if published_parsed:
                published = datetime(*published_parsed[:6]).strftime("%Y-%m-%d %H:%M")
    except Exception:
        pass

    # Link: muchas entradas vienen como URLs de Google que redirigen; opcionalmente resolvemos
    link = entry.get("link", "")
    display_link = link
    if resolve_redirects and link:
        display_link = resolve_url(link)

    # intentamos sacar una imagen pequeña (de RSS o de la página)
    image_url = None
    if "media_thumbnail" in entry:
        try:
            image_url = entry.media_thumbnail[0]["url"]
        except Exception:
            pass
    if not image_url and "media_content" in entry:
        try:
            image_url = entry.media_content[0]["url"]
        except Exception:
            pass
    if not image_url and fetch_images and display_link:
        image_url = extract_og_image(display_link)

    # Source
    source = entry.get("source", {}).get("title") if entry.get("source") else None

    # Render
    cols = st.columns([1, 4]) if image_url else st.columns([1])
    if image_url:
        with cols[0]:
            st.image(image_url, use_column_width=True)
        with cols[1]:
            st.markdown(f"### [{title}]({display_link})")
            if source:
                st.caption(f"Fuente: {source} — {published}")
            else:
                st.caption(published)
            st.write(summary, unsafe_allow_html=True)
            st.write(f"[Ver en Google News]({link})")
    else:
        with cols[0]:
            st.markdown(f"### [{title}]({display_link})")
            if source:
                st.caption(f"Fuente: {source} — {published}")
            else:
                st.caption(published)
            st.write(summary, unsafe_allow_html=True)
            st.write(f"[Ver en Google News]({link})")

st.markdown("---")
st.caption("Generado con Google News RSS. Si las URLs aparecen como enlaces de Google (artículos `CBM...`) el redireccionamiento normalmente lleva al artículo original; existe la posibilidad de que algunos parámetros de Google cambien con el tiempo.")