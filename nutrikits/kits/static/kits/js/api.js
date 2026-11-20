// Thin fetch wrapper for the Django JSON API (handles CSRF + errors).
function csrf() {
  const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

async function request(method, url, data) {
  const opts = { method, headers: { "X-CSRFToken": csrf() }, credentials: "same-origin" };
  if (data instanceof FormData) {
    opts.body = data; // browser sets the multipart boundary itself
  } else if (data !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(data);
  }
  const res = await fetch(url, opts);
  if (res.status === 401) { window.location.href = "/login/"; throw new Error("Please sign in"); }
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json.error || `Request failed (${res.status})`);
  return json;
}

export const api = {
  get: (url) => request("GET", url),
  post: (url, data) => request("POST", url, data ?? {}),
  patch: (url, data) => request("PATCH", url, data ?? {}),
  del: (url) => request("DELETE", url),
};
