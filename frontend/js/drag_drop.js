window.archivosSeleccionados = [];
let dragStartIndex;

const dropArea = document.getElementById('dropArea');
const dropAreaContainer = document.getElementById('dropAreaContainer');
const fileGrid = document.getElementById('fileGrid');
const fileCounter = document.getElementById('fileCounter');
const fileText = document.getElementById('fileText');
const btnClear = document.getElementById('btnClear');

const fileInput = document.createElement('input');
fileInput.type = 'file';
fileInput.multiple = true;
fileInput.style.display = 'none';
document.body.appendChild(fileInput);

dropArea.addEventListener('click', () => {
    if (window.currentTool === 'word-to-pdf') {
        fileInput.accept = '.docx';
    } else {
        fileInput.accept = 'application/pdf, image/png, image/jpeg, image/jpg, .heic, .heif, .jfif, .jif';
    }
    fileInput.click();
});

dropArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropArea.classList.add('bg-primary/20', 'dark:bg-primary/40');
});

dropArea.addEventListener('dragleave', () => {
    dropArea.classList.remove('bg-primary/20', 'dark:bg-primary/40');
});

dropArea.addEventListener('drop', (e) => {
    e.preventDefault();
    dropArea.classList.remove('bg-primary/20', 'dark:bg-primary/40');
    procesarArchivos(e.dataTransfer.files);
});

fileInput.addEventListener('change', (e) => {
    procesarArchivos(e.target.files);
    fileInput.value = '';
});

async function procesarArchivos(archivos) {
    const listaArchivos = Array.from(archivos);
    let filtrados = [];

    if (window.currentTool === 'word-to-pdf') {
        filtrados = listaArchivos.filter(a => a.name.toLowerCase().endsWith('.docx'));
    } else {
        filtrados = listaArchivos.filter(a => 
            a.type.match('image.*') || 
            a.type === 'application/pdf' ||
            a.name.toLowerCase().endsWith('.heic') ||
            a.name.toLowerCase().endsWith('.heif') ||
            a.name.toLowerCase().endsWith('.jfif') ||
            a.name.toLowerCase().endsWith('.jif')
        );
    }

    for (let archivo of filtrados) {
        const item = {
            file: archivo,
            id: Math.random().toString(36).substring(7),
            url: null
        };
        
        window.archivosSeleccionados.push(item);
        renderizarGrilla();

        if (archivo.type.match('image.*') && !archivo.name.toLowerCase().endsWith('.heic')) {
            item.url = URL.createObjectURL(archivo);
            renderizarGrilla();
        } else if (archivo.type === 'application/pdf') {
            generarMiniaturaPDF(archivo, item.id);
        }
    }
}

async function generarMiniaturaPDF(archivo, id) {
    try {
        const arrayBuffer = await archivo.arrayBuffer();
        const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
        const page = await pdf.getPage(1);
        const viewport = page.getViewport({ scale: 0.5 });
        const canvas = document.createElement('canvas');
        const context = canvas.getContext('2d');
        canvas.height = viewport.height;
        canvas.width = viewport.width;
        await page.render({ canvasContext: context, viewport: viewport }).promise;
        const dataUrl = canvas.toDataURL('image/jpeg', 0.8);
        const item = window.archivosSeleccionados.find(i => i.id === id);
        if (item) {
            item.url = dataUrl;
            renderizarGrilla();
        }
    } catch (error) { console.error("Error miniatura:", error); }
}

function renderizarGrilla() {
    fileGrid.innerHTML = '';
    
    window.archivosSeleccionados.forEach((item, index) => {
        const div = document.createElement('div');
        div.className = 'group relative flex flex-col bg-white dark:bg-[#1a2235] rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm hover:shadow-md transition-shadow overflow-hidden cursor-move';
        div.draggable = true;
        div.setAttribute('data-index', index);
        
        let badgeClass = 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300';
        let tipoTxt = 'FILE';
        const ext = item.file.name.split('.').pop().toUpperCase();
        
        if (item.file.type === 'application/pdf') {
            badgeClass = 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400';
            tipoTxt = 'PDF';
        } else if (item.file.type.includes('image') || ['HEIC', 'HEIF', 'JFIF', 'JIF'].includes(ext)) {
            badgeClass = 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400';
            tipoTxt = ext;
        }

        div.innerHTML = `
            <div class="absolute top-2 right-2 z-10 opacity-0 group-hover:opacity-100 transition-opacity">
                <button class="flex items-center justify-center size-8 rounded-full bg-white/90 dark:bg-slate-800/90 text-slate-600 dark:text-slate-300 hover:text-red-500 shadow-sm" onclick="eliminarArchivo('${item.id}')">
                    <span class="material-symbols-outlined text-[18px]">close</span>
                </button>
            </div>
            <div class="absolute top-2 left-2 z-10">
                <span class="px-2 py-1 rounded text-xs font-bold ${badgeClass}">${tipoTxt}</span>
            </div>
            <div class="aspect-[3/4] bg-slate-100 dark:bg-[#101622] bg-cover bg-top flex items-center justify-center border-b border-slate-100 dark:border-slate-800" 
                 style="${item.url ? `background-image: url('${item.url}')` : ''}">
                ${!item.url ? `<span class="material-symbols-outlined text-[40px] text-slate-300">description</span>` : ''}
            </div>
            <div class="p-3 bg-white dark:bg-[#1a2235] flex items-center justify-between pointer-events-none">
                <p class="text-slate-700 dark:text-slate-300 text-sm font-medium truncate pr-2">${item.file.name}</p>
                <span class="material-symbols-outlined text-slate-300 dark:text-slate-600 text-[18px]">drag_indicator</span>
            </div>
        `;
        
        div.addEventListener('dragstart', dragStart);
        div.addEventListener('dragover', dragOver);
        div.addEventListener('drop', dragDrop);
        div.addEventListener('dragenter', dragEnter);
        div.addEventListener('dragleave', dragLeave);
        fileGrid.appendChild(div);
    });

    // Solo agregar la tarjeta si hay al menos un archivo
    if (window.archivosSeleccionados.length > 0) {
        const addCard = document.createElement('div');
        addCard.className = 'flex flex-col items-center justify-center bg-white/5 dark:bg-[#1a2235]/50 rounded-xl border-2 border-dashed border-slate-200 dark:border-slate-800 hover:border-primary dark:hover:border-primary transition-all cursor-pointer aspect-[3/4] group';
        addCard.onclick = () => fileInput.click();
        addCard.innerHTML = `
            <span class="material-symbols-outlined text-slate-400 group-hover:text-primary text-[40px] mb-2">add_circle</span>
            <span class="text-slate-500 dark:text-slate-400 text-sm font-bold">Agregar más</span>
        `;
        fileGrid.appendChild(addCard);
    }

    actualizarUI();
}

function dragStart(e) { dragStartIndex = +this.getAttribute('data-index'); e.dataTransfer.effectAllowed = 'move'; }
function dragOver(e) { e.preventDefault(); }
function dragEnter(e) { e.preventDefault(); this.classList.add('ring-2', 'ring-primary'); }
function dragLeave() { this.classList.remove('ring-2', 'ring-primary'); }
function dragDrop() {
    this.classList.remove('ring-2', 'ring-primary');
    const dragEndIndex = +this.getAttribute('data-index');
    const item = window.archivosSeleccionados.splice(dragStartIndex, 1)[0];
    window.archivosSeleccionados.splice(dragEndIndex, 0, item);
    renderizarGrilla();
}

window.eliminarArchivo = function(id) {
    window.archivosSeleccionados = window.archivosSeleccionados.filter(item => item.id !== id);
    renderizarGrilla();
}

btnClear.addEventListener('click', () => { window.archivosSeleccionados = []; renderizarGrilla(); });

function actualizarUI() {
    const total = window.archivosSeleccionados.length;
    fileCounter.textContent = total;
    if (window.translations && window.currentLang) {
        fileText.textContent = total === 1 ? window.translations[window.currentLang].fileSelectedSingular : window.translations[window.currentLang].fileSelected;
    }
    dropAreaContainer.style.display = total > 0 ? 'none' : 'flex';
}