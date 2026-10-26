"""Descarga el corpus de la Tarea 2. Todos los archivos tienen licencia libre y se citan en datos/fuentes.csv.

    .venv/Scripts/python tarea_2/herramientas/descargar.py

Qué baja (nada de esto se versiona: queda en tarea_2/datos/raw/):

- 25 documentos peruanos de Wikimedia Commons (8 impresos, 8 fotos con sombra o inclinación,
  9 manuscritos) y 5 suplentes por si alguno resulta ilegible. Se pide la versión de Commons
  limitada a 1920 px de ancho (un tamaño estándar de miniatura), suficiente para OCR y mucho más liviana que el original.
- Entrevistas y testimonios en español peruano de Wikimedia Commons (CC BY-SA 4.0 / CC BY 4.0).
  Algunas entrevistas son videos (webm, hasta ~50 MB): de ellos solo se usa el audio.
- 6 frases de OpenSLR 73 (español peruano leído, Google, CC BY-SA 4.0), una por hablante,
  leídas por partes con HTTP Range (no se bajan los zips de 900 MB).

Buenas prácticas: User-Agent descriptivo y una pausa de 1,5 s entre solicitudes.
"""
from __future__ import annotations

import io
import json
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
RAW = RAIZ / "datos" / "raw"
UA = {"User-Agent": "tarea2-voces-documentos/1.0 (curso Data Science Python QLAB; github.com/FaLuna22)"}
PAUSA = 1.5
FECHA = time.strftime("%Y-%m-%d")

# id: (tipo, archivo en Commons, ¿la imagen se puede mostrar en el dashboard?)
# publicable=False cuando el documento trata de personas particulares identificables
# (partidas de bautismo, diplomas o recibos a nombre de alguien): solo se publica su texto seudonimizado.
DOCUMENTOS = {
    # impresos nítidos
    "doc_01": ("impreso", "Comunicado minsa primer fallecido covid-19 Perú.png", True),
    "doc_02": ("impreso", "Comunicado oficial N 21 sobre el fallecimiento de 2 personas por covid-19 en Perú.jpg", True),
    "doc_03": ("impreso", "Carta de agradecimiento del secretario de la Presidencia de la República Nazario Chávez Aliaga al pintor Segundo Ciro Gallardo Gallo en nombre del presidente Manuel Prado Ugarteche.jpg", True),
    "doc_04": ("impreso", "Boletin-N161 de la Liga de Fútbol de Lima.png", True),
    "doc_05": ("impreso", "El Comercio - Lima. Perú y Ecuador. 3-3-1842.jpg", True),
    "doc_06": ("impreso", "Inundación Carhuaz 1844.png", True),
    "doc_07": ("impreso", "Carátula de El Montonero (n. 12, año 1834).jpg", True),
    "doc_08": ("impreso", "La Campana Arequipa 1873.jpg", True),
    # fotos de celular con sombras, brillo o inclinación
    "doc_09": ("foto", "Publicación de la Revista Epoca, julio 1984 ..JPG", True),
    "doc_10": ("foto", "Publicación del Diario \"El Tiempo\" año 1973..JPG", True),
    "doc_11": ("foto", "Periódico Acción de la UR.jpg", True),
    "doc_12": ("foto", "Otorgamiento Municipal.jpg", False),
    "doc_13": ("foto", "Nombramiento municipal de Moyobamba 2015.jpg", False),
    "doc_14": ("foto", "Canciller inaugura exposición del centenario del retorno de Tarata al Perú.jpg", True),
    "doc_15": ("foto", "Noticia diario la Industria, Trujillo 1923.png", True),
    "doc_16": ("foto", "Un Acto Solemne Viene Realizando Actividades por el Bicentenario 01.jpg", True),
    # manuscritos
    "doc_17": ("manuscrito", "Acta de Independencia Peru.jpg", True),
    "doc_18": ("manuscrito", "Acta de la Indepencia del Perù.jpg", True),
    "doc_19": ("manuscrito", "Asiento de la partida de bautismo de Raúl Porras Barrenechea.jpg", False),
    "doc_20": ("manuscrito", "Capitulacón de Ayacucho2.jpg", True),
    "doc_21": ("manuscrito", "Joseolaya partida nacimiento chica.jpg", False),
    "doc_22": ("manuscrito", "Libro de Bautismos en la Gran Villa de Lampa 1832.jpg", False),
    "doc_23": ("manuscrito", "Libro de Bautismos en la Gran Villa de Lampa 1871.jpg", False),
    "doc_24": ("manuscrito", "Peruvian Telephone Company receipt Lima 1895.JPG", False),
    "doc_25": ("manuscrito", "Socgeolima.jpg", False),
}
# suplentes: reemplazan a un documento ilegible del mismo tipo
SUPLENTES = {
    "sup_impreso_1": ("impreso", "Acta de Creación de los Símbolos para el Distrito de Mache.jpg", True),
    "sup_impreso_2": ("impreso", "Himno Chyo.jpg", True),
    "sup_foto_1": ("foto", "Canciller inaugura exposición del centenario del retorno de Tarata al Perú - 54778280176.jpg", True),
    "sup_foto_2": ("foto", "Estado General de Miguel Grau.jpg", True),
    "sup_manuscrito_1": ("manuscrito", "Perucent.jpg", False),
}

# nombre local: archivo en Commons. Todas son entrevistas o testimonios en español peruano.
AUDIOS = {
    "agustino_1": "Entrevista 1 en la Av. Rivagüero - El Agustino.ogg",
    "agustino_2": "Entrevista 2 en la Av. Rivagüero - El Agustino.ogg",
    "fenmucarinap_1": "Entrevista-Aurora Coronado-organización de mujeres indígenas-fiestas patrias.ogg",
    "fenmucarinap_2": "Entrevista a Luz Merida-Organización de mujeres indígenas-fiestas patrias-protesta.ogg",
    "ciudadano": "Entrevista a ciudadano del Perú.ogg",
    "unmsm_2": "Entrevista 2.wav",
    "medio_tiempo": "Entrevista en el medio tiempo.opus",
    "que_es_peru": "¿Qué es el Perú?2 entrevista.webm",
    "magdalena_1": "Entrevista en Magdalena por Fiestas Patrias Perú 2022 (1).webm",
    "magdalena_2": "Entrevista en Magdalena por Fiestas Patrias Perú 2022 (2).webm",
    "magdalena_3": "Entrevista en Magdalena por Fiestas Patrias Perú 2022 (3).webm",
    "plaza_armas": "Entrevista Por el día de la Independencia del Perú.webm",
    **{f"salas_{i}": f"Testimonio {i} - Salas, pantallas y archivos.ogg" for i in range(2, 9)},
    "salas_1": "Testimonio 1 - Salas, pantallas y archivos 01.ogg",
}

OPENSLR73 = "https://www.openslr.org/resources/73/es_pe_{sexo}.zip"


def _get(url: str, rango=None) -> bytes:
    cab = dict(UA)
    if rango:
        cab["Range"] = f"bytes={rango[0]}-{rango[1]}"
    for intento in range(12):
        time.sleep(PAUSA)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=cab), timeout=300) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code != 429 or intento == 11:
                raise
            espera = int(e.headers.get("Retry-After") or 0) or 60 * (intento + 1)
            print(f"  429 (demasiadas solicitudes): espero {espera} s")
            time.sleep(espera)


def _info_commons(titulos: list[str], ancho: int | None = None) -> dict:
    """Metadatos de Commons (URL, licencia, autor, miniatura) para varios archivos a la vez."""
    import html
    import re
    salida = {}
    for i in range(0, len(titulos), 20):
        p = dict(action="query", titles="|".join("File:" + t for t in titulos[i:i + 20]), prop="imageinfo",
                 iiprop="url|size|mime|extmetadata|metadata", format="json")
        if ancho:
            p["iiurlwidth"] = ancho
        r = json.loads(_get("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(p)))
        normal = {n["to"]: n["from"] for n in r["query"].get("normalized", [])}
        for pg in r["query"]["pages"].values():
            ii = pg["imageinfo"][0]
            md = ii.get("extmetadata", {})
            limpio = lambda k: re.sub(r"<[^>]+>", "", html.unescape(md.get(k, {}).get("value", ""))).strip()
            titulo = normal.get(pg["title"], pg["title"])[5:]
            salida[titulo] = dict(url=ii["url"], thumb=ii.get("thumburl"), ancho=ii.get("width"), mime=ii["mime"],
                                  licencia=limpio("LicenseShortName"), autor=limpio("Artist")[:150],
                                  pagina=ii["descriptionurl"])
    return salida


def bajar_documentos() -> pd.DataFrame:
    destino = RAW / "documentos"
    destino.mkdir(parents=True, exist_ok=True)
    todos = DOCUMENTOS | SUPLENTES
    info = _info_commons([t for _, t, _ in todos.values()], ancho=1920)
    filas = []
    for id_, (tipo, titulo, publicable) in todos.items():
        i = info[titulo]
        # si el original mide menos de 1920 px, Commons devuelve el original como "miniatura"
        url = i["thumb"] if i["thumb"] and (i["ancho"] or 0) > 1920 else i["url"]
        url = url.split("?")[0]  # Commons agrega parámetros de seguimiento (utm_*) que no son parte del nombre
        ext = ".png" if url.lower().endswith(".png") else ".jpg"
        ruta = destino / f"{id_}{ext}"
        if not ruta.exists():
            ruta.write_bytes(_get(url))
        filas.append({"id": id_, "modalidad": "documento", "tipo": tipo, "archivo": ruta.relative_to(RAIZ).as_posix(),
                      "titulo_original": titulo, "fuente_url": i["pagina"], "url_archivo": url,
                      "licencia": i["licencia"], "autor": i["autor"], "publicable": publicable,
                      "acceso": "Descarga directa desde Wikimedia Commons (herramientas/descargar.py)",
                      "fecha_extraccion": FECHA})
        print(f"{id_:18s} {tipo:10s} {i['licencia']:15s} {titulo[:60]}")
    return pd.DataFrame(filas)


def bajar_audios() -> pd.DataFrame:
    destino = RAW / "audio" / "originales"
    destino.mkdir(parents=True, exist_ok=True)
    info = _info_commons(list(AUDIOS.values()))
    filas = []
    for local, titulo in AUDIOS.items():
        i = info[titulo]
        i["url"] = i["url"].split("?")[0]  # sin los parámetros utm_* que agrega Commons
        ruta = destino / f"{local}{Path(urllib.parse.unquote(i['url'])).suffix}"
        if not ruta.exists():
            ruta.write_bytes(_get(i["url"]))
        filas.append({"id": local, "modalidad": "audio", "archivo": ruta.relative_to(RAIZ).as_posix(),
                      "titulo_original": titulo, "fuente_url": i["pagina"], "url_archivo": i["url"],
                      "licencia": i["licencia"], "autor": i["autor"], "publicable": True,
                      "acceso": "Descarga directa desde Wikimedia Commons (herramientas/descargar.py)",
                      "fecha_extraccion": FECHA})
        print(f"{local:16s} {i['licencia']:12s} {ruta.stat().st_size / 1e6:6.1f} MB  {titulo[:60]}")
    return pd.DataFrame(filas)


def bajar_openslr73(n_por_sexo: int = 3, semilla: int = 2026) -> pd.DataFrame:
    """Frases de español peruano leído con su transcripción oficial. Reusa el lector por partes de la sesión 13."""
    sys.path.insert(0, str(RAIZ.parent / "sessions" / "13-audio-a-texto"))
    from datos import ZipRemoto, _guardar_16k

    destino = RAW / "audio" / "openslr73"
    destino.mkdir(parents=True, exist_ok=True)
    filas = []
    for sexo in ["female", "male"]:
        url = OPENSLR73.format(sexo=sexo)
        z = zipfile.ZipFile(ZipRemoto(url))
        lineas = z.read("line_index.tsv").decode("utf-8").strip().splitlines()
        tabla = pd.DataFrame([l.split("\t") for l in lineas], columns=["id", "texto"])
        tabla["hablante"] = tabla["id"].str.rsplit("_", n=1).str[0]
        tabla = tabla[tabla["texto"].str.split().str.len().between(12, 25)]  # frases largas: más palabras para el WER
        hablantes = sorted(tabla["hablante"].unique())
        random.Random(semilla).shuffle(hablantes)
        for h in hablantes[:n_por_sexo]:
            fila = tabla[tabla["hablante"] == h].sample(1, random_state=semilla).iloc[0]
            ruta = destino / f"{fila['id']}.wav"
            if not ruta.exists():
                _guardar_16k(z.read(f"{fila['id']}.wav"), ruta)
            filas.append({"id": f"openslr_{fila['id']}", "modalidad": "audio", "archivo": ruta.relative_to(RAIZ).as_posix(),
                          "titulo_original": f"{fila['id']}.wav", "fuente_url": "https://www.openslr.org/73/",
                          "url_archivo": url, "licencia": "CC BY-SA 4.0",
                          "autor": "Google (Guevara-Rukoz et al., 2020)", "publicable": True,
                          "acceso": f"Archivo {fila['id']}.wav dentro de {url.rsplit('/', 1)[-1]} (lectura por HTTP Range)",
                          "fecha_extraccion": FECHA, "texto_oficial": fila["texto"].strip()})
            print(f"openslr {fila['id']}: {fila['texto'][:70]}")
    return pd.DataFrame(filas)


if __name__ == "__main__":
    docs = bajar_documentos()
    auds = bajar_audios()
    slr = bajar_openslr73()
    catalogo = pd.concat([docs, auds, slr], ignore_index=True)
    catalogo.to_csv(RAW / "catalogo_descargas.csv", index=False)
    total = sum(p.stat().st_size for p in RAW.rglob("*") if p.is_file())
    print(f"\n{len(docs)} documentos, {len(auds)} audios de Commons, {len(slr)} frases OpenSLR -> {total / 1e6:.0f} MB en {RAW}")
