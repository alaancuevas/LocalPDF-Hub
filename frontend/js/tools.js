// The tool catalogue. `endpoint` matches docs/api.md; `fields` builds the
// options form and the request body.

const PDF = { extensions: [".pdf"], label: "PDF" };
const IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".jfif", ".heic", ".heif", ".tif", ".tiff"];
const IMAGE = { extensions: IMAGE_EXTENSIONS, label: "JPG, PNG, HEIC, TIFF" };
const PDF_OR_IMAGE = { extensions: [".pdf", ...IMAGE_EXTENSIONS], label: "PDF, JPG, PNG, HEIC, TIFF" };

// Page options of Image to PDF, with its defaults first.
const PAGE_FIELDS = [
  {
    name: "pagesize",
    label: "optionPageSize",
    type: "select",
    options: [
      ["A4", "pageSizeA4"],
      ["letter", "pageSizeLetter"],
      ["fit", "pageSizeFit"],
    ],
  },
  {
    name: "orientation",
    label: "optionOrientation",
    type: "select",
    options: [
      ["portrait", "orientationPortrait"],
      ["landscape", "orientationLandscape"],
    ],
    // A page that fits the image has no orientation of its own.
    disabledWhen: { field: "pagesize", value: "fit" },
  },
  {
    name: "margin",
    label: "optionMargin",
    type: "select",
    options: [
      ["0", "marginNone"],
      ["20", "marginSmall"],
      ["40", "marginLarge"],
    ],
  },
];
const WORD = { extensions: [".docx"], label: "DOCX" };

export const GROUPS = [
  { label: "groupOrganize", tools: ["merge", "mergeAll", "split", "rotate", "compress"] },
  { label: "groupSecurity", tools: ["protect", "unlock", "watermark"] },
  { label: "groupConvert", tools: ["imagesToPdf", "extractImages", "toImages", "toWord", "fromWord"] },
];

export const TOOLS = {
  merge: { icon: "files", endpoint: "merge", accepts: PDF, multiple: true, rotatable: true, fields: [] },
  mergeAll: {
    icon: "stack",
    endpoint: "merge",
    accepts: PDF_OR_IMAGE,
    multiple: true,
    rotatable: true,
    fields: PAGE_FIELDS,
  },
  imagesToPdf: {
    icon: "images-square",
    endpoint: "images-to-pdf",
    accepts: IMAGE,
    multiple: true,
    rotatable: true,
    fields: [...PAGE_FIELDS, { name: "merge_after", label: "optionMergeAfter", type: "checkbox", value: true }],
  },
  split: {
    icon: "scissors",
    endpoint: "split",
    accepts: PDF,
    pagePicker: "select",
    fields: [{ name: "pages", label: "optionPages", hint: "optionPagesHint", type: "text", required: true }],
  },
  rotate: { icon: "arrow-clockwise", endpoint: "rotate", accepts: PDF, pagePicker: "rotate", fields: [] },
  compress: {
    icon: "arrows-in",
    endpoint: "compress",
    accepts: PDF,
    // Recommended first; lossless keeps the images as they are.
    fields: [
      {
        name: "level",
        label: "optionLevel",
        type: "select",
        value: "recommended",
        options: [
          ["recommended", "levelRecommended"],
          ["extreme", "levelExtreme"],
          ["lossless", "levelLossless"],
        ],
      },
    ],
  },
  protect: {
    icon: "lock-simple",
    endpoint: "protect",
    accepts: PDF,
    takesPassword: true,
    // Typed twice; only the first one goes to the server.
    fields: [
      { name: "password", label: "optionPassword", type: "password", required: true },
      {
        name: "password2",
        label: "optionPasswordRepeat",
        type: "password",
        required: true,
        matches: "password",
        send: false,
      },
    ],
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
    // Defaults are the API's, so an untouched form and an empty field ask for the same mark.
    fields: [
      { name: "text", label: "optionText", type: "text", required: true },
      {
        name: "position",
        label: "optionPosition",
        type: "select",
        value: "center",
        options: [
          ["center", "positionCenter"],
          ["top-left", "positionTopLeft"],
          ["top", "positionTop"],
          ["top-right", "positionTopRight"],
          ["left", "positionLeft"],
          ["right", "positionRight"],
          ["bottom-left", "positionBottomLeft"],
          ["bottom", "positionBottom"],
          ["bottom-right", "positionBottomRight"],
          ["mosaic", "positionMosaic"],
        ],
      },
      {
        name: "rotation",
        label: "optionRotation",
        type: "select",
        value: "45",
        options: [
          ["0", "rotation0"],
          ["45", "rotation45"],
          ["90", "rotation90"],
          ["180", "rotation180"],
          ["270", "rotation270"],
        ],
      },
      { name: "size", label: "optionSize", hint: "optionSizeHint", type: "number", min: 8, max: 200, step: 1 },
      { name: "color", label: "optionColor", type: "color", value: "#000000" },
      { name: "opacity", label: "optionOpacity", type: "range", min: 0.05, max: 1, step: 0.05, value: 0.3 },
      { name: "pages", label: "optionMarkPages", hint: "optionMarkPagesHint", type: "text" },
    ],
  },
  extractImages: { icon: "extract-images", endpoint: "extract-images", accepts: PDF, fields: [] },
  toImages: {
    icon: "pdf-to-images",
    endpoint: "to-images",
    accepts: PDF,
    fields: [
      {
        name: "format",
        label: "optionFormat",
        type: "select",
        value: "png",
        options: [
          ["png", "formatPng"],
          ["jpg", "formatJpg"],
        ],
      },
      {
        name: "dpi",
        label: "optionResolution",
        type: "select",
        value: "150",
        options: [
          ["72", "resolution72"],
          ["150", "resolution150"],
          ["300", "resolution300"],
        ],
      },
    ],
  },
  toWord: { icon: "file-doc", endpoint: "to-word", accepts: PDF, fields: [] },
  fromWord: { icon: "file-pdf", endpoint: "from-word", accepts: WORD, multiple: true, fields: [] },
};

export function accepts(tool, file) {
  const name = file.name.toLowerCase();
  return tool.accepts.extensions.some((extension) => name.endsWith(extension));
}
