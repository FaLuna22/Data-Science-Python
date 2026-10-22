"""Paso 4: todo lo que necesita el dashboard.

- NBR de las 30 escenas de set-oct 2026 (para la línea de tiempo y la fecha de quemado)
- Fecha de quemado por píxel: primera escena en que el NBR cae ≥ 0,2 frente a la línea base
- Parches quemados (componentes conectados) con área, severidad, cobertura y altitud
- Sensibilidad: hectáreas según umbral y según el par de fechas elegido
- Capas en EPSG:4326 para el mapa: color real antes/después, dNBR, severidad, WorldCover, relieve
Escribe salidas/dashboard_data.json
"""
import base64, io, json
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import rasterio, geopandas as gpd
from rasterio.mask import mask
from rasterio.vrt import WarpedVRT
from rasterio.warp import reproject, Resampling, transform_geom
from rasterio.features import shapes
from rasterio.transform import from_bounds, xy
from scipy.ndimage import binary_dilation, label
from shapely.geometry import shape, mapping
from pyproj import Transformer
from PIL import Image

BUCKET = "https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/18/L/YH/2026"
WC = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_S18W075_Map.tif"
DEM = ["https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_S16_00_W0{0}_00_DEM/"
       "Copernicus_DSM_COG_10_S16_00_W0{0}_00_DEM.tif".format(x) for x in (73, 74)]
PRE, POST = "S2C_18LYH_20260915_0_L2A", "S2A_18LYH_20261017_0_L2A"
HA = 0.04
MALAS = [0, 1, 3, 6, 8, 9, 10, 11]

dist = gpd.read_file("chichas.geojson")
escenas = json.load(open("salidas/escenas_nubes.json"))


def ruta(esc):
    return f"{BUCKET}/{int(esc.split('_')[2][4:6])}/{esc}"


def leer(esc, banda):
    with rasterio.open(f"{ruta(esc)}/{banda}.tif") as src:
        arr, tr = mask(src, dist.to_crs(src.crs).geometry, crop=True, nodata=0, filled=True)
        return arr[0], tr, src.crs


def nbr_escena(esc):
    b8a, tr, crs = leer(esc, "B8A")
    b12, _, _ = leer(esc, "B12")
    scl, _, _ = leer(esc, "SCL")
    b8a, b12 = b8a.astype("float32"), b12.astype("float32")
    v = (b8a - b12) / (b8a + b12 + 1e-6)
    v[np.isin(scl, MALAS)] = np.nan
    return esc, v, tr, crs


# 1. NBR de todas las escenas -----------------------------------------------------------
with ThreadPoolExecutor(8) as ex:
    res = list(ex.map(nbr_escena, [e["escena"] for e in escenas]))
nbr = {e: v for e, v, _, _ in res}
_, _, TR, CRS = res[0]
forma = nbr[PRE].shape
assert all(v.shape == forma for v in nbr.values())
fechas = [e["escena"] for e in escenas]
print("NBR listo:", len(nbr), "escenas", forma)

# 2. dNBR principal, robusto y parches ---------------------------------------------------
dnbr = nbr[PRE] - nbr[POST]
validos = np.isfinite(dnbr)
hueco = ~validos & binary_dilation(validos, iterations=3)
cerca = binary_dilation(hueco, iterations=3)
quemado = validos & (dnbr >= 0.27)
robusto = quemado & ~cerca

wc = np.zeros(forma, "uint8")
with rasterio.open(WC) as src:
    reproject(rasterio.band(src, 1), wc, dst_transform=TR, dst_crs=CRS, resampling=Resampling.mode)
dem = np.full(forma, np.nan, "float32")
for u in DEM:
    tmp = np.full(forma, np.nan, "float32")
    with rasterio.open(u) as src:
        reproject(rasterio.band(src, 1), tmp, dst_transform=TR, dst_crs=CRS,
                  resampling=Resampling.bilinear, dst_nodata=np.nan)
    dem = np.where(np.isfinite(tmp), tmp, dem)
print("WorldCover y DEM listos")

CLASES = {10: "Bosque", 20: "Matorral", 30: "Pastizal", 40: "Cultivo", 50: "Urbano",
          60: "Suelo desnudo / escasa veg.", 70: "Nieve", 80: "Agua", 90: "Humedal", 100: "Musgo/liquen"}
COLOR_WC = {10: "#006400", 20: "#ffbb22", 30: "#ffff4c", 40: "#f096ff", 50: "#fa0000",
            60: "#b4b4b4", 70: "#f0f0f0", 80: "#0064c8", 90: "#0096a0", 100: "#fae6a0"}

# 3. Fecha de quemado por píxel -----------------------------------------------------------
# línea base = mediana de NBR de las escenas limpias del 1 al 15 de setiembre
base_esc = [e["escena"] for e in escenas if e["fecha"] <= "20260915" and e["nubes_pct"] < 5]
base = np.nanmedian(np.stack([nbr[e] for e in base_esc]), axis=0)
caida = np.full(forma, -1, "int16")
for i, e in enumerate(fechas):
    if e in base_esc:
        continue
    cae = (base - nbr[e]) >= 0.2
    nuevo = robusto & cae & (caida < 0)
    caida[nuevo] = i
fecha_pix = caida

# 4. Parches ------------------------------------------------------------------------------
lab, n = label(robusto, structure=np.ones((3, 3)))
a_4326 = Transformer.from_crs(CRS, 4326, always_xy=True)
parches = []
for k in range(1, n + 1):
    m = lab == k
    npx = int(m.sum())
    if npx < 25:                       # < 1 ha: ruido
        continue
    d = dnbr[m]
    cov = {CLASES.get(int(c), str(c)): round(float((wc[m] == c).sum() * HA), 2) for c in np.unique(wc[m])}
    rr, cc = np.nonzero(m)
    x, y = xy(TR, rr, cc)
    lon, lat = a_4326.transform(np.mean(x), np.mean(y))
    f_ok = fecha_pix[m]
    f_ok = f_ok[f_ok >= 0]
    primera = fechas[int(np.bincount(f_ok).argmax())].split("_")[2] if len(f_ok) else None
    geoms = [shape(g) for g, v in shapes(m.astype("uint8"), mask=m, transform=TR) if v == 1]
    from shapely.ops import unary_union
    poly = unary_union(geoms).simplify(15)
    parches.append(dict(
        ha=round(npx * HA, 1),
        ha_sev={"Moderada-baja": round(float(((d >= .27) & (d < .44)).sum() * HA), 1),
                "Moderada-alta": round(float(((d >= .44) & (d < .66)).sum() * HA), 1),
                "Alta": round(float((d >= .66).sum() * HA), 1)},
        dnbr_medio=round(float(d.mean()), 3), dnbr_max=round(float(d.max()), 3),
        cobertura=dict(sorted(cov.items(), key=lambda t: -t[1])),
        alt_media=round(float(np.nanmean(dem[m]))), alt_min=round(float(np.nanmin(dem[m]))),
        alt_max=round(float(np.nanmax(dem[m]))),
        lon=round(lon, 5), lat=round(lat, 5), fecha_caida=primera,
        geom=transform_geom(CRS, "EPSG:4326", mapping(poly), precision=5)))
parches.sort(key=lambda p: -p["ha"])
for i, p in enumerate(parches, 1):
    p["id"] = i
print("parches >= 1 ha:", len(parches), "suman", round(sum(p["ha"] for p in parches), 1), "ha")

# 5. Línea de tiempo ----------------------------------------------------------------------
grande = np.zeros(forma, bool)
for k in range(1, n + 1):
    if (lab == k).sum() * HA == parches[0]["ha"]:
        grande = lab == k
        break
anillo = binary_dilation(grande, iterations=25) & ~binary_dilation(grande, iterations=8) & validos & ~quemado
serie = []
for e in escenas:
    v = nbr[e["escena"]]
    ok = np.isfinite(v[grande])
    serie.append(dict(fecha=e["fecha"], escena=e["escena"],
                      nubes_distrito=e["nubes_pct"],
                      nubes_parche=round(float(100 * (1 - ok.mean())), 1),
                      nbr_parche=round(float(np.nanmean(v[grande])), 4) if ok.any() else None,
                      nbr_control=round(float(np.nanmean(v[anillo])), 4) if np.isfinite(v[anillo]).any() else None))
acum = []
for i, e in enumerate(fechas):
    acum.append(dict(fecha=e.split("_")[2], ha_nuevas=round(float((fecha_pix == i).sum() * HA), 1),
                     ha_acum=round(float(((fecha_pix >= 0) & (fecha_pix <= i)).sum() * HA), 1)))

# 6. Sensibilidad -------------------------------------------------------------------------
umbrales = [round(u, 2) for u in np.arange(0.05, 0.71, 0.01)]
sens_umbral = [dict(u=u, total=round(float((validos & (dnbr >= u)).sum() * HA), 1),
                    robusto=round(float((validos & (dnbr >= u) & ~cerca).sum() * HA), 1)) for u in umbrales]
pres = [e["escena"] for e in escenas if e["fecha"] <= "20261005" and e["nubes_pct"] < 1][-6:]
posts = [e["escena"] for e in escenas if e["fecha"] >= "20261010" and e["nubes_pct"] < 1]
pares = []
for a in pres:
    for b in posts:
        d = nbr[a] - nbr[b]
        ok = np.isfinite(d)
        pares.append(dict(pre=a.split("_")[2], post=b.split("_")[2],
                          ha=round(float((ok & (d >= 0.27)).sum() * HA), 1),
                          ha_robusto=round(float((ok & (d >= 0.27) & ~cerca).sum() * HA), 1)))

# 7. Altitud ------------------------------------------------------------------------------
bins = np.arange(np.floor(np.nanmin(dem[validos]) / 100) * 100, np.nanmax(dem[validos]) + 100, 100)
h_dist, _ = np.histogram(dem[validos & np.isfinite(dem)], bins)
h_q, _ = np.histogram(dem[robusto & np.isfinite(dem)], bins)
altitud = dict(bins=[int(b) for b in bins[:-1]], distrito_ha=[round(float(x * HA), 1) for x in h_dist],
               quemado_ha=[round(float(x * HA), 2) for x in h_q])

# 8. Capas del mapa en EPSG:4326 ----------------------------------------------------------
W, S, E, N = dist.total_bounds
pad = 0.01
W, S, E, N = W - pad, S - pad, E + pad, N + pad
RES = 0.0002                           # ≈ 21 m
ancho, alto = int((E - W) / RES), int((N - S) / RES)
T4 = from_bounds(W, S, E, N, ancho, alto)


def a4326(arr, resamp=Resampling.nearest, nodata=np.nan):
    out = np.full((alto, ancho), nodata, arr.dtype)
    reproject(arr, out, src_transform=TR, src_crs=CRS, dst_transform=T4, dst_crs="EPSG:4326",
              resampling=resamp, src_nodata=nodata, dst_nodata=nodata)
    return out


def png(rgba, fmt="PNG", q=85):
    b = io.BytesIO()
    img = Image.fromarray(rgba)
    if fmt == "JPEG":
        img = img.convert("RGB")
    img.save(b, fmt, optimize=True, **({"quality": q} if fmt == "JPEG" else {}))
    return f"data:image/{fmt.lower()};base64," + base64.b64encode(b.getvalue()).decode()


def hex2rgb(h):
    return [int(h[i:i + 2], 16) for i in (1, 3, 5)]


def tci(esc):
    with rasterio.open(f"{ruta(esc)}/TCI.tif") as src:
        with WarpedVRT(src, crs="EPSG:4326", transform=T4, width=ancho, height=alto,
                       resampling=Resampling.average) as vrt:
            a = vrt.read()
    rgba = np.dstack([a[0], a[1], a[2], np.where(a.sum(0) > 0, 255, 0).astype("uint8")])
    return png(rgba, "JPEG", 80)


capas = {"antes": tci(PRE), "despues": tci(POST)}
print("color real listo")

d4 = a4326(dnbr.astype("float32"))
import matplotlib
cmap = matplotlib.colormaps["RdYlGn_r"]
norm = np.clip((d4 + 0.3) / 1.0, 0, 1)
rgba = (cmap(norm) * 255).astype("uint8")
rgba[..., 3] = np.where(np.isfinite(d4), 230, 0)
capas["dnbr"] = png(rgba)

SEV_COL = ["#fee08b", "#fdae61", "#f46d43", "#a50026"]
sev = np.zeros(forma, "uint8")
for i, (a, b) in enumerate(zip([.10, .27, .44, .66], [.27, .44, .66, 9]), 1):
    sev[validos & (dnbr >= a) & (dnbr < b)] = i
s4 = a4326(sev, nodata=0)
rgba = np.zeros((alto, ancho, 4), "uint8")
for i, c in enumerate(SEV_COL, 1):
    rgba[s4 == i] = hex2rgb(c) + [255 if i >= 2 else 150]
capas["severidad"] = png(rgba)

w4 = a4326(wc, nodata=0)
rgba = np.zeros((alto, ancho, 4), "uint8")
for c, col in COLOR_WC.items():
    rgba[w4 == c] = hex2rgb(col) + [200]
capas["worldcover"] = png(rgba)

f4 = a4326(np.where(fecha_pix >= 0, fecha_pix + 1, 0).astype("uint8"), nodata=0)
cm2 = matplotlib.colormaps["plasma"]
rgba = np.zeros((alto, ancho, 4), "uint8")
vals = sorted(set(np.unique(f4)) - {0})
for v in vals:
    rgba[f4 == v] = (np.array(cm2((v - 1) / max(len(fechas) - 1, 1))) * 255).astype("uint8")
capas["fecha"] = png(rgba)

dem4 = a4326(dem, Resampling.bilinear)
gy, gx = np.gradient(np.nan_to_num(dem4, nan=np.nanmean(dem4)), 21, 21)
slope = np.arctan(np.hypot(gx, gy))
aspect = np.arctan2(-gx, gy)
az, alt_sol = np.radians(315), np.radians(45)
hs = np.sin(alt_sol) * np.cos(slope) + np.cos(alt_sol) * np.sin(slope) * np.cos(az - aspect)
hs = (np.clip(hs, 0, 1) * 255).astype("uint8")
capas["relieve"] = png(np.dstack([hs, hs, hs, np.full_like(hs, 255)]), "JPEG", 75)
print("capas listas")

# Recortes de color real del parche grande, escena por escena
p0 = parches[0]
g = shape(p0["geom"]).bounds
cx, cy = (g[0] + g[2]) / 2, (g[1] + g[3]) / 2
lado = max(g[2] - g[0], g[3] - g[1]) * 0.75 + 0.005
CB = (cx - lado, cy - lado, cx + lado, cy + lado)
CT = from_bounds(*CB, 220, 220)


def recorte(e):
    with rasterio.open(f"{ruta(e['escena'])}/TCI.tif") as src:
        with WarpedVRT(src, crs="EPSG:4326", transform=CT, width=220, height=220,
                       resampling=Resampling.bilinear) as vrt:
            a = vrt.read()
    return png(np.dstack([a[0], a[1], a[2], np.full(a.shape[1:], 255, "uint8")]), "JPEG", 72)


with ThreadPoolExecutor(8) as ex:
    recortes = list(ex.map(recorte, escenas))
for s, r in zip(serie, recortes):
    s["img"] = r
print("recortes listos")

# Límite del distrito
limite = json.loads(dist.to_json())["features"][0]["geometry"]
resumen = json.load(open("salidas/resultados.json"))

out = dict(
    corte="2026-10-21", pre=PRE, post=POST, bounds=[[S, W], [N, E]], recorte_bounds=[[CB[1], CB[0]], [CB[3], CB[2]]],
    capas=capas, limite=limite, parches=parches, serie=serie, acumulado=acum,
    base_escenas=[e.split("_")[2] for e in base_esc],
    sens_umbral=sens_umbral, pares=pares, altitud=altitud, resumen=resumen,
    alt_quemado=dict(media=round(float(np.nanmean(dem[robusto]))), min=round(float(np.nanmin(dem[robusto]))),
                     max=round(float(np.nanmax(dem[robusto])))),
    alt_distrito=dict(min=round(float(np.nanmin(dem[validos]))), max=round(float(np.nanmax(dem[validos])))),
    sev_x_cob={CLASES.get(int(c), str(c)): {n: round(float(((wc == c) & (sev == i)).sum() * HA), 1)
                                            for i, n in enumerate(["Baja", "Moderada-baja", "Moderada-alta", "Alta"], 1)}
               for c in np.unique(wc[validos]) if c},
    clases_wc={CLASES[c]: COLOR_WC[c] for c in CLASES},
    fechas=[e.split("_")[2] for e in fechas],
)
json.dump(out, open("salidas/dashboard_data.json", "w"), ensure_ascii=False)
print("listo:", round(len(json.dumps(out)) / 1e6, 2), "MB")
