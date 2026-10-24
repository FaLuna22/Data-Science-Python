"""Piezas comunes: malla de estudio, STAC de Planetary Computer y rutas.

La malla es la de MODIS a 500 m (sinusoidal), recortada al sur andino. Usar la malla nativa
de MCD64A1 y MOD13A1 evita remuestrear 26 años de datos: solo se proyectan una vez la
altitud, la cobertura y los distritos.
"""
import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import requests
from rasterio.transform import Affine

AQUI = Path(__file__).parent
DATOS = AQUI / "datos"            # caché pesada (no va al repo)
SALIDAS = AQUI / "salidas"        # resultados livianos (sí van al repo)
DATOS.mkdir(exist_ok=True)
SALIDAS.mkdir(exist_ok=True)

API = "https://planetarycomputer.microsoft.com/api/stac/v1"
SAS = "https://planetarycomputer.microsoft.com/api/sas/v1/token"

# Sur andino según SENAMHI: Ayacucho, Apurímac, Cusco, Arequipa, Moquegua, Puno y Tacna
DEPARTAMENTOS = {"03": "Apurímac", "04": "Arequipa", "05": "Ayacucho", "08": "Cusco",
                 "18": "Moquegua", "21": "Puno", "23": "Tacna"}
BBOX = [-75.9, -18.6, -68.5, -11.0]
DISTRITOS = AQUI.parent.parent / "sessions/06-geoespacial/lab/Data/peru_distrital_simple.geojson"

# Malla sinusoidal MODIS: tiles h10v10 y h11v10 (latitudes -10 a -20) lado a lado
SINU = ('PROJCS["MODIS Sinusoidal",GEOGCS["Custom",DATUM["Custom",SPHEROID["Custom",6371007.181,0]],'
        'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],PROJECTION["Sinusoidal"],'
        'PARAMETER["longitude_of_center",0],PARAMETER["false_easting",0],PARAMETER["false_northing",0],'
        'UNIT["metre",1]]')
PIX = 463.31271652749973                      # lado del píxel de 500 m
HA_PIX = PIX ** 2 / 1e4                       # 21,47 ha
X0_H10, Y0_V10 = -8895604.157333, -1111950.519667
TILES = ("h10v10", "h11v10")
# Recorte de la malla 2400 x 4800 de los dos tiles: filas y columnas del sur andino
FILA0, FILAS = 280, 1740                      # lat ≈ -11,1 a -18,7
COL0, COLS = 1700, 1670                       # x de la costa de Ayacucho al Titicaca
TRANSFORM = Affine(PIX, 0, X0_H10 + COL0 * PIX, 0, -PIX, Y0_V10 - FILA0 * PIX)


def buscar(coleccion, fechas=None, bbox=BBOX, **extra):
    cuerpo = {"collections": [coleccion], "bbox": bbox, "limit": 1000, **extra}
    if fechas:
        cuerpo["datetime"] = fechas
    feats, url = [], f"{API}/search"
    while url:
        r = requests.post(url, json=cuerpo, timeout=120).json()
        feats += r["features"]
        sig = [l for l in r.get("links", []) if l["rel"] == "next"]
        url, cuerpo = (sig[0]["href"], sig[0].get("body", cuerpo)) if sig else (None, None)
    return feats


@lru_cache
def _token(cuenta, contenedor):
    return requests.get(f"{SAS}/{cuenta}/{contenedor}", timeout=60).json()["token"]


def firmar(item, asset):
    """URL del COG con el token SAS de su contenedor de Azure (sin clave)."""
    href = item["assets"][asset]["href"]
    u = urlparse(href)
    return href + "?" + _token(u.netloc.split(".")[0], u.path.split("/")[1])


def leer_tiles(items, asset):
    """Pega h10v10 y h11v10 de un mismo período y devuelve solo el recorte del sur andino."""
    import rasterio
    partes = {}
    for it in items:
        tile = next(t for t in TILES if f".{t}." in it["id"])
        with rasterio.open(firmar(it, asset)) as s:
            partes[tile] = s.read(1)
    if len(partes) < 2:
        return None
    mosaico = np.hstack([partes["h10v10"], partes["h11v10"]])
    return mosaico[FILA0:FILA0 + FILAS, COL0:COL0 + COLS]


def guardar_json(nombre, obj):
    with open(SALIDAS / nombre, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
