// The dialog that opens PDFs with a password. pdf.js checks each password
// here, then /unlock (docs/api.md) returns a copy without it, which replaces
// the file. The tools themselves never see a password.

import { ApiError, runTool } from "./api.js";
import { t } from "./i18n.js";
import { probe } from "./pages.js";

/**
 * Asks for the password of each locked entry and swaps in the unlocked copy.
 * Resolves true once every entry is open, false if the user cancels; on
 * cancel the entries keep their locked files. `tooBig(entry, size)` returns
 * a message when the unlocked copy would break the size limits.
 */
export function askPasswords(entries, tooBig) {
  return new Promise((resolve) => {
    const dialog = document.createElement("dialog");
    dialog.setAttribute("aria-labelledby", "passwords-title");
    const form = document.createElement("form");
    const title = el("h2", "", t(entries.length === 1 ? "passwordTitleOne" : "passwordTitle"));
    title.id = "passwords-title";
    form.append(title, el("p", "dialog-note", t("passwordNote")));

    const rows = entries.map((entry, index) => {
      const label = el("label", "field");
      const input = document.createElement("input");
      Object.assign(input, { type: "password", autocomplete: "off", required: true, name: `password-${index}` });
      const error = el("p", "field-error");
      error.id = `password-error-${index}`;
      error.hidden = true;
      input.setAttribute("aria-describedby", error.id);
      label.append(el("span", "field-label", entry.file.name), input, error);
      form.append(label);
      return { entry, input, error, open: false };
    });

    const actions = el("div", "dialog-actions");
    const cancel = el("button", "secondary", t("cancel"));
    cancel.type = "button";
    const submit = el("button", "primary", t("passwordSubmit"));
    submit.type = "submit";
    actions.append(cancel, submit);
    form.append(actions);
    dialog.append(form);
    document.body.append(dialog);

    let settled = false;
    const finish = (opened) => {
      if (settled) return;
      settled = true;
      dialog.close();
      dialog.remove();
      resolve(opened);
    };
    const busy = (on) => {
      submit.disabled = on;
      cancel.disabled = on;
      submit.textContent = t(on ? "passwordWorking" : "passwordSubmit");
    };

    cancel.addEventListener("click", () => finish(false));
    // Escape cancels too, but not halfway through an unlock.
    dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      if (!submit.disabled) finish(false);
    });
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      busy(true);
      // One at a time: the server would queue the unlock jobs anyway.
      for (const row of rows) {
        if (row.open) continue;
        const problem = await unlock(row, tooBig);
        row.error.textContent = problem;
        row.error.hidden = !problem;
        row.input.setAttribute("aria-invalid", String(Boolean(problem)));
        if (problem) {
          busy(false);
          row.input.focus();
          row.input.select();
          return;
        }
        row.open = true;
        row.input.disabled = true;
      }
      finish(true);
    });
    dialog.showModal();
  });
}

async function unlock(row, tooBig) {
  const { entry } = row;
  const password = row.input.value;
  const checked = await probe(entry.file, password);
  if (checked.state === "wrong" || checked.state === "locked") return t("error.ERR_WRONG_PASSWORD");
  // pdf.js accepted it; the server has the last word, and its error is shown as is.
  const body = new FormData();
  body.append("file", entry.file, entry.file.name);
  body.append("password", password);
  let blob;
  try {
    ({ blob } = await runTool("unlock", body));
  } catch (error) {
    return t(`error.${error instanceof ApiError ? error.code : "ERR_INTERNAL"}`);
  }
  const problem = tooBig(entry, blob.size);
  if (problem) return problem;
  // The name the user picked, not "<name>_unlocked.pdf"; the locked file is dropped.
  entry.file = new File([blob], entry.file.name, { type: "application/pdf" });
  Object.assign(entry, { locked: false, password, pages: checked.pages });
  return "";
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
