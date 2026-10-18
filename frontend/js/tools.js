// The tool catalogue. `endpoint` matches docs/api.md; `fields` builds the
// options form and the request body.

const PDF = { extensions: [".pdf"], label: "PDF" };
const PDF_OR_IMAGE = {
  extensions: [".pdf", ".png", ".jpg", ".jpeg", ".jfif", ".heic", ".heif"],
  label: "PDF, JPG, PNG, HEIC",
};
const WORD = { extensions: [".docx"], label: "DOCX" };

export const GROUPS = [
  { label: "groupOrganize", tools: ["merge", "split", "rotate", "compress"] },
  { label: "groupSecurity", tools: ["protect", "unlock", "watermark"] },
  { label: "groupConvert", tools: ["extractImages", "toImages", "toWord", "fromWord"] },
];

export const TOOLS = {
  merge: { icon: "files", endpoint: "merge", accepts: PDF_OR_IMAGE, multiple: true, rotatable: true, fields: [] },
  split: {
    icon: "scissors",
    endpoint: "split",
    accepts: PDF,
    pagePicker: "select",
    fields: [{ name: "pages", label: "optionPages", hint: "optionPagesHint", type: "text", required: true }],
  },
  rotate: { icon: "arrow-clockwise", endpoint: "rotate", accepts: PDF, pagePicker: "rotate", fields: [] },
  compress: { icon: "arrows-in", endpoint: "compress", accepts: PDF, fields: [] },
  protect: {
    icon: "lock-simple",
    endpoint: "protect",
    accepts: PDF,
    takesPassword: true,
    fields: [{ name: "password", label: "optionPassword", type: "password", required: true }],
  },
  unlock: {
    icon: "lock-simple-open",
    endpoint: "unlock",
    accepts: PDF,
    takesPassword: true,
    fields: [{ name: "password", label: "optionPassword", type: "password", required: true }],
  },
  watermark: {
    icon: "watermark",
    endpoint: "watermark",
    accepts: PDF,
    fields: [
      { name: "text", label: "optionText", type: "text", required: true },
      { name: "opacity", label: "optionOpacity", type: "range", min: 0.05, max: 1, step: 0.05, value: 0.3 },
    ],
  },
  extractImages: { icon: "extract-images", endpoint: "extract-images", accepts: PDF, fields: [] },
  toImages: { icon: "pdf-to-images", endpoint: "to-images", accepts: PDF, fields: [] },
  toWord: { icon: "file-doc", endpoint: "to-word", accepts: PDF, fields: [] },
  fromWord: { icon: "file-pdf", endpoint: "from-word", accepts: WORD, multiple: true, fields: [] },
};

export function accepts(tool, file) {
  const name = file.name.toLowerCase();
  return tool.accepts.extensions.some((extension) => name.endsWith(extension));
}
