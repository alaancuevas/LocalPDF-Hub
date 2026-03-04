const viewHome = document.getElementById('view-home');
const viewProceso = document.getElementById('view-proceso');
const viewCargando = document.getElementById('view-cargando');
const viewCompletado = document.getElementById('view-completado');
const viewError = document.getElementById('view-error');
const btnLogo = document.getElementById('btnLogo');
const btnToolMerge = document.getElementById('btnToolMerge');
const btnToolWordToPdf = document.getElementById('btnToolWordToPdf');

function showView(viewToShow) {
    [viewHome, viewProceso, viewCargando, viewCompletado, viewError].forEach(v => v.classList.add('hidden'));
    if (viewToShow === viewCargando) { viewProceso.classList.remove('hidden'); viewCargando.classList.remove('hidden'); }
    else { viewToShow.classList.remove('hidden'); }
}

btnLogo.addEventListener('click', () => showView(viewHome));
btnToolMerge.addEventListener('click', () => {
    window.currentTool = 'merge';
    document.querySelector('#view-proceso h1').innerText = "Unir PDF e Imágenes";
    fileInput.accept = 'application/pdf, image/png, image/jpeg, image/jpg';
    showView(viewProceso);
});
btnToolWordToPdf.addEventListener('click', () => {
    window.currentTool = 'word-to-pdf';
    document.querySelector('#view-proceso h1').innerText = "Word a PDF";
    fileInput.accept = '.docx';
    showView(viewProceso);
});
document.getElementById('btnNewTaskComplete').addEventListener('click', () => showView(viewHome));
document.getElementById('btnBackToHub').addEventListener('click', () => showView(viewHome));
document.getElementById('btnTryAgain').addEventListener('click', () => showView(viewProceso));