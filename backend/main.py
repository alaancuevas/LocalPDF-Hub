import os
import uuid
import shutil
import time
import sys
import webbrowser
import uvicorn
import pythoncom
from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PyPDF2 import PdfMerger
from PIL import Image, ImageOps
from docx2pdf import convert
from pillow_heif import register_heif_opener

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
        return {"error": str(e)}, 500

@app.post("/convertir-word")
async def convertir_word(archivos: list[UploadFile] = File(...)):
    pythoncom.CoInitialize()
    task_id = str(uuid.uuid4())
    task_dir = os.path.join(BASE_TEMP, task_id)
    os.makedirs(task_dir)
    archivo = archivos[0]
    nombre_ext = archivo.filename.split('.')[-1].lower()
    nombre_temp = os.path.join(task_dir, f"input.{nombre_ext}")
    nombre_pdf = os.path.join(task_dir, "output.pdf")
    resultado_final = os.path.join(BASE_TEMP, f"word_{task_id}.pdf")
    try:
        contenido = await archivo.read()
        with open(nombre_temp, "wb") as f:
            f.write(contenido)
        convert(nombre_temp, nombre_pdf)
        shutil.copy(nombre_pdf, resultado_final)
        time.sleep(0.5)
        shutil.rmtree(task_dir, ignore_errors=True)
        return FileResponse(resultado_final, media_type="application/pdf", filename=f"{archivo.filename.split('.')[0]}.pdf")
    except Exception as e:
        if os.path.exists(task_dir):
            shutil.rmtree(task_dir, ignore_errors=True)
        return {"error": str(e)}, 500
    finally:
        pythoncom.CoUninitialize()

frontend_path = os.path.join(get_base_path(), "frontend")
app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")

if __name__ == "__main__":
    webbrowser.open("http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000, use_colors=False)