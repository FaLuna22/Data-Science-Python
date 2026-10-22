"""Paso 3 (control): ¿cuánto del 'quemado' está pegado a nieve/agua enmascarada?
Los bordes de nieve que se derrite también bajan el NBR y fingen un incendio."""
import json, numpy as np, rasterio
from scipy.ndimage import binary_dilation
with rasterio.open("salidas/dnbr_chichas.tif") as s:
    d = s.read(1)
validos = np.isfinite(d)
# píxeles enmascarados dentro de la caja (nieve, agua, sombra); el exterior del distrito es 0 en SCL,
# así que aquí usamos solo los huecos internos: NaN rodeados de datos
hueco = ~validos & binary_dilation(validos, iterations=3)
cerca = binary_dilation(hueco, iterations=3)           # 3 píxeles = 60 m
q = validos & (d >= 0.27)
res = json.load(open("salidas/resultados.json"))
res["control_nieve"] = {"ha_quemadas_total": round(float(q.sum() * 0.04), 1),
                        "ha_a_menos_de_60m_de_mascara": round(float((q & cerca).sum() * 0.04), 1),
                        "ha_quemadas_robustas": round(float((q & ~cerca).sum() * 0.04), 1),
                        "ha_robustas_dnbr_044": round(float((validos & (d >= 0.44) & ~cerca).sum() * 0.04), 1)}
print(res["control_nieve"])
json.dump(res, open("salidas/resultados.json", "w"), indent=1, ensure_ascii=False)
