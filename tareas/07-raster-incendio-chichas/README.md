# ¿Cuánto se quemó en Chichas (Condesuyos, Arequipa) en la temporada 2026?

Tarea de la sesión 07 · Raster — **Reto A (otro incendio)** con cruce del **Reto C (¿qué se quemó?)**,
validada con focos de calor de **NASA FIRMS** y con MODIS y Landsat de **Microsoft Planetary Computer**.

![Mapa dNBR y severidad](salidas/mapa_dnbr_chichas.png)

## La pregunta

Chichas aparece entre los incendios activos de octubre de 2026. ¿Cuántas hectáreas se
quemaron dentro del distrito entre mediados de setiembre y mediados de octubre, con qué
severidad y sobre qué cobertura (bosque, matorral, pastizal o cultivo)? ¿Cuándo empezó y
terminó el fuego, y es normal que arda así?

## Datos y fechas

| Dato | Fuente | Fecha | Nubes en el distrito |
|---|---|---|---|
| Imagen **antes** | Sentinel-2 L2A `S2C_18LYH_20260915_0_L2A` (bucket público `sentinel-cogs` en AWS) | 15 set 2026 | **0,01 %** |
| Imagen **después** | Sentinel-2 L2A `S2A_18LYH_20261017_0_L2A` | 17 oct 2026 | **0,02 %** |
| Cobertura del suelo | ESA WorldCover 2021 v200, 10 m (tile `S18W075`) | 2021 | — |
| Límite distrital | INEI, `peru_distrital_simple.geojson` (sesión 06), UBIGEO 040604 | — | — |
| Focos de calor NRT | **NASA FIRMS**: VIIRS S-NPP, NOAA-20, NOAA-21 (375 m) y MODIS (1 km), archivos públicos de 7 días | 14–21 oct 2026 | — |
| Focos históricos | **NASA FIRMS**, archivo anual de Perú: MODIS 2001–2025, VIIRS S-NPP 2012–2025 | 2001–2025 | — |
| Fuego diario | **Planetary Computer**, MOD14A1/MYD14A1 v061 (FireMask, 1 km) | 1 set – 15 oct 2026 | mediana 0,6 %; 6 días nublados, todos en setiembre |
| Área quemada mensual | **Planetary Computer**, MCD64A1 v061 (500 m) | nov 2000 – ago 2026 | — |
| Segundo sensor | **Planetary Computer**, Landsat 8/9 C2 L2 (30 m), ruta 004, filas 070–071 | 2 ago – 5 oct 2026 | 3–63 % |

El % de nubes de **las 30 escenas** Sentinel-2 de setiembre y octubre está en
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
4. **`04_datos_dashboard.py`** y **`05_persistencia.py`** — NBR de las 30 escenas, parches,
   sensibilidad, capas del mapa y dNBR corregido por offset con las imágenes del 17, 18 y 20 oct.
5. **`07_firms.py`** — focos FIRMS NRT (se acumulan en `salidas/firms_nrt.csv`, porque la ventana
   de 7 días se mueve; con la variable `FIRMS_MAP_KEY` baja todo set–oct por la API) e históricos.
   Un foco "coincide" con el quemado si su huella (medio píxel: 187 m VIIRS, 500 m MODIS) toca
   quemado robusto del 17, 18 o 20 oct. **Área confirmada** = unión del quemado robusto de las
   tres fechas, solo en los parches que tienen un foco a ≤ 375 m (VIIRS) o ≤ 1 km (MODIS).
6. **`08_planetary.py`** — consulta el STAC de Planetary Computer (sin clave; cada COG se firma con
   el token SAS de su contenedor): píxeles de fuego MODIS por día, área quemada MCD64A1 por año y
   por píxel, y NBR Landsat del parche 1 con su anillo de control.

Reproducir (con el entorno del curso: `uv sync --group raster --group geo`):

```bash
cd tareas/07-raster-incendio-chichas
uv run python 01_escenas.py && uv run python 02_dnbr.py && uv run python 03_control_nieve.py
uv run python 04_datos_dashboard.py && uv run python 05_persistencia.py  # requiere pillow y scipy
uv run python 07_firms.py && uv run python 08_planetary.py && uv run python 06_dashboard.py
```

No hace falta clave: todo se lee por HTTP desde COGs públicos (AWS y Planetary Computer), solo la
ventana del distrito, y FIRMS publica sus últimos 7 días sin clave. Opcional:
`FIRMS_MAP_KEY=... uv run python 07_firms.py` para bajar todos los focos desde el 1 de setiembre.

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

### Validación con FIRMS y Planetary Computer

| Indicador | Valor |
|---|---:|
| Focos FIRMS dentro del distrito (157 VIIRS + 9 MODIS) | **166** |
| Primer / último foco (hora de Perú) | 16 oct 14:08 / 18 oct 14:13 |
| Focos antes / después de la imagen Sentinel-2 del 17 oct (10:07) | 50 / 116 |
| Focos que caen sobre quemado robusto (17, 18 o 20 oct) | 149 (90 %) |
| Parches ≥ 1 ha con algún foco | 10 de 17 (44,5 de 57,9 ha) |
| Quemado robusto, unión 17 + 18 + 20 oct (dNBR corregido) | 445,3 ha |
| … en parches que tocan un foco (**mejor estimación**) | **≈ 400 ha** |
| Píxeles de fuego MODIS 14A1 en el distrito, 1 set – 15 oct | 0 |
| dNBR Landsat 19 set → 5 oct dentro de los parches | 0,003 (sin cicatriz) |
| Focos VIIRS S-NPP: oct 2026 (3 días) frente al peor año completo (2013) | 58 frente a 44 |
| Años con área quemada MCD64A1 en el distrito (2001 – ago 2026) | 2002 (1 460 ha) y 2013 (451 ha) |

## Dashboard

[`dashboard.html`](dashboard.html) es un archivo autocontenido (5 MB, funciona sin internet:
Leaflet y Chart.js van incrustados). Descárgalo y ábrelo en el navegador. Incluye:

- **Mapa** con capas (color real antes/después, relieve, dNBR, severidad, fecha de caída del NBR,
  WorldCover, años quemados MCD64A1, parches y **focos FIRMS** con su huella y ficha).
- **Focos de calor**: focos cada 3 horas frente a los pasos de Sentinel-2, coincidencia
  foco–quemado por fecha, y fuego diario del 1 set al 21 oct (MODIS 14A1 + FIRMS).
- Tabla de 17 **parches** ordenable y enlazada al mapa, con focos y quemas previas.
- **Línea de tiempo** de las 30 escenas con reproducción, y la serie **Landsat 8/9**.
- Sensibilidad al umbral y al par de fechas, cruce severidad × cobertura y altitud.
- **Historia 2001–2026**: focos por año y por mes, y hectáreas MCD64A1.

Se regenera con `04` → `05` → `07` → `08` → `06`.

## 4 hallazgos

1. **El fuego duró unas 48 horas y la imagen del 17 oct lo captó a la mitad.** MODIS 14A1 no ve
   ningún píxel de fuego del 1 set al 15 oct (con cielo despejado todo octubre), y Landsat no ve cicatriz el
   5 oct. El primer foco VIIRS dentro del distrito es del **16 oct a las 14:08** y el último del
   **18 oct a las 14:13** (hora de Perú); del 19 al 21 oct no hay ninguno. De los 166 focos, 50 son
   anteriores a la imagen Sentinel-2 del 17 oct (10:07) y 116 posteriores, y 106 de estos caen
   sobre quemado que recién aparece el 18 o el 20 oct. Por eso el par 15 set → 17 oct (117 ha) se
   queda corto y la huella "se mueve": no era ruido, era el fuego avanzando. La unión del quemado
   robusto de las tres fechas, en parches tocados por focos, da **≈ 400 ha** (el 20 oct tiene
   16–18 % de nubes; el número final se cierra con la próxima imagen limpia).
2. **Lo que arde es vegetación altoandina, no bosque**: en el par principal, pastizal 37 ha
   y matorral 25 ha (53 % del quemado). Bosque y cultivo suman menos de 2 ha. Los 10 parches
   con focos están entre 3 288 y 4 290 m.
3. **Los focos separan fuego de artefactos.** El 90 % de los focos cae sobre quemado robusto, y
   10 de los 17 parches tienen focos. Los 7 sin ningún foco (13,4 ha) están **todos sobre
   5 170 m**, en "suelo desnudo" junto al nevado: casi seguro deshielo o sombra de nieve, aunque
   pasen el control de 60 m. Esto completa el control de nieve (37 de 117 ha dudosas el 17 oct).
4. **Es un incendio fuera de lo normal para Chichas.** De 2001 a 2025 hubo 279 focos en el
   distrito, el 63 % entre setiembre y noviembre. Con el mismo satélite, VIIRS S-NPP detectó
   **58 focos en 3 días** de octubre de 2026, más que en todo 2013 (44), su peor año. MCD64A1 solo
   marca quemas grandes en 2002 (1 460 ha) y 2013 (451 ha); el lugar del parche 1 ya se quemó en 2002.

## Limitaciones

- **Un foco no es un área**: un píxel VIIRS mide 375 m y uno MODIS 1 km; el foco solo dice que
  algo ardía allí durante el paso del satélite. Nubes y humo espeso esconden focos.
- **Ventana FIRMS**: sin clave, FIRMS publica solo los últimos 7 días (aquí 14–21 oct). Antes de
  esa ventana se usó MODIS 14A1 (Planetary Computer), menos sensible a fuegos pequeños. Con
  `FIRMS_MAP_KEY` el script baja toda la temporada.
- **MCD64A1 llega con ~2 meses de retraso** (último mes: agosto 2026) y a 500 m no ve fuegos chicos.
- **Landsat**: la última escena publicada en Planetary Computer es del 5 oct, anterior al fuego;
  `08_planetary.py` toma sola la más reciente, así que al volver a correrlo medirá el área con un
  segundo sensor.
- **El límite distrital está simplificado**: hay 90 focos más a ≤ 15 km, fuera del polígono, que
  aquí no se cuentan.
- **Las fechas importan**: el dNBR con una imagen tomada durante el fuego mide llamas y humo, no
  la cicatriz final; la ceniza que el viento se lleva y el rebrote del pajonal también cambian el NBR.
- **El umbral 0,27 es genérico** (calibrado en bosques de EE. UU.); en puna con poca
  biomasa los incendios reales dan dNBR bajos, así que parte de las 740 ha "baja" podría
  ser fuego leve, o sequía estacional.
- WorldCover es de 2021 y se remuestreó de 10 a 20 m.
