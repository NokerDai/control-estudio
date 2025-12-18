"""
streamlit_app.py

App web en Streamlit para gestionar y visualizar un árbol de lecturas filosóficas.
Usa el mismo modelo de datos que reading_tree.py (título, autor, image_url, antes).

Ejecutar con:
    streamlit run streamlit_app.py

Dependencias:
    pip install streamlit networkx matplotlib
"""

import json
from pathlib import Path
import uuid
from typing import List, Optional, Dict

import streamlit as st
import networkx as nx
import matplotlib.pyplot as plt


# -----------------------------
# MODELO DE DATOS
# -----------------------------
class Node:
    def __init__(self, title: str, author: Optional[str] = None, image_url: Optional[str] = None, antes: Optional[List[str]] = None, id: Optional[str] = None):
        self.id = id or str(uuid.uuid4())
        self.title = title
        self.author = author
        self.image_url = image_url
        self.antes = antes or []

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "title": self.title,
            "author": self.author,
            "image_url": self.image_url,
            "antes": self.antes,
        }

    @staticmethod
    def from_dict(d: Dict):
        return Node(
            id=d.get("id"),
            title=d["title"],
            author=d.get("author"),
            image_url=d.get("image_url"),
            antes=d.get("antes", []),
        )


class ReadingTree:
    def __init__(self):
        self.nodes: Dict[str, Node] = {}

    def add_node(self, title, author=None, image_url=None, antes=None):
        if title in self.nodes:
            raise ValueError("Ya existe un título con ese nombre")
        self.nodes[title] = Node(title, author, image_url, antes or [])

    def to_graph(self) -> nx.DiGraph:
        G = nx.DiGraph()
        for t in self.nodes:
            G.add_node(t)
        for t, n in self.nodes.items():
            for b in n.antes:
                if b in self.nodes:
                    G.add_edge(b, t)
        return G

    def save(self, path: str):
        data = [n.to_dict() for n in self.nodes.values()]
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self, path: str):
        p = Path(path)
        if not p.exists():
            return
        data = json.loads(p.read_text(encoding="utf-8"))
        for d in data:
            n = Node.from_dict(d)
            self.nodes[n.title] = n


# -----------------------------
# CONFIG STREAMLIT
# -----------------------------
st.set_page_config(page_title="Árbol de lecturas", layout="wide")
st.title("Árbol de lecturas filosóficas")

DATA_FILE = "reading_tree.json"

if "tree" not in st.session_state:
    tree = ReadingTree()
    tree.load(DATA_FILE)
    st.session_state.tree = tree


tree: ReadingTree = st.session_state.tree


# -----------------------------
# SIDEBAR: AÑADIR ENTRADAS
# -----------------------------
st.sidebar.header("Añadir obra")

with st.sidebar.form("add_form"):
    title = st.text_input("Título")
    author = st.text_input("Autor")
    image_url = st.text_input("URL de imagen")
    antes = st.multiselect("Leer antes", options=sorted(tree.nodes.keys()))
    submitted = st.form_submit_button("Añadir")

    if submitted:
        if not title:
            st.sidebar.error("El título es obligatorio")
        else:
            try:
                tree.add_node(title, author or None, image_url or None, antes)
                tree.save(DATA_FILE)
                st.sidebar.success("Obra añadida")
                st.rerun()
            except Exception as e:
                st.sidebar.error(str(e))


# -----------------------------
# COLUMNA IZQUIERDA: LISTA
# -----------------------------
col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("Obras")
    selected = st.selectbox("Seleccionar", options=["—"] + sorted(tree.nodes.keys()))


# -----------------------------
# COLUMNA DERECHA: DETALLE
# -----------------------------
with col2:
    if selected and selected != "—":
        n = tree.nodes[selected]
        st.subheader(n.title)
        if n.author:
            st.markdown(f"**Autor:** {n.author}")
        if n.image_url:
            st.image(n.image_url, use_container_width=True)
        if n.antes:
            st.markdown("**Leer antes:**")
            for a in n.antes:
                st.markdown(f"- {a}")
    else:
        st.info("Selecciona una obra para ver detalles")


# -----------------------------
# VISUALIZACIÓN DEL GRAFO
# -----------------------------
st.divider()
st.subheader("Mapa de lecturas")

if tree.nodes:
    G = tree.to_graph()
    fig = plt.figure(figsize=(10, 6))
    pos = nx.spring_layout(G)
    nx.draw(G, pos, with_labels=True, node_size=2000, font_size=9)
    st.pyplot(fig)
else:
    st.info("Aún no hay obras cargadas")