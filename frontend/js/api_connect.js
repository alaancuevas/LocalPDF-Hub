const btnTransformAction = document.getElementById('btnTransform');
const progressCircle = document.getElementById('progressCircle');
const progressText = document.getElementById('progressText');
let progressInterval;

function startSimulatedProgress() {
    let currentProgress = 0;
    progressCircle.style.strokeDashoffset = 282.7;
    progressText.innerText = '0%';
    
    progressInterval = setInterval(() => {
        if (currentProgress < 90) {
            currentProgress += Math.floor(Math.random() * 5) + 2;
            if (currentProgress > 90) currentProgress = 90;
            progressCircle.style.strokeDashoffset = 282.7 - (currentProgress / 100) * 282.7;
            progressText.innerText = `${currentProgress}%`;
        }
    }, 200);
}

btnTransformAction.addEventListener('click', async () => {
    if (window.archivosSeleccionados.length === 0) return;

    const formData = new FormData();
    window.archivosSeleccionados.forEach(item => {
        formData.append('archivos', item.file);
    });

    const endpoint = window.currentTool === 'word-to-pdf' 
        ? 'http://127.0.0.1:8000/convertir-word' 
        : 'http://127.0.0.1:8000/procesar';
    
    showView(viewCargando);
    startSimulatedProgress();

    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            body: formData
        });

        if (response.ok) {
            clearInterval(progressInterval);
            progressCircle.style.strokeDashoffset = '0';
            progressText.innerText = '100%';

            const blob = await response.blob();
            const downloadUrl = URL.createObjectURL(blob);

            // Configuramos el botón de descarga
            const btnGuardar = document.querySelector('#view-completado button');
            const newBtn = btnGuardar.cloneNode(true);
            btnGuardar.parentNode.replaceChild(newBtn, btnGuardar);
            
            newBtn.addEventListener('click', () => {
                const a = document.createElement('a');
                a.href = downloadUrl;
                a.download = window.currentTool === 'word-to-pdf' ? "documento.pdf" : "unido.pdf";
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
            });

            // --- LIMPIEZA AUTOMÁTICA ---
            window.archivosSeleccionados = []; 
            if (typeof renderizarGrilla === "function") {
                renderizarGrilla(); 
            }
            // ---------------------------

            setTimeout(() => {
                showView(viewCompletado);
            }, 600);

        } else {
            throw new Error("Error en el servidor");
        }
    } catch (error) {
        clearInterval(progressInterval);
        console.error(error);
        showView(viewError);
    }
});