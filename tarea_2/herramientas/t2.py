"""Funciones que comparten los dos notebooks de la Tarea 2: OCR, métricas y seudonimización.

El audio usa directamente voz.py de la sesión 13 (VAD, faster-whisper, diarización, SRT/TXT).
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
DATOS = RAIZ / "datos"
RAW = DATOS / "raw"
SESION13 = RAIZ.parent / "sessions" / "13-audio-a-texto"


# ───────────────────────────────────────────────────────── archivos
def sha256(ruta: str | Path) -> str:
    """Huella del archivo: dos archivos con el mismo hash son el mismo documento o audio."""
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


# ───────────────────────────────────────────────────────── OCR
def _renglones(idx: list[int], cajas: np.ndarray) -> list[list[int]]:
    """Agrupa cajas en renglones: mismo renglón si los centros verticales distan menos de media línea."""
    if not idx:
        return []
    centro = (cajas[:, 1] + cajas[:, 3]) / 2
    alto = np.median(cajas[idx, 3] - cajas[idx, 1]) or 1.0
    orden = sorted(idx, key=lambda i: centro[i])
    renglones, actual, y_ref = [], [orden[0]], centro[orden[0]]
    for i in orden[1:]:
        if abs(centro[i] - y_ref) <= alto / 2:
            actual.append(i)
        else:
            renglones.append(actual)
            actual, y_ref = [i], centro[i]
    renglones.append(actual)
    return [sorted(r, key=lambda i: cajas[i, 0]) for r in renglones]


def _columnas(idx: list[int], cajas: np.ndarray, ancho: float) -> list[list[int]]:
    """Separa en columnas: cortes donde ninguna caja cubre el eje x en al menos 1 % del ancho de página."""
    cubierto = np.zeros(int(ancho) + 2, dtype=bool)
    for i in idx:
        cubierto[int(cajas[i, 0]):int(cajas[i, 2]) + 1] = True
    cortes, hueco = [], 0
    for x, c in enumerate(cubierto):
        hueco = 0 if c else hueco + 1
        if hueco == max(3, int(0.01 * ancho)):
            cortes.append(x)
    bordes = [0, *cortes, ancho + 1]
    grupos = [[i for i in idx if a <= (cajas[i, 0] + cajas[i, 2]) / 2 < b] for a, b in zip(bordes, bordes[1:])]
    return [g for g in grupos if g]


def ordenar_lineas(textos: list[str], cajas: np.ndarray) -> str:
    """Une las líneas del OCR en orden de lectura, respetando columnas de periódico.

    `cajas` es (n, 4) con x0, y0, x1, y1. Las cajas anchas (más de la mitad de la página: títulos,
    cabeceras) se leen como renglones; las angostas se agrupan en columnas que se leen de izquierda
    a derecha y, dentro de cada una, de arriba abajo.
    """
    if not textos:
        return ""
    cajas = np.asarray(cajas, dtype=float).reshape(-1, 4)
    x_min, x_max = cajas[:, 0].min(), cajas[:, 2].max()
    ancho = max(x_max - x_min, 1.0)
    cajas = cajas - np.array([x_min, 0, x_min, 0])
    anchas = [i for i in range(len(textos)) if cajas[i, 2] - cajas[i, 0] > 0.5 * ancho]
    angostas = [i for i in range(len(textos)) if i not in set(anchas)]
    columnas = _columnas(angostas, cajas, ancho)
    if len(columnas) <= 1:  # una sola columna: renglones normales
        return "\n".join(" ".join(textos[i] for i in r) for r in _renglones(list(range(len(textos))), cajas))
    inicio_cols = min(cajas[i, 1] for i in angostas)
    bloques = [_renglones([i for i in anchas if cajas[i, 1] < inicio_cols], cajas)]
    bloques += [_renglones(c, cajas) for c in columnas]
    bloques.append(_renglones([i for i in anchas if cajas[i, 1] >= inicio_cols], cajas))
    return "\n".join(" ".join(textos[i] for i in r) for b in bloques for r in b)


def leer_paddle(motor, ruta: str | Path) -> dict:
    """OCR con PaddleOCR 3.x. Devuelve texto en orden de lectura, nº de líneas y confianza media."""
    r = motor.predict(str(ruta))[0]
    textos = list(r["rec_texts"])
    cajas = np.asarray(r["rec_boxes"]).reshape(-1, 4) if textos else np.zeros((0, 4))
    puntajes = list(r["rec_scores"])
    return {"texto": ordenar_lineas(textos, cajas), "n_lineas": len(textos),
            "confianza": float(np.mean(puntajes)) if puntajes else 0.0, "crudo": r}


def leer_easyocr(lector, ruta: str | Path) -> dict:
    """OCR con EasyOCR (detector CRAFT + reconocedor CRNN). Misma salida que leer_paddle."""
    res = lector.readtext(str(ruta))
    if not res:
        return {"texto": "", "n_lineas": 0, "confianza": 0.0}
    cajas = np.array([[min(p[0] for p in c), min(p[1] for p in c), max(p[0] for p in c), max(p[1] for p in c)]
                      for c, _, _ in res])
    return {"texto": ordenar_lineas([t for _, t, _ in res], cajas), "n_lineas": len(res),
            "confianza": float(np.mean([s for _, _, s in res]))}


# ───────────────────────────────────────────────────────── métricas
MARCAS = re.compile(r"\[(?:HABLANTE_\d+|H\d+|\?|ilegible|inaudible)\]|^\[\d\d:\d\d:\d\d\]", re.I | re.M)


def normalizar(texto: str) -> str:
    """El mismo criterio para referencias y modelos: minúsculas, NFC, sin puntuación, sin marcas
    de hablante ni [?], espacios simples. Las tildes y la ortografía antigua se conservan."""
    texto = MARCAS.sub(" ", texto or "")
    texto = unicodedata.normalize("NFC", texto.lower())
    texto = re.sub(r"[^\w\s]", " ", texto)
    texto = texto.replace("_", " ")
    return re.sub(r"\s+", " ", texto).strip()


def cer(referencia: str, hipotesis: str) -> float:
    import jiwer
    return jiwer.cer(normalizar(referencia), normalizar(hipotesis) or "∅")


def wer(referencia: str, hipotesis: str) -> float:
    import jiwer
    return jiwer.wer(normalizar(referencia), normalizar(hipotesis) or "∅")


def cer_corpus(referencias: list[str], hipotesis: list[str]) -> float:
    """CER agregado: errores totales / caracteres totales (los documentos largos pesan más)."""
    import jiwer
    return jiwer.cer([normalizar(r) for r in referencias], [normalizar(h) or "∅" for h in hipotesis])


def wer_corpus(referencias: list[str], hipotesis: list[str]) -> float:
    import jiwer
    return jiwer.wer([normalizar(r) for r in referencias], [normalizar(h) or "∅" for h in hipotesis])


# ───────────────────────────────────────────────────────── seudonimización
PATRONES = {
    "DNI": re.compile(r"(?<!\d)\d{8}(?!\d)"),
    "TELEFONO": re.compile(r"(?<!\d)9\d{2}[ -]?\d{3}[ -]?\d{3}(?!\d)"),
    "CORREO": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
}


def seudonimizar(texto: str, reemplazos: dict[str, str], parecido: int = 85) -> tuple[str, int]:
    """Cambia nombres de personas particulares por seudónimos y borra DNI, teléfonos y correos.

    Usa la comparación difusa de voz.py (atrapa 'Vázquez' cuando la lista dice 'Vásquez').
    Devuelve el texto y cuántas entidades se reemplazaron. No reemplaza la revisión humana.
    """
    import sys
    sys.path.insert(0, str(SESION13))
    from voz import seudonimizar as _seudo

    if not isinstance(texto, str) or not texto:
        return texto, 0
    n = 0
    salida = texto
    for nombre, seudo in reemplazos.items():
        nuevo = _seudo(salida, {nombre: seudo}, parecido=parecido)
        n += max(0, nuevo.count(seudo) - salida.count(seudo))
        salida = nuevo
    for etiqueta, patron in PATRONES.items():
        salida, k = patron.subn(f"[{etiqueta}]", salida)
        n += k
    return salida, n
