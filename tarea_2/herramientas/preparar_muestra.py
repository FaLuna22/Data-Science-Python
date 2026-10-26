"""Define la muestra de evaluación de la Parte 2 (10 documentos y 10 clips del corpus de la Parte 1).

    .venv/Scripts/python tarea_2/herramientas/preparar_muestra.py

Se fija ANTES de calcular cualquier métrica y no se cambia después. Escribe:
- datos/raw/recortes/{id}.png: el recorte de cada documento que se transcribe a mano y que leen todos los OCR.
  Los documentos largos (periódicos) se evalúan en un recorte de 6 a 15 líneas: transcribir a mano una página
  entera de 1844 no es viable, y todos los modelos leen exactamente el mismo recorte.
- datos/ejemplos/recortes/{id}.png: copia de los recortes publicables (sin datos personales) para el dashboard.
- datos/muestra_evaluacion.csv: la lista que usa herramientas/anotar_referencias.py.
"""
from pathlib import Path
import shutil

import pandas as pd
from PIL import Image

RAIZ = Path(__file__).resolve().parents[1]
DATOS = RAIZ / "datos"

# id: recorte (x0, y0, x1, y1) como fracción del ancho y alto de la imagen
MUESTRA_DOCS = {
    "doc_02": (0.10, 0.27, 0.92, 0.60),   # impreso: comunicado MINSA N° 21
    "doc_04": (0.00, 0.03, 1.00, 0.36),   # impreso: boletín de la Liga de Fútbol (1934)
    "doc_06": (0.00, 0.28, 0.34, 0.45),   # impreso: El Peruano (1844), primera columna
    "doc_09": (0.02, 0.74, 0.98, 0.99),   # foto: aviso en revista Época (1984), luz tenue
    "doc_12": (0.10, 0.19, 0.82, 0.36),   # foto: resolución municipal, hoja inclinada
    "doc_15": (0.00, 0.00, 1.00, 0.26),   # foto: La Industria (1923), página curvada
    "doc_17": (0.00, 0.00, 1.00, 0.17),   # manuscrito: Acta de la Independencia (1821)
    "doc_20": (0.03, 0.50, 0.97, 0.80),   # manuscrito: diploma de la Medalla del Centenario (1921)
    "doc_21": (0.00, 0.00, 1.00, 1.00),   # manuscrito: partida de nacimiento
    "doc_24": (0.00, 0.27, 1.00, 0.75),   # manuscrito: recibo de la Peruvian Telephone Company (1895)
}

# (audio de origen, parte): condición de grabación
MUESTRA_AUDIO = {
    ("medio_tiempo", 1): "calle con multitud y bocinas",
    ("agustino_2", 1): "calle, entrevista multihablante",
    ("magdalena_2", 1): "feria al aire libre",
    ("que_es_peru", 1): "plaza, entrevista breve",
    ("fenmucarinap_2", 2): "conferencia de prensa con eco",
    ("salas_5", 1): "testimonio en interior",
}
N_OPENSLR = 4  # frases leídas de OpenSLR 73 (estudio): 2 mujeres y 2 hombres


def preparar() -> pd.DataFrame:
    documentos = pd.read_csv(DATOS / "documentos.csv")
    transcripciones = pd.read_csv(DATOS / "transcripciones.csv")
    catalogo = pd.read_csv(DATOS / "raw" / "catalogo_descargas.csv")
    (DATOS / "raw" / "recortes").mkdir(parents=True, exist_ok=True)
    (DATOS / "ejemplos" / "recortes").mkdir(parents=True, exist_ok=True)

    filas = []
    for id_, caja in MUESTRA_DOCS.items():
        d = documentos.set_index("id").loc[id_]
        im = Image.open(RAIZ / d["archivo"]).convert("RGB")
        w, h = im.size
        recorte = im.crop((int(caja[0] * w), int(caja[1] * h), int(caja[2] * w), int(caja[3] * h)))
        ruta = DATOS / "raw" / "recortes" / f"{id_}.png"
        recorte.save(ruta)
        if d["publicable"]:
            shutil.copy(ruta, DATOS / "ejemplos" / "recortes" / f"{id_}.png")
        filas.append({"id": id_, "modalidad": "documento", "tipo": d["tipo"], "archivo_eval": ruta.relative_to(RAIZ).as_posix(),
                      "recorte": ",".join(map(str, caja)), "fuente": d["fuente"], "publicable": d["publicable"]})

    oficiales = catalogo.dropna(subset=["texto_oficial"]).set_index("id")["texto_oficial"]
    slr = transcripciones[transcripciones["origen"].str.startswith("openslr")]
    elegidos = list(slr["origen"].iloc[:N_OPENSLR // 2]) + list(slr["origen"].iloc[-(N_OPENSLR // 2):])  # 2 mujeres + 2 hombres
    seleccion = [(o, 1, "lectura en estudio (OpenSLR 73)") for o in elegidos]
    seleccion += [(o, p, c) for (o, p), c in MUESTRA_AUDIO.items()]
    for origen, parte, condicion in seleccion:
        clips = transcripciones[transcripciones["origen"] == origen].sort_values("inicio")
        c = clips.iloc[parte - 1]
        filas.append({"id": c["id"], "modalidad": "audio", "tipo": condicion, "archivo_eval": c["archivo_audio"],
                      "duracion_seg": c["duracion_seg"], "origen": origen, "fuente": c["fuente"],
                      "texto_oficial": oficiales.get(origen, "")})
    muestra = pd.DataFrame(filas)
    muestra.to_csv(DATOS / "muestra_evaluacion.csv", index=False)
    return muestra


def muestra_auditoria(semilla: int = 2026) -> pd.DataFrame:
    """20 extracciones del LLM al azar para la auditoría humana: 10 documentos y 10 audios (semilla fija)."""
    ext = pd.read_csv(DATOS / "extraccion_llm.csv")
    muestra = pd.concat([ext[ext["modalidad"] == m].sample(10, random_state=semilla) for m in ["documento", "audio"]])
    muestra[["id", "modalidad"]].to_csv(DATOS / "muestra_auditoria.csv", index=False)
    return muestra


if __name__ == "__main__":
    import sys
    if "--auditoria" in sys.argv:
        print(muestra_auditoria()[["id", "modalidad"]].to_string(index=False))
        raise SystemExit
    m = preparar()
    print(m[["id", "modalidad", "tipo", "archivo_eval"]].to_string(index=False))
    audio = m[m["modalidad"] == "audio"]
    print(f"\nA transcribir a mano: {len(m) - len(audio)} recortes y {audio['duracion_seg'].sum() / 60:.1f} min de audio")
