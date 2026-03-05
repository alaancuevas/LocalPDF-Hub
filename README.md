# 📄 LocalPDF Hub

**LocalPDF Hub** es una herramienta de escritorio potente y privada diseñada para gestionar documentos sin salir de tu computadora. Permite unir archivos PDF, dividir documentos por rangos de páginas o selección manual, combinar imágenes de múltiples formatos en un solo archivo y convertir documentos Word a PDF de forma instantánea.

---

## ✨ Características Principales

* **Privacidad Total:** Todo el procesamiento ocurre localmente en tu dispositivo (`127.0.0.1`). Tus documentos sensibles nunca se suben a la nube.
* **División Avanzada de PDF:** Extrae páginas específicas definiendo un rango numérico, o elimínalas manualmente una por una con previsualización individual en tiempo real gracias a PDF.js.
* **Soporte Multi-Formato:** Totalmente compatible con PDF, PNG, JPG, JPEG, JFIF y formatos nativos de dispositivos Apple (HEIC/HEIF).
* **Conversión de Word a PDF:** Transforma archivos `.docx` a PDF de forma local manteniendo el formato original. Soporta procesamiento por lotes (devuelve un `.zip` automático al subir múltiples archivos).
* **Soporte Multi-idioma:** Interfaz bilingüe fluida (Español / Inglés) con detección y guardado automático de tus preferencias.
* **Corrección de Rotación:** Detecta automáticamente la orientación de las fotografías de celulares mediante sus metadatos EXIF para que siempre se visualicen correctamente en tu documento final.
* **Interfaz Intuitiva:** Sistema moderno de arrastrar y soltar (Drag & Drop) con generación instantánea de miniaturas.
* **Cero Residuos:** Sistema de autolimpieza inteligente que elimina los archivos temporales inmediatamente después de procesarlos para no ocupar espacio en tu disco.

---

## 🚀 Instalación y Uso (Usuario Final)

1. Ve a la sección **[Releases](../../releases)** en el panel derecho de este repositorio.
2. Descarga el archivo ejecutable `LocalPDF_Hub.exe` de la última versión disponible.
3. Ejecuta el archivo (es portable, **no requiere instalación**). 
4. Se abrirá automáticamente tu navegador web predeterminado con la aplicación lista para usarse.

---

## 💻 Desarrollo Local

Si deseas ejecutar el código fuente, explorar cómo funciona por dentro o realizar tus propias modificaciones:

### Requisitos Previos
* **Python 3.10+**
* **Microsoft Word** instalado en el sistema (necesario para el motor de conversión `.docx` vía COM).

### Configuración
1. Clona el repositorio.
2. Instala las dependencias:
   `py -m pip install fastapi uvicorn PyPDF2 Pillow pillow-heif docx2pdf pythoncom`
3. Ejecuta el servidor:
   `py backend/main.py`

## Tecnologías Utilizadas
- **Backend**: FastAPI (Python)
- **Frontend**: HTML5, JavaScript (Vanilla), Tailwind CSS
- **Procesamiento**: Pillow, PyPDF2, docx2pdf, PDF.js
- **Empaquetado**: PyInstaller

---
Desarrollado por Roy - 2026