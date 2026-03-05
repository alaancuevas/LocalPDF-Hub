window.translations = {
    es: {
        badgeLocal: "Procesamiento 100% Local y Privado",
        titleHome: "Tus archivos nunca salen de tu dispositivo.",
        descHome: "Experimenta herramientas de manipulación de PDF e imágenes seguras y ultrarrápidas totalmente sin conexión. Sin subidas, sin servidores, solo poder local puro.",
        titleMergeCard: "Convertir y Unir",
        descMergeCard: "Convierte imágenes a PDF, une PDFs y combina múltiples archivos en un solo documento.",
        titleProcess: "Unir, convertir y Reordenar Archivos",
        descProcess: "Arrastra y suelta para reorganizar tus archivos. Todo el procesamiento se realiza localmente en tu dispositivo.",
        dropTitle: "Arrastra y suelta los archivos aquí",
        dropDesc: "o haz clic para seleccionar archivos a modificar",
        btnSelectFiles: "Seleccionar Archivos",
        btnClear: "Limpiar todo",
        btnTransformText: "Transformar y Unir",
        loadingTitle: "Uniendo archivos localmente...",
        loadingDesc: "Esto puede tardar unos segundos dependiendo del tamaño de los archivos.",
        badgeLoading: "Procesamiento 100% Local",
        successTitle: "¡Archivos procesados con éxito!",
        successDesc: "Tus documentos están listos para ser descargados.",
        btnSavePdf: "Guardar PDF",
        btnNewTask: "Iniciar nueva tarea",
        errorTitle: "Algo salió mal",
        errorDesc: "Error procesando los archivos. Verifica los formatos e intenta nuevamente.",
        btnTryAgain: "Intentar de nuevo",
        btnBackHub: "Volver al inicio",
        fileSelected: "archivos seleccionados",
        fileSelectedSingular: "archivo seleccionado",
        titleWordCard: "Word a PDF",
        descWordCard: "Convierte tus documentos .docx a formato PDF de forma local.",
        footerRights: "© 2026 LocalPDF Hub. Derechos para Roy.",
        footerPrivacy: "Privacidad y velocidad sin salir de tu red local.",
        titleProcessMerge: "Unir, Convertir y Reordenar Archivos",
        descProcessMerge: "Arrastra y suelta para reorganizar tus archivos. Todo el procesamiento se realiza localmente.",
        titleProcessWord: "Convertir Word a PDF",
        descProcessWord: "Arrastra y suelta tus archivos .docx para convertirlos. Todo el procesamiento es local.",
        titleSplitCard: "Dividir PDF",
        descSplitCard: "Extrae un rango de páginas de tu PDF de forma local.",
        titleProcessSplit: "Dividir Archivo PDF",
        descProcessSplit: "Ingresa el rango de páginas que necesitás extraer del documento.",
        labelFrom: "Desde página:",
        labelTo: "Hasta página:",
        btnTransformSplit: "Cortar y Descargar PDF",
        badgePage: "PAG",
        titlePage: "Página"
    },
    en: {
        badgeLocal: "100% Local & Private Processing",
        titleHome: "Your files never leave your device.",
        descHome: "Experience secure, lightning-fast PDF and image manipulation tools completely offline. No uploads, no servers, just pure local power.",
        titleMergeCard: "Convert & Merge",
        descMergeCard: "Convert images to PDF, merge PDFs, and combine multiple files into a single document.",
        titleProcess: "Merge, Convert & Reorder Files",
        descProcess: "Drag and drop to rearrange your files. All processing happens locally on your device.",
        dropTitle: "Drag & Drop Files Here",
        dropDesc: "or click to select files to modify",
        btnSelectFiles: "Select Files",
        btnClear: "Clear All",
        btnTransformText: "Transform & Merge",
        loadingTitle: "Merging files locally...",
        loadingDesc: "This may take a few seconds depending on the file sizes.",
        badgeLoading: "100% Local Processing",
        successTitle: "Files processed Successfully!",
        successDesc: "Your documents are ready to be downloaded.",
        btnSavePdf: "Save PDF",
        btnNewTask: "Start New Task",
        errorTitle: "Something went wrong",
        errorDesc: "Error processing files. Check the formats and try again.",
        btnTryAgain: "Try Again",
        btnBackHub: "Go back to Hub",
        fileSelected: "files selected",
        fileSelectedSingular: "file selected",
        titleWordCard: "Word to PDF",
        descWordCard: "Convert your .docx documents to PDF format locally.",
        footerRights: "© 2026 LocalPDF Hub. Rights reserved for Roy.",
        footerPrivacy: "Privacy and speed without leaving your local network.",
        titleProcessMerge: "Merge, Convert and Rearrange Files",
        descProcessMerge: "Drag and drop to rearrange your files. All processing happens locally.",
        titleProcessWord: "Convert Word to PDF",
        descProcessWord: "Drag and drop your .docx files to convert them. All processing is local.",
        titleSplitCard: "Split PDF",
        descSplitCard: "Extract a page range from your PDF locally.",
        titleProcessSplit: "Split PDF File",
        descProcessSplit: "Enter the page range you need to extract from the document.",
        labelFrom: "From page:",
        labelTo: "To page:",
        btnTransformSplit: "Cut & Download PDF",
        badgePage: "PAGE",
        titlePage: "Page"
    }
};

window.currentLang = localStorage.getItem('language') || 'es';

const btnLanguage = document.getElementById('btnLanguage');
const langText = document.getElementById('langText');

function applyLanguage() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (window.translations[window.currentLang][key]) {
            el.innerText = window.translations[window.currentLang][key];
        }
    });
    
    langText.innerText = window.currentLang === 'es' ? 'EN' : 'ES';
    
    if (typeof actualizarUI === 'function') {
        actualizarUI();
    }
    
    if (typeof renderizarGrilla === 'function') {
        renderizarGrilla();
    }
}

btnLanguage.addEventListener('click', () => {
    window.currentLang = window.currentLang === 'es' ? 'en' : 'es';
    localStorage.setItem('language', window.currentLang);
    applyLanguage();
});

document.addEventListener('DOMContentLoaded', applyLanguage);