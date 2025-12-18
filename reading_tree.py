"""
reading_tree.py

Script para crear y gestionar un "árbol de lecturas" donde cada entrada tiene:
 - título (clave única)
 - subtítulo
 - ruta a imagen (opcional)
 - lista de "antes" (títulos de otras entradas que deben leerse antes)

Funcionalidades:
 - añadir / eliminar entradas
 - enlazar (añadir un "antes")
 - listar entradas
 - mostrar detalles de una entrada
 - buscar todos los caminos de lectura que llevan a un autor/obra objetivo
 - ordenar topológicamente (si el grafo es acíclico)
 - guardar / cargar a JSON
 - visualizar el grafo (usa networkx + matplotlib)

Uso: ejecutar `python reading_tree.py` y seguir el menú interactivo.
Dependencias: networkx, matplotlib (para visualizar). Instalar con:
    pip install networkx matplotlib

Este script está pensado como base: puede integrarse fácilmente en una app web/GUI,
exportar a formatos más ricos, o adaptarse a un grafo más complejo (múltiples "antes",
pesos, fechas, etiquetas, etc.).
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
import json
import uuid
from pathlib import Path
import networkx as nx
import matplotlib.pyplot as plt


@dataclass
class Node:
    id: str
    title: str
    author: Optional[str] = None
    image_url: Optional[str] = None
    antes: List[str] = None  # lista de títulos que deben ir antes

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "author": self.author,
            "image_url": self.image_url,
            "antes": self.antes or [],
        }

    @staticmethod
    def from_dict(d: Dict):
        return Node(
            id=d.get("id") or str(uuid.uuid4()),
            title=d["title"],
            author=d.get("author"),
            image_url=d.get("image_url"),
            antes=d.get("antes", []),
        )


class ReadingTree:
    def __init__(self):
        # almacenar por título para facilidad de uso (títulos deben ser únicos)
        self.nodes: Dict[str, Node] = {}

    def add_node(self, title: str, author: Optional[str] = None, image_url: Optional[str] = None, antes: Optional[List[str]] = None):
        if title in self.nodes:
            raise ValueError(f"Ya existe una entrada con el título '{title}'.")
        node = Node(id=str(uuid.uuid4()), title=title, author=author, image_url=image_url, antes=antes or [])
        self.nodes[title] = node
        return node

    def remove_node(self, title: str):
        if title not in self.nodes:
            raise KeyError(f"No existe la entrada '{title}'.")
        # remover referencia en otros nodos
        for n in self.nodes.values():
            if title in (n.antes or []):
                n.antes.remove(title)
        del self.nodes[title]

    def link_before(self, child_title: str, before_title: str):
        """Establece que antes_title debe leerse antes que child_title."""
        if child_title not in self.nodes:
            raise KeyError(f"No existe la entrada '{child_title}'.")
        if before_title not in self.nodes:
            raise KeyError(f"No existe la entrada '{before_title}'.")
        node = self.nodes[child_title]
        if before_title in (node.antes or []):
            return
        node.antes.append(before_title)

    def unlink_before(self, child_title: str, before_title: str):
        if child_title not in self.nodes:
            raise KeyError(f"No existe la entrada '{child_title}'.")
        node = self.nodes[child_title]
        if before_title in (node.antes or []):
            node.antes.remove(before_title)

    def to_graph(self) -> nx.DiGraph:
        G = nx.DiGraph()
        for title, node in self.nodes.items():
            G.add_node(title)
        # añadir aristas de "antes" -> nodo
        for title, node in self.nodes.items():
            for b in node.antes or []:
                if b in self.nodes:
                    G.add_edge(b, title)
        return G

    def visualize(self, figsize=(12, 8), save_path: Optional[str] = None):
        G = self.to_graph()
        plt.figure(figsize=figsize)
        try:
            pos = nx.spring_layout(G)
        except Exception:
            pos = None
        nx.draw(G, with_labels=True, arrows=True, node_size=1500, font_size=10)
        if save_path:
            plt.savefig(save_path, bbox_inches='tight')
            print(f"Guardado: {save_path}")
        plt.show()

    def get_paths_to(self, target_title: str, max_paths: int = 100) -> List[List[str]]:
        if target_title not in self.nodes:
            raise KeyError(f"No existe la entrada '{target_title}'.")
        G = self.to_graph()
        # nodos sin 'antes' son raíces
        roots = [t for t, n in self.nodes.items() if not (n.antes)]
        paths = []
        for r in roots:
            if nx.has_path(G, r, target_title):
                for p in nx.all_simple_paths(G, source=r, target=target_title):
                    paths.append(p)
                    if len(paths) >= max_paths:
                        return paths
        return paths

    def topological_order(self) -> List[str]:
        G = self.to_graph()
        if nx.is_directed_acyclic_graph(G):
            return list(nx.topological_sort(G))
        else:
            raise RuntimeError("El grafo contiene ciclos; no es posible un orden topológico.")

    def save_json(self, path: str):
        data = [n.to_dict() for n in self.nodes.values()]
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def load_json(self, path: str):
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(path)
        data = json.loads(p.read_text(encoding='utf-8'))
        self.nodes = {}
        for d in data:
            n = Node.from_dict(d)
            self.nodes[n.title] = n

    def list_nodes(self) -> List[str]:
        return sorted(self.nodes.keys())

    def show_node(self, title: str) -> Dict:
        if title not in self.nodes:
            raise KeyError(f"No existe la entrada '{title}'.")
        return self.nodes[title].to_dict()


def interactive_loop(filename: str = 'reading_tree.json'):
    rt = ReadingTree()
    # si existe archivo, cargarlo
    try:
        rt.load_json(filename)
        print(f"Cargado desde {filename} ({len(rt.nodes)} entradas).")
    except FileNotFoundError:
        print("No se encontró archivo guardado; empezando nuevo árbol.")

    def help_text():
        print("Comandos disponibles:")
        print("  add -> Añadir nueva entrada")
        print("  link -> Añadir 'antes' (relación) entre entradas")
        print("  unlink -> Quitar una relación 'antes'")
        print("  remove -> Eliminar una entrada")
        print("  list -> Listar títulos")
        print("  show -> Mostrar detalles de una entrada")
        print("  paths -> Mostrar caminos hacia un título objetivo")
        print("  topo -> Orden topológico (si aplica)")
        print("  vis -> Visualizar grafo")
        print("  save -> Guardar en archivo")
        print("  quit -> Salir (se guarda automáticamente)")

    help_text()
    while True:
        cmd = input('\n> ').strip().lower()
        try:
            if cmd in ('help', 'h'):
                help_text()
            elif cmd == 'add':
                title = input('Título: ').strip()
                author = input('Autor (opcional): ').strip() or None
                image_url = input('URL de imagen (opcional): ').strip() or None
                antes_raw = input("'Antes' (títulos separados por ; ) (opcional): ").strip()
                antes = [s.strip() for s in antes_raw.split(';') if s.strip()] if antes_raw else []
                rt.add_node(title=title, author=author, image_url=image_url, antes=antes)
                print(f"Añadido: {title}")
            elif cmd == 'link':
                child = input('Título hijo (el que viene después): ').strip()
                before = input('Título que debe ir antes: ').strip()
                rt.link_before(child, before)
                print('Relación creada.')
            elif cmd == 'unlink':
                child = input('Título hijo: ').strip()
                before = input('Título antes: ').strip()
                rt.unlink_before(child, before)
                print('Relación eliminada.')
            elif cmd == 'remove':
                t = input('Título a eliminar: ').strip()
                rt.remove_node(t)
                print('Eliminado.')
            elif cmd == 'list':
                for t in rt.list_nodes():
                    print(' -', t)
            elif cmd == 'show':
                t = input('Título a mostrar: ').strip()
                d = rt.show_node(t)
                print(json.dumps(d, ensure_ascii=False, indent=2))
            elif cmd == 'paths':
                target = input('Título objetivo: ').strip()
                paths = rt.get_paths_to(target)
                if not paths:
                    print('No se encontraron caminos desde raíces hasta el objetivo.')
                else:
                    for i, p in enumerate(paths, 1):
                        print(f"{i}. " + ' -> '.join(p))
            elif cmd == 'topo':
                try:
                    order = rt.topological_order()
                    print('Orden topológico:')
                    print(' -> '.join(order))
                except RuntimeError as e:
                    print('Error:', e)
            elif cmd == 'vis':
                s = input('Ruta para guardar imagen (o dejar vacío para sólo mostrar): ').strip() or None
                rt.visualize(save_path=s)
            elif cmd == 'save':
                rt.save_json(filename)
                print(f'Guardado en {filename}.')
            elif cmd in ('quit', 'exit'):
                rt.save_json(filename)
                print(f'Guardado en {filename}. Adiós.')
                break
            else:
                print('Comando no reconocido. Escriba "help" para ver comandos.')
        except Exception as e:
            print('Error:', e)


if __name__ == '__main__':
    interactive_loop()