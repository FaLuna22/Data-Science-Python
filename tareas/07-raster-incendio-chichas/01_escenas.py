"""Paso 1: lista las escenas Sentinel-2 L2A del tile 18LYH (sep-oct 2026)
y mide el % de nubes DENTRO del distrito de Chichas con la capa SCL."""
import re, json
import numpy as np
import requests, rasterio
import geopandas as gpd
from rasterio.mask import mask

BUCKET = "https://sentinel-cogs.s3.us-west-2.amazonaws.com"
TILE = "sentinel-s2-l2a-cogs/18/L/YH/2026"
dist = gpd.read_file("chichas.geojson")

escenas = []
for mes in (9, 10):
    xml = requests.get(f"{BUCKET}/?list-type=2&prefix={TILE}/{mes}/&delimiter=/", timeout=60).text
    escenas += re.findall(r"<Prefix>([^<]*_L2A)/</Prefix>", xml)

filas = []
for p in sorted(escenas, key=lambda s: s.split("_")[2]):
    url = f"{BUCKET}/{p}/SCL.tif"
    with rasterio.open(url) as src:
        geom = dist.to_crs(src.crs).geometry
        scl, _ = mask(src, geom, crop=True, nodata=0, filled=True)
    scl = scl[0]
    dentro = scl > 0                                   # 0 = sin dato / fuera del distrito
    nubes = np.isin(scl, [3, 8, 9, 10])                # sombra, nube media/alta, cirro
    cobertura = dentro.sum()
    fila = dict(escena=p.split("/")[-1], fecha=p.split("_")[2],
                pix_validos=int(cobertura),
                nubes_pct=round(float(100 * nubes.sum() / max(cobertura, 1)), 2))
    print(fila); filas.append(fila)

json.dump(filas, open("salidas/escenas_nubes.json", "w"), indent=1)
