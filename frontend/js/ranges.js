// Page lists as people type them ("1-3, 5"). The server parses the same
// text again; here it only keeps the thumbnails and the field in step.

/** Pages named in `text` that exist in a `total`-page document; the rest is ignored. */
export function parseRanges(text, total) {
  const pages = new Set();
  for (const part of text.split(",")) {
    const match = part.trim().match(/^(\d+)(?:\s*-\s*(\d+))?$/);
    if (!match) continue;
    let first = Number(match[1]);
    let last = match[2] ? Number(match[2]) : first;
    if (first > last) [first, last] = [last, first];
    for (let page = Math.max(1, first); page <= Math.min(last, total); page++) pages.add(page);
  }
  return pages;
}

/** The shortest text for a set of pages: {1, 2, 3, 5} becomes "1-3, 5". */
export function formatRanges(pages) {
  const sorted = [...pages].sort((a, b) => a - b);
  const parts = [];
  for (let i = 0; i < sorted.length; ) {
    let j = i;
    while (j + 1 < sorted.length && sorted[j + 1] === sorted[j] + 1) j++;
    parts.push(i === j ? String(sorted[i]) : `${sorted[i]}-${sorted[j]}`);
    i = j + 1;
  }
  return parts.join(", ");
}
