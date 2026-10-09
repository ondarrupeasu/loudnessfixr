"""Ninguna clase define dos veces el mismo método.

⚠️ Python no avisa: el segundo `def` pisa al primero y la clase funciona igual. Así que un
arreglo escrito en la copia muerta no cambia nada, y parece que el arreglo está mal. Pasó en
IngestR (`ReviewPanel` tenía quince métodos pegados por duplicado) y en PostHandleR.

Prueba común de la suite (la reparte MissionControl, idéntica en todas las apps). Solo usa la
biblioteca estándar: vale con pytest, con unittest o lanzándola a mano.
"""

import ast
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
# Lo que no es código de la app: entornos, compilados, terceros y los propios tests.
FUERA = {"build", "dist", "dist_out", "vendor", "node_modules", "__pycache__", "tests", "test"}


def _es_de_la_app(fichero: Path) -> bool:
    partes = fichero.relative_to(RAIZ).parts[:-1]
    return not any(p in FUERA or p.startswith((".", "venv")) for p in partes)


def metodos_repetidos():
    repetidos = []
    for fichero in sorted(RAIZ.rglob("*.py")):
        if not _es_de_la_app(fichero):
            continue
        arbol = ast.parse(fichero.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.ClassDef):
                continue
            vistos = set()
            for h in nodo.body:
                if not isinstance(h, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                # Un `@x.setter` (o `.getter`, `.deleter`) repite el nombre A PROPÓSITO: es la
                # otra mitad de la misma propiedad. Igual un `@overload` de typing.
                if any((isinstance(d, ast.Attribute) and d.attr in ("setter", "getter", "deleter"))
                       or (isinstance(d, ast.Name) and d.id == "overload")
                       or (isinstance(d, ast.Attribute) and d.attr == "overload")
                       for d in h.decorator_list):
                    continue
                if h.name in vistos:
                    rel = fichero.relative_to(RAIZ).as_posix()
                    repetidos.append(f"{rel}:{h.lineno} {nodo.name}.{h.name}")
                vistos.add(h.name)
    return repetidos


class SinMetodosDuplicados(unittest.TestCase):
    def test_ninguna_clase_define_dos_veces_el_mismo_metodo(self):
        repetidos = metodos_repetidos()
        self.assertFalse(repetidos, "definidos dos veces (el segundo pisa al primero): "
                         + ", ".join(repetidos))


if __name__ == "__main__":
    unittest.main()
