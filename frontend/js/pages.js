// Page counts with pdf.js, loaded only when a PDF is first added.

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
