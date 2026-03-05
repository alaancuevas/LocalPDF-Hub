import os
import uuid
import shutil
import time
import sys
import webbrowser
import uvicorn
import pythoncom
import traceback
import zipfile
import io
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PyPDF2 import PdfMerger, PdfReader, PdfWriter
from PIL import Image, ImageOps
from docx2pdf import convert
from pillow_heif import register_heif_opener
from typing import List

register_heif_opener()

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

def get_base_path():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def get_executable_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

BASE_TEMP = os.path.join(get_executable_dir(), "temp")
if not os.path.exists(BASE_TEMP):
    os.makedirs(BASE_TEMP)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def cleanup_final_file(file_path: str, retries=5, delay=2):
    time.sleep(delay)
    for i in range(retries):
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                break
            except Exception:
                time.sleep(delay)

@app.post("/procesar")
async def procesar_archivos(background_tasks: BackgroundTasks, archivos: list[UploadFile] = File(...)):
    task_id = str(uuid.uuid4())
    task_dir = os.path.join(BASE_TEMP, task_id)
    os.makedirs(task_dir)
    merger = PdfMerger()
    resultado_path = os.path.join(BASE_TEMP, f"final_{task_id}.pdf")
    try:
        for index, archivo in enumerate(archivos):
            nombre_ext = archivo.filename.split('.')[-1].lower()
            nombre_temp = os.path.join(task_dir, f"original_{index}.{nombre_ext}")
            contenido = await archivo.read()
            with open(nombre_temp, "wb") as f:
                f.write(contenido)
            if nombre_ext in ['png', 'jpg', 'jpeg', 'heic', 'heif', 'jfif', 'jif']:
                with Image.open(nombre_temp) as imagen:
                    imagen_corregida = ImageOps.exif_transpose(imagen)
                    imagen_pdf = imagen_corregida.convert("RGB")
                    nombre_pdf = os.path.join(task_dir, f"conv_{index}.pdf")
                    imagen_pdf.save(nombre_pdf)
                    merger.append(nombre_pdf)
            elif nombre_ext == 'pdf':
                with open(nombre_temp, "rb") as pdf_file:
                    merger.append(pdf_file)
        with open(resultado_path, "wb") as f_out:
            merger.write(f_out)
        merger.close()
        time.sleep(0.5)
        shutil.rmtree(task_dir, ignore_errors=True)
        background_tasks.add_task(cleanup_final_file, resultado_path)
        return FileResponse(resultado_path, media_type="application/pdf", filename="Documento_Fusionado.pdf")
    except Exception as e:
        if 'merger' in locals():
            merger.close()
        shutil.rmtree(task_dir, ignore_errors=True)
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/convertir-word")
async def convertir_word(archivos: List[UploadFile] = File(...)):
    pythoncom.CoInitialize()
    temp_dir = f"temp_{os.urandom(4).hex()}"
    temp_path = os.path.join(BASE_TEMP, temp_dir)
    os.makedirs(temp_path, exist_ok=True)
    
    pdf_paths = []
    try:
        for archivo in archivos:
            docx_path = os.path.join(temp_path, archivo.filename)
            pdf_filename = archivo.filename.rsplit(".", 1)[0] + ".pdf"
            pdf_path = os.path.join(temp_path, pdf_filename)
            
            contenido = await archivo.read()
            with open(docx_path, "wb") as f:
                f.write(contenido)
            
            convert(docx_path, pdf_path)
            pdf_paths.append((pdf_filename, pdf_path))

        if len(archivos) == 1:
            pdf_filename, pdf_path = pdf_paths[0]
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()
            shutil.rmtree(temp_path, ignore_errors=True)
            return StreamingResponse(
                io.BytesIO(pdf_bytes),
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{pdf_filename}"'}
            )
            
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for pdf_filename, pdf_path in pdf_paths:
                zip_file.write(pdf_path, arcname=pdf_filename)
                
        zip_buffer.seek(0)
        shutil.rmtree(temp_path, ignore_errors=True)
        
        return StreamingResponse(
            zip_buffer, 
            media_type="application/zip", 
            headers={"Content-Disposition": "attachment; filename=Documentos_Convertidos.zip"}
        )
    except Exception as e:
        error_trace = traceback.format_exc()
        shutil.rmtree(temp_path, ignore_errors=True)
        return JSONResponse(status_code=500, content={"error": str(e), "detalle": error_trace})
    finally:
        pythoncom.CoUninitialize()

@app.post("/dividir-pdf")
async def dividir_pdf(background_tasks: BackgroundTasks, archivo: UploadFile = File(...), desde: int = Form(1), hasta: int = Form(1), paginas: str = Form(None)):
    task_id = str(uuid.uuid4())
    task_dir = os.path.join(BASE_TEMP, task_id)
    os.makedirs(task_dir)
    input_path = os.path.join(task_dir, "input.pdf")
    resultado_path = os.path.join(BASE_TEMP, f"split_{task_id}.pdf")
    try:
        contenido = await archivo.read()
        with open(input_path, "wb") as f:
            f.write(contenido)
        reader = PdfReader(input_path)
        writer = PdfWriter()
        total_paginas = len(reader.pages)
        
        if paginas:
            paginas_list = [int(p.strip()) for p in paginas.split(",") if p.strip().isdigit()]
            for p in paginas_list:
                idx = p - 1
                if 0 <= idx < total_paginas:
                    writer.add_page(reader.pages[idx])
        else:
            start = max(0, desde - 1)
            end = min(total_paginas, hasta)
            for i in range(start, end):
                writer.add_page(reader.pages[i])
                
        with open(resultado_path, "wb") as f_out:
            writer.write(f_out)
        shutil.rmtree(task_dir, ignore_errors=True)
        background_tasks.add_task(cleanup_final_file, resultado_path)
        return FileResponse(resultado_path, media_type="application/pdf", filename=f"Recorte_{archivo.filename}")
    except Exception as e:
        if os.path.exists(task_dir):
            shutil.rmtree(task_dir, ignore_errors=True)
        return JSONResponse(status_code=500, content={"error": str(e)})

frontend_path = os.path.join(get_base_path(), "frontend")
app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")

if __name__ == "__main__":
    webbrowser.open("http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000, use_colors=False)