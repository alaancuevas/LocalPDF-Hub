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
    
    let endpoint = 'http://127.0.0.1:8000/procesar';
    let defaultFileName = "Merged_Document.pdf";

    if (window.currentTool === 'word-to-pdf') {
        endpoint = 'http://127.0.0.1:8000/convertir-word';
        window.archivosSeleccionados.forEach(item => {
            formData.append('archivos', item.file);
        });
    } 
    else if (window.currentTool === 'split') {
        endpoint = 'http://127.0.0.1:8000/dividir-pdf';
        defaultFileName = "Extracted_Pages.pdf";
        formData.append('archivo', window.archivosSeleccionados[0].file);
        
        const inputFrom = document.getElementById('split-from');
        if (inputFrom && inputFrom.disabled) {
            const paginasStr = window.archivosSeleccionados.map(item => item.pageNumber).join(',');
            formData.append('paginas', paginasStr);
        } else {
            formData.append('desde', inputFrom.value);
            formData.append('hasta', document.getElementById('split-to').value);
        }
    } 
    else {
        window.archivosSeleccionados.forEach(item => {
            formData.append('archivos', item.file);
        });
    }
    
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

            const btnGuardar = document.querySelector('#view-completado button');
            const newBtn = btnGuardar.cloneNode(true);
            btnGuardar.parentNode.replaceChild(newBtn, btnGuardar);
            
            let finalDownloadName = defaultFileName;
            if (window.currentTool === 'word-to-pdf') {
                if (window.archivosSeleccionados.length > 1) {
                    finalDownloadName = window.currentLang === 'es' ? "Documentos_Convertidos.zip" : "Converted_Documents.zip";
                } else {
                    finalDownloadName = window.archivosSeleccionados[0].file.name.replace(/\.docx$/i, '.pdf');
                }
            }
            
            newBtn.addEventListener('click', () => {
                const a = document.createElement('a');
                a.href = downloadUrl;
                a.download = finalDownloadName;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
            });

            window.archivosSeleccionados = []; 
            if (typeof renderizarGrilla === "function") {
                renderizarGrilla(); 
            }

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