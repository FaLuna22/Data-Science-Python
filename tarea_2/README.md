# Tarea 2 · Voces y documentos peruanos: del archivo escaneado al texto buscable

**Pregunta:** ¿podemos convertir documentos escaneados y entrevistas en audio en un archivo de texto estructurado y buscable?

**Dashboard público:** _(pendiente: enlace de Streamlit Community Cloud)_

Pipeline con modelos abiertos y locales: OCR con PaddleOCR, transcripción con faster-whisper (VAD + diarización),
seudonimización, extracción de campos con un LLM local (Qwen2.5-3B-Instruct) y evaluación contra transcripciones
hechas a mano. El dashboard solo lee los CSV que producen los notebooks.

## Contenido

| Archivo | Qué hace |
|---|---|
| `01_extraccion.ipynb` | Corpus, limpieza (hash, ilegibles, audios sin voz), OCR, ASR con VAD y diarización, seudonimización, EDA y exportación |
| `02_evaluacion.ipynb` | Muestra de 10 documentos y 10 clips con referencias manuales, CER/WER base, modelos alternativos, LLM y auditoría, casos difíciles y decisión |
| `app.py` | Dashboard de Streamlit |
| `herramientas/descargar.py` | Descarga el corpus (Commons y OpenSLR 73) y deja un catálogo con licencias |
| `herramientas/t2.py` | Orden de lectura del OCR, normalización, CER/WER, seudonimización |
| `herramientas/preparar_muestra.py` | Muestra de evaluación (recortes y clips fijos) y muestra de auditoría |
| `herramientas/anotar_referencias.py` | App local para transcribir a mano las referencias (oculta la salida de los modelos) |
| `herramientas/auditar_llm.py` | App local para auditar las 20 extracciones del LLM |
| `herramientas/extraer_llm.py` | Extracción estructurada con Qwen2.5-3B-Instruct en la GPU |
| `datos/documentos.csv` | 25 documentos: texto OCR seudonimizado y referencia manual de la muestra |
| `datos/transcripciones.csv` | Clips de audio: texto ASR seudonimizado con marcas de hablante |
| `datos/extraccion_llm.csv` | Campos JSON extraídos por el LLM |
| `datos/fuentes.csv` | Fuente, autor, licencia y forma de acceso de cada archivo |
| `datos/metricas_*.csv`, `datos/auditoria_llm.csv` | Resultados de la evaluación que usa el dashboard |
| `datos/ejemplos/recortes/` | Recortes publicables de la muestra de evaluación |
| `evidencias_ia/` | Capturas de la conversación con Claude Code |

## Corpus y fuentes (extraídos el 26/10/2026)

**Documentos (25, Wikimedia Commons):** 8 impresos nítidos (comunicados del MINSA 2020, carta de la Secretaría de la
Presidencia de 1956, boletín de la Liga de Fútbol de Lima de 1934, *El Comercio* 1842, *El Peruano* 1844, *El Montonero*
1834, *La Campana* 1873), 8 fotos con sombra, brillo o inclinación (revista *Época* 1984, diario *El Tiempo* 1973,
periódico *Acción*, resoluciones municipales de Moyobamba, exposición de Tarata, *La Industria* 1923, guía del
Bicentenario) y 9 manuscritos (Acta de la Independencia, partidas de bautismo y nacimiento, libros de bautismo de Lampa,
recibo de 1895, diplomas). Licencias: dominio público, CC0, CC BY 2.0/4.0 y CC BY-SA 3.0/4.0.

**Audio (Wikimedia Commons, CC BY-SA 4.0 y CC BY 4.0):** entrevistas de calle en El Agustino, Magdalena y la Plaza de
Armas, minientrevistas en el repechaje Perú-Australia, dirigentes de Fenmucarinap, estudiantes de la UNMSM y testimonios
del proyecto *Salas, pantallas y archivos* (WikiAcción Perú). Más 6 frases leídas de **OpenSLR 73** (Google, CC BY-SA 4.0).

El detalle por archivo (URL, autor, licencia) está en `datos/fuentes.csv`. Los originales no se versionan; se recuperan con
`herramientas/descargar.py`.

## Resultados

_(pendiente)_

## Hallazgos

_(pendiente)_

## Limitaciones técnicas

_(pendiente)_

## Ética y datos personales

- Solo archivos con licencia libre, con atribución en `datos/fuentes.csv`.
- Seudonimización: lista de personas particulares revisada a mano (no versionada) + reemplazo difuso de nombres y borrado
  de DNI, teléfonos y correos (`t2.seudonimizar`). Se conservan los nombres de figuras históricas o públicas en su rol público.
- Las imágenes que nombran a personas particulares no se muestran en el dashboard; su texto se publica seudonimizado.
- Los audios se reproducen desde su URL pública de Wikimedia Commons; no se suben audios al repositorio.

## Cómo ejecutar

Dashboard en local (solo necesita `requirements.txt`):

```bash
cd tarea_2
pip install -r requirements.txt
streamlit run app.py
```

Notebooks (Windows con GPU NVIDIA). Las librerías son las de los grupos `docai` y `audio` del curso, pero en un entorno con
PyTorch CUDA, porque el `uv.lock` del curso instala PyTorch solo para CPU y PaddlePaddle en CPU falla en Windows:

```bash
cd tarea_2
uv venv .venv-gpu --python 3.12
uv pip install --python .venv-gpu/Scripts/python.exe torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .venv-gpu/Scripts/python.exe "paddleocr==3.7.0" "paddlex==3.7.2" "opencv-contrib-python==4.10.0.84" "opencv-python==4.10.0.84" "opencv-python-headless==4.10.0.84" "transformers==5.16.1" accelerate "faster-whisper==1.2.1" "av<19" "pyannote-audio>=4.0.7" jiwer rapidfuzz soundfile scipy scikit-learn pandas plotly kaleido easyocr ipykernel nbconvert streamlit
.venv-gpu/Scripts/python.exe herramientas/descargar.py
.venv-gpu/Scripts/python.exe -m jupyter nbconvert --to notebook --execute --inplace 01_extraccion.ipynb
.venv-gpu/Scripts/streamlit run herramientas/anotar_referencias.py
.venv-gpu/Scripts/python.exe -m jupyter nbconvert --to notebook --execute --inplace 02_evaluacion.ipynb
```
