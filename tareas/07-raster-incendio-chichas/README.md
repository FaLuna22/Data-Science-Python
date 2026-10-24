# ¿Cuánto se quemó en Chichas (Condesuyos, Arequipa) en la temporada 2026?

Tarea de la sesión 07 · Raster — **Reto A (otro incendio)** con cruce del **Reto C (¿qué se quemó?)**.

![Mapa dNBR y severidad](salidas/mapa_dnbr_chichas.png)

## La pregunta

Chichas aparece entre los incendios activos de octubre de 2026. ¿Cuántas hectáreas se
quemaron dentro del distrito entre mediados de setiembre y mediados de octubre, con qué
severidad y sobre qué cobertura (bosque, matorral, pastizal o cultivo)?

## Datos y fechas

| Dato | Fuente | Fecha | Nubes en el distrito |
|---|---|---|---|
| Imagen **antes** | Sentinel-2 L2A `S2C_18LYH_20260915_0_L2A` (bucket público `sentinel-cogs` en AWS) | 15 set 2026 | **0,01 %** |
| Imagen **después** | Sentinel-2 L2A `S2A_18LYH_20261017_0_L2A` | 17 oct 2026 | **0,02 %** |
| Imagen **después (referencia)** | Sentinel-2 L2A `S2A_18LYH_20261020_1_L2A` | 20 oct 2026 | 16 % (0 % sobre la zona de focos) |
| Focos de calor | NASA FIRMS, VIIRS 375 m (S-NPP, NOAA-20, NOAA-21), CSV público de 7 días | 17–24 oct 2026 | — |
| Cobertura del suelo | ESA WorldCover 2021 v200, 10 m (tile `S18W075`) | 2021 | — |
| Límite distrital | INEI, `peru_distrital_simple.geojson` (sesión 06), UBIGEO 040604 | — | — |
| Relieve | Copernicus DEM GLO-30 (bucket público en AWS) | — | — |

El % de nubes de **las 30 escenas** de setiembre y octubre está en
[`salidas/escenas_nubes.json`](salidas/escenas_nubes.json). Se calculó con la capa SCL
**solo dentro del distrito** (clases 3, 8, 9 y 10), no con el % de nubes de toda la escena.

## Método

1. **`01_escenas.py`** — lista las escenas del tile 18LYH y mide nubes dentro de Chichas.
   Elegí el par antes/después más cercano a la temporada con nubes ≈ 0 % y cobertura completa.
2. **`02_dnbr.py`** — NBR = (B8A − B12) / (B8A + B12) a 20 m; dNBR = NBR antes − NBR después.
   Enmascaro en cualquiera de las dos fechas: sin dato, saturado, sombra, **agua**, nubes y
   **nieve** (SCL). Clasifico con los umbrales USGS (Key & Benson): 0,10 / 0,27 / 0,44 / 0,66.
   **Quemado = dNBR ≥ 0,27**. 1 píxel = 0,04 ha. Cruzo con WorldCover remuestreado por moda.
3. **`03_control_nieve.py`** — control de calidad: los bordes de nieve y de lagunas que
   cambian entre fechas también bajan el NBR. Separo el "quemado" que está a ≤ 60 m de un
   píxel enmascarado.

Reproducir (con el entorno del curso: `uv sync --group raster --group geo`):

```bash
cd tareas/07-raster-incendio-chichas
uv run python 01_escenas.py && uv run python 02_dnbr.py && uv run python 03_control_nieve.py
uv run python 04_datos_dashboard.py && uv run python 05_persistencia.py && uv run python 07_firms.py && uv run python 06_dashboard.py  # requiere pillow y scipy
```

No hace falta clave: todo se lee por HTTP desde COGs públicos, solo la ventana del distrito.

## Resultados

| Severidad (dNBR) | Hectáreas |
|---|---:|
| Baja (0,10–0,27) | 740,6 |
| Moderada-baja (0,27–0,44) | 54,8 |
| Moderada-alta (0,44–0,66) | 39,9 |
| Alta (≥ 0,66) | 22,6 |
| **Quemado (≥ 0,27)** | **117,3** |
| … de eso, a ≤ 60 m de nieve/agua (sospechoso) | 37,0 |
| **Quemado robusto** (≥ 0,27 y lejos de máscaras) | **80,4** |

![Quemado por cobertura](salidas/quemado_por_cobertura.png)

## Dashboard

[`dashboard.html`](dashboard.html) es un archivo autocontenido (5 MB, funciona sin internet:
Leaflet y Chart.js van incrustados). Descárgalo y ábrelo en el navegador. Incluye mapa con
capas (color real antes/después, relieve, dNBR, severidad, fecha de caída del NBR,
WorldCover, focos VIIRS, zona de focos y parches), focos por pasada de satélite, área
quemada por fecha dentro y fuera de la zona de focos, línea de tiempo de las 31 escenas con
reproducción, sensibilidad al umbral y al par de fechas, cruce severidad × cobertura,
altitud, tabla de parches enlazada al mapa y tabla de escenas. Se regenera con
`04_datos_dashboard.py` → `05_persistencia.py` → `07_firms.py` → `06_dashboard.py`.

## Validación con focos VIIRS (NASA FIRMS)

`07_firms.py` baja los CSV públicos de 7 días de S-NPP, NOAA-20 y NOAA-21 (17 al 24 oct).
Hay **172 focos en Chichas, todos entre el 17 oct 00:21 y el 18 oct 14:13** (hora de Lima),
en el noroeste del distrito, justo sobre los parches que marca el dNBR. Después no hay más.
Con ellos armé una **zona de focos** (buffer de 750 m, 2 454 ha) y medí el dNBR ≥ 0,27 dentro
y fuera de ella frente al 15 de setiembre:

| Imagen después | Zona visible | Dentro (ha) | Fuera (ha) |
|---|---:|---:|---:|
| 17 oct · S2A (fuego activo) | 99 % | 56 | 61 |
| 18 oct · S2C (fuego activo) | 100 % | 81 | 68 |
| **20 oct · S2A (ya sin focos)** | **100 %** | **258** | **11** |
| 20 oct · S2B | 75 % | 124 | 203 |
| 23 oct · S2B | 56 % | 2 | 24 |

## 3 hallazgos

1. **Se quemaron entre ~80 y ~260 ha de puna en el noroeste de Chichas el 17 y 18 de
   octubre.** La primera imagen limpia después del último foco (20 oct, S2A) da 258 ha con
   dNBR ≥ 0,27 dentro de la zona de focos y solo 11 ha fuera. La otra imagen del mismo día
   (S2B) confirma 82 de 147 ha comparables, así que el piso es ~80 ha. Casi todo es
   severidad moderada-baja (3 ha ≥ 0,44): poca biomasa, típico de pajonal.
2. **La imagen del 17 oct no sirve para medir el área: captó el fuego encendido.** Sentinel-2
   pasó a las 10:20 h, entre las pasadas VIIRS de la madrugada y del mediodía. El NBR del
   parche 1 cae de −0,10 a −0,64 y al día siguiente vuelve a parecerse a su entorno. Ese par
   da 117 ha en todo el distrito, pero solo 56 ha caen en la zona de focos; las otras 61 ha
   son ruido. Los parches sin foco están a más de 5 000 m, junto al nevado (probable
   deshielo).
3. **Lo que arde es vegetación altoandina, no bosque**: pastizal y matorral, a 4 079 m de
   altitud media. Bosque y cultivo suman menos de 2 ha. Y la cicatriz se borra rápido: el
   23 oct solo 2 de las 101 ha visibles siguen con dNBR ≥ 0,27 (en el pajonal hay poca
   biomasa, y el viento o la lluvia se llevan la ceniza).

## Limitaciones

- **FIRMS solo guarda 7 días en su CSV público** (17 al 24 oct): no se sabe si hubo focos
  antes del 17 oct. Para eso hace falta la API de FIRMS con clave (MAP_KEY).
- **Un foco de calor no es un incendio:** la zona de 750 m puede incluir algo no quemado y
  dejar fuera bordes quemados que no se detectaron.
- **Las nubes esconden el fuego:** el 20 oct (S2B) y el 23 oct tienen nubes sobre la zona;
  solo se compara lo que se ve en ambas imágenes.
- **El umbral 0,27 es genérico** (calibrado en bosques de EE. UU.); en puna con poca
  biomasa los incendios reales dan dNBR bajos.
- El límite distrital está simplificado (1 km de holgura para los focos). WorldCover es de
  2021 y se remuestreó de 10 a 20 m.
