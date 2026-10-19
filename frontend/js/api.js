// Calls to the local server (docs/api.md). Every POST carries the launch
// token the server put into index.html.

const TOKEN = document.querySelector('meta[name="localpdf-token"]')?.content ?? "";

export class ApiError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

export async function runTool(endpoint, body) {
  let response;
  try {
    response = await fetch(`/api/v1/pdf/${endpoint}`, {
      method: "POST",
      headers: { "X-LocalPDF-Token": TOKEN },
      body,
    });
  } catch (error) {
    throw new ApiError("NETWORK", error.message);
  }
  if (response.ok) {
    return { blob: await response.blob(), name: fileName(response) };
  }
  // A 403 here means the server restarted and this page holds a dead token.
  if (response.status === 403) throw new ApiError("SESSION_EXPIRED", "Forbidden");
  const error = await response.json().catch(() => ({ code: "ERR_INTERNAL", message: response.statusText }));
  throw new ApiError(error.code, error.message);
}

function fileName(response) {
  const header = response.headers.get("content-disposition") ?? "";
  const encoded = header.match(/filename\*=utf-8''([^;]+)/i);
  if (encoded) {
    try {
      return decodeURIComponent(encoded[1]);
    } catch {
      // A malformed escape falls back to the plain name.
    }
  }
  return header.match(/filename="?([^";]+)/i)?.[1] ?? "result";
}
