"""Extracción estructurada con un LLM local (Qwen2.5-3B-Instruct) sobre los textos OCR y ASR ya seudonimizados.

    tarea_2/.venv-gpu/Scripts/python tarea_2/herramientas/extraer_llm.py

Corre en el entorno aparte .venv-gpu (PyTorch con CUDA) porque el entorno del curso trae PyTorch solo para CPU.
Lee datos/documentos.csv y datos/transcripciones.csv y escribe datos/extraccion_llm.csv con
id, modalidad, campos_json, modelo_llm, fecha (+ segundos y si el JSON fue válido).

Decodificación greedy (sin muestreo): la misma entrada da siempre la misma salida.
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

RAIZ = Path(__file__).resolve().parents[1]
DATOS = RAIZ / "datos"
MODELO = "Qwen/Qwen2.5-3B-Instruct"
MAX_CHARS = 3500  # los periódicos completos pasan de 6000 caracteres: se usa el comienzo

SISTEMA = """Eres un asistente de archivo que extrae datos de textos peruanos obtenidos por OCR o por transcripción de audio.
Respondes SOLO con un objeto JSON válido, sin texto adicional ni bloques de código.
Reglas estrictas:
- Usa únicamente información que aparece en el texto. Si un dato no aparece, escribe null. No adivines ni completes.
- El texto puede tener errores de OCR o de transcripción; no los corrijas inventando contenido.
- Las etiquetas como PERSONA_1 o [HABLANTE_2] son seudónimos: cópialas tal cual si las necesitas.
- "resumen": 1 o 2 oraciones en español, fieles al texto."""

ESQUEMA_DOC = """Devuelve este JSON:
{"modalidad": "documento",
 "tipo_documento": "comunicado | carta | periódico | revista | resolución | diploma | acta | partida | recibo | boletín | otro",
 "tema": "tema principal en pocas palabras",
 "resumen": "...",
 "emisor": "institución o persona que emite el documento, o null",
 "fecha": "fecha tal como aparece en el texto, o null",
 "lugar": "ciudad o lugar que aparece en el texto, o null",
 "monto": "cantidad de dinero tal como aparece, o null"}"""

ESQUEMA_AUDIO = """Devuelve este JSON:
{"modalidad": "audio",
 "tipo_audio": "entrevista | testimonio | lectura | conferencia | otro",
 "tema": "tema principal en pocas palabras",
 "resumen": "...",
 "citas_clave": ["hasta 2 frases copiadas literalmente del texto"],
 "numero_hablantes": "número de hablantes distintos SOLO si el texto trae marcas [HABLANTE_n]; si no, null",
 "lugar": "lugar mencionado en el texto, o null"}"""


def cargar():
    tok = AutoTokenizer.from_pretrained(MODELO)
    modelo = AutoModelForCausalLM.from_pretrained(MODELO, dtype=torch.bfloat16, device_map="cuda")
    return tok, modelo


def preguntar(tok, modelo, texto: str, esquema: str) -> tuple[str, float]:
    mensajes = [{"role": "system", "content": SISTEMA},
                {"role": "user", "content": f"{esquema}\n\nTEXTO:\n\"\"\"\n{texto[:MAX_CHARS]}\n\"\"\""}]
    entrada = tok.apply_chat_template(mensajes, add_generation_prompt=True, return_tensors="pt", return_dict=True).to("cuda")
    t0 = time.perf_counter()
    with torch.inference_mode():
        salida = modelo.generate(**entrada, max_new_tokens=400, do_sample=False)
    respuesta = tok.decode(salida[0, entrada["input_ids"].shape[1]:], skip_special_tokens=True)
    return respuesta, time.perf_counter() - t0


def a_json(respuesta: str) -> tuple[dict | None, bool]:
    """Toma el primer objeto JSON de la respuesta. Devuelve (campos, era_valido)."""
    m = re.search(r"\{.*\}", respuesta, re.S)
    if not m:
        return None, False
    try:
        return json.loads(m.group(0)), True
    except json.JSONDecodeError:
        return None, False


def main():
    docs = pd.read_csv(DATOS / "documentos.csv")
    auds = pd.read_csv(DATOS / "transcripciones.csv")
    tareas = [(r.id, "documento", r.texto_ocr, ESQUEMA_DOC) for r in docs.itertuples()]
    tareas += [(r.id, "audio", r.texto_asr, ESQUEMA_AUDIO) for r in auds.itertuples()]
    tok, modelo = cargar()
    print(f"{MODELO} en {torch.cuda.get_device_name(0)} · {len(tareas)} textos", flush=True)
    filas = []
    for id_, modalidad, texto, esquema in tareas:
        texto = texto if isinstance(texto, str) else ""
        respuesta, seg = preguntar(tok, modelo, texto, esquema)
        campos, valido = a_json(respuesta)
        if campos is None:
            campos = {"modalidad": modalidad, "error": "respuesta sin JSON válido", "respuesta_cruda": respuesta[:500]}
        campos["modalidad"] = modalidad
        filas.append({"id": id_, "modalidad": modalidad, "campos_json": json.dumps(campos, ensure_ascii=False),
                      "modelo_llm": f"{MODELO} (bf16, GPU, greedy)", "fecha": date.today().isoformat(),
                      "segundos": round(seg, 2), "json_valido": valido})
        print(f"{id_:10s} {seg:5.1f} s  {'ok' if valido else 'JSON INVÁLIDO'}  {campos.get('tema')}", flush=True)
    salida = pd.DataFrame(filas)
    salida.to_csv(DATOS / "extraccion_llm.csv", index=False)
    print(f"\n{salida['json_valido'].mean():.0%} de respuestas con JSON válido · {salida['segundos'].sum() / 60:.1f} min")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
