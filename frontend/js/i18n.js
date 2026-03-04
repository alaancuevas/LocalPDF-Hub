window.translations = {
    es: {
        badgeLocal: "Procesamiento 100% Local y Privado",
        titleHome: "Tus archivos nunca salen de tu dispositivo.",
        descHome: "Experimenta herramientas de manipulación de PDF e imágenes seguras y ultrarrápidas totalmente sin conexión. Sin subidas, sin servidores, solo poder local puro.",
        titleMergeCard: "Unir PDF e Imágenes",
        descMergeCard: "Combina múltiples archivos en un solo documento cohesivo con facilidad.",
        titleProcess: "Unir y Reordenar Archivos",
        descProcess: "Arrastra y suelta para reorganizar tus archivos. Todo el procesamiento se realiza localmente en tu dispositivo.",
        dropTitle: "Arrastra y suelta los archivos aquí",
        dropDesc: "o haz clic para seleccionar archivos PDF e imágenes",
        btnSelectFiles: "Seleccionar Archivos",
        btnClear: "Limpiar todo",
        btnTransformText: "Transformar y Unir",
        loadingTitle: "Uniendo archivos localmente...",
        loadingDesc: "Esto puede tardar unos segundos dependiendo del tamaño de los archivos.",
        badgeLoading: "Procesamiento 100% Local",
        successTitle: "¡Archivos unidos con éxito!",
        successDesc: "Tus documentos están listos para ser descargados.",
        btnSavePdf: "Guardar PDF",
        btnNewTask: "Iniciar nueva tarea",
        errorTitle: "Algo salió mal",
        errorDesc: "Error procesando los archivos. Verifica los formatos e intenta nuevamente.",
        btnTryAgain: "Intentar de nuevo",
        btnBackHub: "Volver al inicio",
        fileSelected: "archivos seleccionados",
        fileSelectedSingular: "archivo seleccionado"
    },
    en: {
        badgeLocal: "100% Local & Private Processing",
        titleHome: "Your files never leave your device.",
        descHome: "Experience secure, lightning-fast PDF and image manipulation tools completely offline. No uploads, no servers, just pure local power.",
        titleMergeCard: "Merge PDF & Images",
        descMergeCard: "Combine multiple files into a single cohesive document with ease.",
        titleProcess: "Merge & Reorder Files",
        descProcess: "Drag and drop to rearrange your files. All processing happens locally on your device.",
        dropTitle: "Drag & Drop Files Here",
        dropDesc: "or click to select PDF and image files",
        btnSelectFiles: "Select Files",
        btnClear: "Clear All",
        btnTransformText: "Transform & Merge",
        loadingTitle: "Merging files locally...",
        loadingDesc: "This may take a few seconds depending on the file sizes.",
        badgeLoading: "100% Local Processing",
        successTitle: "Files Merged Successfully!",
        successDesc: "Your documents are ready to be downloaded.",
        btnSavePdf: "Save PDF",
        btnNewTask: "Start New Task",
        errorTitle: "Something went wrong",
        errorDesc: "Error processing files. Check the formats and try again.",
        btnTryAgain: "Try Again",
        btnBackHub: "Go back to Hub",
        fileSelected: "files selected",
        fileSelectedSingular: "file selected"
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
}

btnLanguage.addEventListener('click', () => {
    window.currentLang = window.currentLang === 'es' ? 'en' : 'es';
    localStorage.setItem('language', window.currentLang);
    applyLanguage();
});

document.addEventListener('DOMContentLoaded', applyLanguage);