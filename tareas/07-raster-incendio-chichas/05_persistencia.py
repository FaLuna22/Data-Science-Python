"""Paso 5 (control): ¿la cicatriz del 17-oct persiste el 18 y 20-oct?
dNBR corregido = dNBR − mediana del dNBR del distrito (quita cambios regionales de
iluminación, humedad o fenología, práctica estándar de 'offset')."""
import json, numpy as np, rasterio, geopandas as gpd
from rasterio.mask import mask
B = "https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/18/L/YH/2026"
dist = gpd.read_file("chichas.geojson")
MALAS = [0, 1, 3, 6, 8, 9, 10, 11]
def nbr(p):
    out = []
    for b in ("B8A", "B12", "SCL"):
        with rasterio.open(f"{B}/{p}/{b}.tif") as s:
            out.append(mask(s, dist.to_crs(s.crs).geometry, crop=True, nodata=0, filled=True)[0][0])
    n = (out[0].astype("f4") - out[1]) / (out[0].astype("f4") + out[1] + 1e-6)
    n[np.isin(out[2], MALAS)] = np.nan
    return n
pre = nbr("9/S2C_18LYH_20260915_0_L2A")
posts = {"20261017": "10/S2A_18LYH_20261017_0_L2A", "20261018": "10/S2C_18LYH_20261018_0_L2A",
         "20261020": "10/S2A_18LYH_20261020_1_L2A"}
res, q = {}, {}
for f, p in posts.items():
    d = pre - nbr(p)
    off = float(np.nanmedian(d))
    dc = d - off
    q[f] = np.isfinite(dc) & (dc >= 0.27)
    res[f] = dict(offset=round(off, 3), ha_sin_corregir=round(float((np.isfinite(d) & (d >= .27)).sum() * .04), 1),
                  ha_corregido=round(float(q[f].sum() * .04), 1))
res["persistente_17_18_20"] = round(float((q["20261017"] & q["20261018"] & q["20261020"]).sum() * .04), 1)
res["persistente_18_20"] = round(float((q["20261018"] & q["20261020"]).sum() * .04), 1)
print(json.dumps(res, indent=1))
r = json.load(open("salidas/resultados.json")); r["persistencia"] = res
json.dump(r, open("salidas/resultados.json", "w"), indent=1, ensure_ascii=False)
