import streamlit as st

def main():
    st.title("📚 Biblioteca")
    st.set_page_config(
        page_title="Biblioteca",
        page_icon="📚"
    )

    # Lista de filósofos en orden cronológico
    PHILOSOPHERS = [
        "Heráclito",
        "Parménides",
        "Sócrates",
        "Platón",
        "Aristóteles",
        "Agustín de Hipona",
        "Tomás de Aquino",
        "René Descartes",
        "Thomas Hobbes",
        "John Locke",
        "Baruch Spinoza",
        "Gottfried W. Leibniz",
        "George Berkeley",
        "Francis Hutcheson",
        "Jean-Jacques Rousseau",
        "David Hume",
        "Immanuel Kant",
        "Jeremy Bentham",
        "G. W. F. Hegel",
        "Arthur Schopenhauer",
        "Søren Kierkegaard",
        "John Stuart Mill",
        "Karl Marx",
        "Friedrich Nietzsche",
        "Gottlob Frege",
        "Max Weber",
        "Bertrand Russell",
        "Karl Polanyi",
        "Ludwig Wittgenstein",
        "Edmund Husserl",
        "Martin Heidegger",
        "Karl Popper",
        "Jean-Paul Sartre",
        "Simone de Beauvoir",
        "Michel Foucault",
    ]

    st.set_page_config(page_title="Biblioteca Filosófica", layout="wide")
    st.title("Biblioteca Filosófica (orden cronológico)")

    # Inicializar estado
    if "library" not in st.session_state:
        st.session_state.library = {philosopher: [] for philosopher in PHILOSOPHERS}

    # Renderizar filósofos
    for philosopher in PHILOSOPHERS:
        with st.expander(philosopher, expanded=False):
            st.subheader("Libros")

            # Mostrar libros existentes
            if st.session_state.library[philosopher]:
                cols = st.columns(3)
                for idx, book in enumerate(st.session_state.library[philosopher]):
                    with cols[idx % 3]:
                        st.image(book["image"], use_container_width=True)
                        st.markdown(f"**{book['title']}**")
            else:
                st.info("No hay libros agregados todavía.")

            st.divider()
            st.markdown("### Agregar libro")

            title = st.text_input(
                "Título del libro",
                key=f"title_{philosopher}",
            )
            image_url = st.text_input(
                "URL de la imagen de portada",
                key=f"image_{philosopher}",
            )

            if st.button("Agregar libro", key=f"add_{philosopher}"):
                if title and image_url:
                    st.session_state.library[philosopher].append(
                        {"title": title, "image": image_url}
                    )
                    st.success("Libro agregado correctamente")
                else:
                    st.error("Debes completar el título y la URL de la imagen")