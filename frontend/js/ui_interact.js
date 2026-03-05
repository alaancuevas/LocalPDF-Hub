const viewHome = document.getElementById('view-home');
const viewProceso = document.getElementById('view-proceso');
const viewCargando = document.getElementById('view-cargando');
const viewCompletado = document.getElementById('view-completado');
const viewError = document.getElementById('view-error');
const btnLogo = document.getElementById('btnLogo');
const btnToolMerge = document.getElementById('btnToolMerge');
const btnToolWordToPdf = document.getElementById('btnToolWordToPdf');
const btnToolSplit = document.getElementById('btnToolSplit');
const processTitleText = document.getElementById('processTitleText');
const processDescText = document.getElementById('processDescText');
const splitSettings = document.getElementById('split-settings');

function showView(viewToShow) {
    [viewHome, viewProceso, viewCargando, viewCompletado, viewError].forEach(v => v.classList.add('hidden'));
    if (viewToShow === viewCargando) { 
        viewProceso.classList.remove('hidden'); 
        viewCargando.classList.remove('hidden'); 
    }
    else { 
        viewToShow.classList.remove('hidden'); 
    }
}

btnLogo.addEventListener('click', () => showView(viewHome));

btnToolMerge.addEventListener('click', () => {
    window.currentTool = 'merge';
    processTitleText.setAttribute('data-i18n', 'titleProcessMerge');
    processDescText.setAttribute('data-i18n', 'descProcessMerge');
    splitSettings.classList.add('hidden');
    
    if (typeof applyLanguage === 'function') {
        applyLanguage();
    }

    fileInput.accept = 'application/pdf, image/png, image/jpeg, image/jpg';
    showView(viewProceso);
});

btnToolWordToPdf.addEventListener('click', () => {
    window.currentTool = 'word-to-pdf';
    processTitleText.setAttribute('data-i18n', 'titleProcessWord');
    processDescText.setAttribute('data-i18n', 'descProcessWord');
    splitSettings.classList.add('hidden');
    
    if (typeof applyLanguage === 'function') {
        applyLanguage();
    }

    fileInput.accept = '.docx';
    showView(viewProceso);
});

btnToolSplit.addEventListener('click', () => {
    window.currentTool = 'split';
    processTitleText.setAttribute('data-i18n', 'titleProcessSplit');
    processDescText.setAttribute('data-i18n', 'descProcessSplit');
    
    const btnTransform = document.getElementById('btnTransform');
    btnTransform.querySelector('span[data-i18n]').setAttribute('data-i18n', 'btnTransformSplit');
    btnTransform.querySelector('.material-symbols-outlined').innerText = 'content_cut';
    
    splitSettings.classList.remove('hidden');
    
    if (typeof applyLanguage === 'function') {
        applyLanguage();
    }
    fileInput.accept = 'application/pdf'; 
    showView(viewProceso);
});

document.getElementById('btnNewTaskComplete').addEventListener('click', () => showView(viewHome));
document.getElementById('btnBackToHub').addEventListener('click', () => showView(viewHome));
document.getElementById('btnTryAgain').addEventListener('click', () => showView(viewProceso));