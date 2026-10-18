// Page counts and thumbnails with pdf.js, loaded only when a PDF is first added.

let library;

async function pdfjs() {
  if (!library) {
    library = await import("../libs/pdf.min.mjs");
    library.GlobalWorkerOptions.workerSrc = new URL("../libs/pdf.worker.min.mjs", import.meta.url).href;
  }
  return library;
}

/**
 * Opens a file once to learn what it is.
 *   ok       opens (an image counts as one page)
 *   locked   needs a password to open (pdf.js NEED_PASSWORD)
 *   wrong    the password given is not correct (INCORRECT_PASSWORD)
 *   damaged  pdf.js says it is not a PDF it can read (InvalidPDFException)
 *   aborted  the file was replaced while it opened; nobody is waiting
 *   unknown  anything else, e.g. the worker ran out of memory: the server decides
 */
export async function probe(file, password) {
  if (!file.name.toLowerCase().endsWith(".pdf")) return { state: "ok", pages: 1 };
  const lib = await pdfjs();
  const task = lib.getDocument({ data: await file.arrayBuffer(), password });
  try {
    return { state: "ok", pages: (await task.promise).numPages };
  } catch (error) {
    return { state: classify(lib, error), pages: null };
  } finally {
    // In pdf.js 4+ the loading task, not the document, frees the worker memory.
    task.destroy();
  }
}

function classify(lib, error) {
  if (error?.name === "PasswordException") {
    return error.code === lib.PasswordResponses.INCORRECT_PASSWORD ? "wrong" : "locked";
  }
  if (error?.name === "InvalidPDFException") return "damaged";
  if (error?.name === "AbortException") return "aborted";
  return "unknown";
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

/**
 * The first page of a result, drawn once, with its page count. pdf.js is
 * closed as soon as the page is drawn. Returns { locked: true } for an
 * encrypted result and null when it cannot be read or the signal aborted.
 */
export async function thumbnail(blob, box, signal) {
  const lib = await pdfjs();
  if (signal.aborted) return null;
  const task = lib.getDocument({ data: await blob.arrayBuffer() });
  const stop = () => task.destroy();
  signal.addEventListener("abort", stop, { once: true });
  try {
    const pdf = await task.promise;
    const canvas = document.createElement("canvas");
    await drawPage(pdf, 1, canvas, box);
    return signal.aborted ? null : { canvas, pages: pdf.numPages };
  } catch (error) {
    return error?.name === "PasswordException" ? { locked: true } : null;
  } finally {
    signal.removeEventListener("abort", stop);
    task.destroy();
  }
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
