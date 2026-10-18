// Page counts and thumbnails with pdf.js, loaded only when a PDF is first added.

let library;

async function pdfjs() {
  if (!library) {
    library = await import("../libs/pdf.min.mjs");
    library.GlobalWorkerOptions.workerSrc = new URL("../libs/pdf.worker.min.mjs", import.meta.url).href;
  }
  return library;
}

/** Number of pages, 1 for an image, or null when it cannot be read (e.g. a password). */
export async function pageCount(file) {
  if (!file.name.toLowerCase().endsWith(".pdf")) return 1;
  const lib = await pdfjs();
  const task = lib.getDocument({ data: await file.arrayBuffer() });
  try {
    return (await task.promise).numPages;
  } catch {
    return null;
  } finally {
    // In pdf.js 4+ the loading task, not the document, frees the worker memory.
    task.destroy();
  }
}

/**
 * Keeps a PDF open to draw its pages, or returns null when it cannot be read.
 * The caller must call close() when the file leaves the screen.
 */
export async function openPages(file) {
  const lib = await pdfjs();
  const task = lib.getDocument({ data: await file.arrayBuffer() });
  let pdf;
  try {
    pdf = await task.promise;
  } catch {
    task.destroy();
    return null;
  }
  // One page at a time: a long document scrolled quickly would otherwise
  // start hundreds of renders at once.
  let queue = Promise.resolve();
  return {
    count: pdf.numPages,
    draw(number, canvas, box) {
      queue = queue.then(() => drawPage(pdf, number, canvas, box)).catch(() => {});
      return queue;
    },
    close: () => task.destroy(),
  };
}

async function drawPage(pdf, number, canvas, box) {
  const page = await pdf.getPage(number);
  const natural = page.getViewport({ scale: 1 });
  // The viewport already applies the page's own /Rotate.
  const viewport = page.getViewport({ scale: box / Math.max(natural.width, natural.height) });
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.floor(viewport.width * ratio);
  canvas.height = Math.floor(viewport.height * ratio);
  canvas.style.width = `${Math.floor(viewport.width)}px`;
  canvas.style.height = `${Math.floor(viewport.height)}px`;
  const transform = ratio === 1 ? null : [ratio, 0, 0, ratio, 0, 0];
  await page.render({ canvas, viewport, transform }).promise;
  page.cleanup();
}
