import streamlit as st
import feedparser
import requests
import urllib.parse
from datetime import datetime
from bs4 import BeautifulSoup


COUNTRIES = {
    "Argentina": {"gl": "AR", "hl": "es-419", "ceid": "AR:es-419"},
    "United States": {"gl": "US", "hl": "en-US", "ceid": "US:en"},
    "Germany": {"gl": "DE", "hl": "de-DE", "ceid": "DE:de"},
    "China": {"gl": "CN", "hl": "zh-CN", "ceid": "CN:zh-CN"},
}


@st.cache_data(ttl=120)
def fetch_feed(url: str):
    return feedparser.parse(url)


def build_feed_url(country_key: str, query: str = "") -> str:
    cfg = COUNTRIES[country_key]
    if query.strip():
        q_enc = urllib.parse.quote(query)
        return (
            f"https://news.google.com/rss/search?q={q_enc}"
            f"&hl={cfg['hl']}&gl={cfg['gl']}&ceid={cfg['ceid']}"
        )
    return (
        f"https://news.google.com/rss"
        f"?hl={cfg['hl']}&gl={cfg['gl']}&ceid={cfg['ceid']}"
    )


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


def extract_og_image(article_url: str, timeout: int = 6):
    try:
        r = requests.get(
            article_url,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, "html.parser")
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            return og["content"]

        img = soup.find("img")
        if img and img.get("src"):
            return img["src"]

    except Exception:
        return None

    return None


def main():
    st.set_page_config(
        page_title="Visualizador Google News",
        layout="wide",
    )

    st.title("Visualizador de Google News (RSS)")
    st.markdown(
        "Selecciona país y (opcionalmente) una búsqueda para "
        "ver titulares de Google News."
    )

    # Sidebar
    with st.sidebar:
        country = st.selectbox("País", list(COUNTRIES.keys()))
        query = st.text_input("Buscar (opcional)", "")
        n_articles = st.slider("Cantidad de artículos", 5, 50, 15)
        fetch_images = st.checkbox("Extraer imágenes (lento)", False)
        resolve_links = st.checkbox("Resolver enlaces finales", True)

    feed_url = build_feed_url(country, query)
    st.sidebar.code(feed_url)

    parsed = fetch_feed(feed_url)

    if parsed.bozo:
        st.error("Error al leer el feed RSS.")
        return

    entries = parsed.entries[:n_articles]

    if not entries:
        st.info("No se encontraron artículos.")
        return

    for entry in entries:
        title = entry.get("title", "Sin título")
        summary = entry.get("summary", "")
        link = entry.get("link", "")
        published = entry.get("published", "")

        if resolve_links and link:
            final_link = resolve_url(link)
        else:
            final_link = link

        image_url = None
        if fetch_images and final_link:
            image_url = extract_og_image(final_link)

        cols = st.columns([1, 4]) if image_url else st.columns([1])

        if image_url:
            with cols[0]:
                st.image(image_url, use_column_width=True)
            with cols[1]:
                st.markdown(f"### [{title}]({final_link})")
                st.caption(published)
                st.write(summary, unsafe_allow_html=True)
        else:
            with cols[0]:
                st.markdown(f"### [{title}]({final_link})")
                st.caption(published)
                st.write(summary, unsafe_allow_html=True)


if __name__ == "__main__":
    main()