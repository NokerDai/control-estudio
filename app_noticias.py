import streamlit as st
import feedparser
import requests
import urllib.parse
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator


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


@st.cache_data(ttl=120)
def fetch_feed(url: str):
    return feedparser.parse(url)


@st.cache_data(ttl=3600)
def translate_to_spanish(text: str) -> str:
    try:
        return translator.translate(text)
    except Exception:
        return text


def build_feed_url(
    country_key: str,
    query: str = "",
    topic: str | None = None,
) -> str:
    cfg = COUNTRIES[country_key]
    params = f"hl={cfg['hl']}&gl={cfg['gl']}&ceid={cfg['ceid']}"

    if query.strip():
        q_enc = urllib.parse.quote(query)
        return f"https://news.google.com/rss/search?q={q_enc}&{params}"

    if topic:
        return (
            "https://news.google.com/rss/headlines/section/topic/"
            f"{topic}?{params}"
        )

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

    except Exception:
        return None

    return None


def main():
    st.set_page_config(
        page_title="Visualizador Google News",
        layout="wide",
    )

    st.title("Visualizador de Google News")
    st.markdown(
        "Titulares por país con selección de tema y traducción opcional al español."
    )

    with st.sidebar:
        st.markdown("---")
        country = st.selectbox("País", list(COUNTRIES.keys()))
        topic_label = st.selectbox("Tema", list(TOPICS.keys()))
        topic_id = TOPICS[topic_label]

        query = st.text_input("Buscar (opcional)", "")
        n_articles = st.slider("Cantidad de artículos", 5, 50, 15)
        translate_titles = st.checkbox("Traducir títulos al español", False)
        fetch_images = st.checkbox("Extraer imágenes (lento)", False)
        resolve_links = st.checkbox("Resolver enlaces finales", True)

    feed_url = build_feed_url(country, query, topic_id)
    st.sidebar.code(feed_url)

    parsed = fetch_feed(feed_url)

    if parsed.bozo:
        st.error("Error al leer el feed RSS.")
        return

    entries = parsed.entries[:n_articles]

    if not entries:
        st.info("No se encontraron artículos.")
        return

    st.divider()

    for entry in entries:
        title_original = entry.get("title", "Sin título")
        summary = entry.get("summary", "")
        link = entry.get("link", "")
        published = entry.get("published", "")

        if translate_titles:
            title_es = translate_to_spanish(title_original)
            title_display = f"{title_es}\n\n*({title_original})*"
        else:
            title_display = title_original

        final_link = resolve_url(link) if resolve_links and link else link

        cols = st.columns([1])

        with cols[0]:
            st.markdown(f"### [{title_display}]({final_link})")
            if published:
                st.caption(published)
            st.write(summary, unsafe_allow_html=True)

        st.divider()


if __name__ == "__main__":
    main()