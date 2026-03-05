# LocalPDF Hub

LocalPDF Hub es una herramienta de escritorio potente y privada diseñada para gestionar documentos sin salir de tu computadora. Permite unir archivos PDF, dividir documentos por rangos de páginas, combinar imágenes de múltiples formatos en un solo archivo y convertir documentos Word a PDF de forma instantánea.

## Características Principales

- **Privacidad Total**: Todo el procesamiento ocurre localmente en tu dispositivo (127.0.0.1). Nada se sube a la nube.
- **Dividir por Rango**: Extrae páginas específicas de un PDF con previsualización individual de cada página en tiempo real.
- **Soporte Multi-Formato**: Compatible con PDF, PNG, JPG, JPEG, JFIF y formatos de iPhone (HEIC/HEIF).
- **Soporte Multi-idioma**: Interfaz bilingüe (Español/Inglés) con detección automática de preferencia.
- **Corrección de Rotación**: Detecta automáticamente la orientación de las fotos de celulares para que siempre se vean bien.
- **Conversión de Word**: Transforma archivos .docx a PDF de forma local manteniendo el formato original.
- **Interfaz Intuitiva**: Sistema de arrastrar y soltar con generación de miniaturas instantánea.
- **Cero Residuos**: Sistema de autolimpieza que borra los archivos temporales inmediatamente después de procesarlos.

## Instalación y Uso (Usuario)

1. Ve a la sección **Releases** en este repositorio.
2. Descarga el archivo `LocalPDF_Hub.exe`.
3. Ejecuta el archivo (no requiere instalación). Se abrirá tu navegador automáticamente con la aplicación.

## Desarrollo Local

Si deseas ejecutar el código fuente o realizar modificaciones:

### Requisitos
- Python 3.10+
- Microsoft Word (necesario para la conversión .docx vía COM)

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