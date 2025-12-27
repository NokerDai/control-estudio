import streamlit as st

def main():
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

    # Estado
    if "library" not in st.session_state:
        st.session_state.library = {p: [] for p in PHILOSOPHERS}

    if "active_philosopher" not in st.session_state:
        st.session_state.active_philosopher = None

    # UI principal
    for philosopher in PHILOSOPHERS:
        col1, col2 = st.columns([9, 1])

        with col1:
            st.markdown(f"## {philosopher}")

        with col2:
            if st.button("＋", key=f"add_{philosopher}"):
                st.session_state.active_philosopher = philosopher

        books = st.session_state.library[philosopher]

        if books:
            cols = st.columns(5)
            for i, book in enumerate(books):
                with cols[i % 5]:
                    st.image(book["image"], use_container_width=True)
                    st.caption(book["title"])
        else:
            st.markdown("_Sin libros aún._")

        st.divider()

    # Pseudo-modal compatible
    if st.session_state.active_philosopher:
        st.markdown("---")
        st.subheader(f"Agregar libro a {st.session_state.active_philosopher}")

        with st.container():
            title = st.text_input("Título del libro", key="modal_title")
            image_url = st.text_input("URL de la portada", key="modal_image")

            c1, c2 = st.columns(2)

            with c1:
                if st.button("Agregar libro"):
                    if title and image_url:
                        st.session_state.library[
                            st.session_state.active_philosopher
                        ].append({"title": title, "image": image_url})
                        st.session_state.active_philosopher = None
                        st.rerun()
                    else:
                        st.error("Completa todos los campos")

            with c2:
                if st.button("Cancelar"):
                    st.session_state.active_philosopher = None
                    st.rerun()