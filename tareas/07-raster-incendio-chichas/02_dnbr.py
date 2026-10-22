"""Paso 2: NBR antes/después, dNBR, hectáreas por severidad y cruce con WorldCover."""
import json
import numpy as np
import rasterio, geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from rasterio.mask import mask
from rasterio.warp import reproject, Resampling

BUCKET = "https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/18/L/YH/2026"
PRE = "9/S2C_18LYH_20260915_0_L2A"
POST = "10/S2A_18LYH_20261017_0_L2A"
WC = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_S18W075_Map.tif"
dist = gpd.read_file("chichas.geojson")

def leer(escena, banda):
    with rasterio.open(f"{BUCKET}/{escena}/{banda}.tif") as src:
        arr, tr = mask(src, dist.to_crs(src.crs).geometry, crop=True, nodata=0, filled=True)
        return arr[0].astype("float32"), tr, src.crs

def nbr(escena):
    b8a, tr, crs = leer(escena, "B8A")   # NIR estrecho, 20 m
    b12, _, _ = leer(escena, "B12")      # SWIR, 20 m
    scl, _, _ = leer(escena, "SCL")
    malo = np.isin(scl, [0, 1, 3, 6, 8, 9, 10, 11])   # sin dato, saturado, sombra, agua, nubes, nieve
    v = (b8a - b12) / (b8a + b12 + 1e-6)
    v[malo] = np.nan
    return v, tr, crs

nbr_pre, tr, crs = nbr(PRE)
nbr_post, _, _ = nbr(POST)
dnbr = nbr_pre - nbr_post
validos = np.isfinite(dnbr)
HA = 20 * 20 / 10_000                                # 1 píxel de 20 m = 0,04 ha

# Clases USGS (Key & Benson 2006)
cortes = [0.10, 0.27, 0.44, 0.66, 9]
nombres = ["Baja", "Moderada-baja", "Moderada-alta", "Alta"]
sev = np.zeros(dnbr.shape, "uint8")
for i, (a, b) in enumerate(zip(cortes[:-1], cortes[1:]), 1):
    sev[validos & (dnbr >= a) & (dnbr < b)] = i
quemado = sev >= 2                                   # dNBR >= 0,27, mismo umbral que la clase

res = {"pre": PRE.split("/")[1], "post": POST.split("/")[1],
       "pix_validos": int(validos.sum()),
       "ha_validas": round(validos.sum() * HA, 1),
       "ha_por_severidad": {n: round(float((sev == i).sum() * HA), 1) for i, n in enumerate(nombres, 1)},
       "ha_quemadas_dnbr_027": round(float(quemado.sum() * HA), 1),
       "dnbr_p99": round(float(np.nanpercentile(dnbr, 99)), 3)}

# Cruce con ESA WorldCover 2021 (10 m) remuestreado a la grilla de 20 m (moda)
wc = np.zeros(dnbr.shape, "uint8")
with rasterio.open(WC) as src:
    reproject(rasterio.band(src, 1), wc, dst_transform=tr, dst_crs=crs, resampling=Resampling.mode)
CLASES = {10: "Bosque", 20: "Matorral", 30: "Pastizal", 40: "Cultivo", 50: "Urbano",
          60: "Suelo desnudo / escasa veg.", 70: "Nieve", 80: "Agua", 90: "Humedal", 95: "Manglar", 100: "Musgo/liquen"}
res["ha_quemadas_por_cobertura"] = {CLASES.get(int(c), str(c)): round(float(((wc == c) & quemado).sum() * HA), 1)
                                    for c in np.unique(wc[quemado])}
res["ha_cobertura_distrito"] = {CLASES.get(int(c), str(c)): round(float(((wc == c) & validos).sum() * HA), 1)
                                for c in np.unique(wc[validos]) if c}

# Ubicación de los parches quemados (centroides de píxeles quemados)
filas, cols = np.nonzero(quemado)
if len(filas):
    from rasterio.transform import xy
    from pyproj import Transformer
    x, y = xy(tr, filas, cols)
    lon, lat = Transformer.from_crs(crs, 4326, always_xy=True).transform(np.mean(x), np.mean(y))
    res["centroide_quemado_lonlat"] = [round(lon, 4), round(lat, 4)]
json.dump(res, open("salidas/resultados.json", "w"), indent=1, ensure_ascii=False)
print(json.dumps(res, indent=1, ensure_ascii=False))

# Guardar dNBR como GeoTIFF
with rasterio.open("salidas/dnbr_chichas.tif", "w", driver="GTiff", height=dnbr.shape[0], width=dnbr.shape[1],
                   count=1, dtype="float32", crs=crs, transform=tr, nodata=np.nan, compress="deflate") as dst:
    dst.write(dnbr, 1)

# Mapas
ext = [tr.c, tr.c + tr.a * dnbr.shape[1], tr.f + tr.e * dnbr.shape[0], tr.f]
borde = dist.to_crs(crs)
fig, ax = plt.subplots(1, 2, figsize=(13, 6.5))
im = ax[0].imshow(dnbr, cmap="RdYlGn_r", vmin=-0.3, vmax=0.7, extent=ext)
fig.colorbar(im, ax=ax[0], shrink=0.75, label="dNBR")
ax[0].set_title("dNBR = NBR(15-sep) − NBR(17-oct)")
cm = ListedColormap(["#f0f0f0", "#fee08b", "#fdae61", "#f46d43", "#a50026"])
ax[1].imshow(np.where(validos, sev, np.nan), cmap=cm, norm=BoundaryNorm(np.arange(-0.5, 5.5), 5), extent=ext)
ax[1].set_title(f"Severidad USGS · quemado (dNBR ≥ 0,27): {res['ha_quemadas_dnbr_027']:,.0f} ha")
from matplotlib.patches import Patch
ax[1].legend(handles=[Patch(color=c, label=l) for c, l in zip(cm.colors, ["No quemado", *nombres])],
             loc="lower left", fontsize=8)
for a in ax:
    borde.boundary.plot(ax=a, color="black", lw=1)
    a.set_xticks([]); a.set_yticks([])
fig.suptitle("Chichas (Condesuyos, Arequipa) · Sentinel-2 L2A, 20 m · nubes 0,01 % / 0,02 %", fontsize=13)
fig.tight_layout(); fig.savefig("salidas/mapa_dnbr_chichas.png", dpi=130)

# Gráfico de barras por cobertura
q = res["ha_quemadas_por_cobertura"]
fig, ax = plt.subplots(figsize=(7, 3.5))
ax.barh(list(q), list(q.values()), color="#d7301f")
ax.set_xlabel("Hectáreas con dNBR ≥ 0,27"); ax.set_title("¿Qué se quemó? (ESA WorldCover 2021)")
fig.tight_layout(); fig.savefig("salidas/quemado_por_cobertura.png", dpi=130)
