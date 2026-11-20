// Small shared UI helpers: DOM, formatting, toasts, tabs, accordions, count-up.
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function esc(value) {
  const d = document.createElement("div");
  d.textContent = value ?? "";
  return d.innerHTML;
}

export const rwf = (n) => `${Math.round(n).toLocaleString("en-RW")} RWF`;
export const qty = (n, unit) => (unit === "pc" ? `${+n.toFixed(2)} pc` : `${+n.toFixed(1)} ${unit}`);

export function toast(message, kind = "") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = message;
  $("#toasts").append(el);
  setTimeout(() => el.remove(), 3500);
}

export function initTabs(onChange) {
  const buttons = $$("#tabs button");
  const show = (name) => {
    buttons.forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
    $$(".tab").forEach((t) => {
      const on = t.id === `tab-${name}`;
      t.hidden = !on;
      if (on && !reduceMotion) { t.classList.remove("swap"); void t.offsetWidth; t.classList.add("swap"); }
    });
    onChange?.(name);
  };
  buttons.forEach((b) => b.addEventListener("click", () => { show(b.dataset.tab); window.scrollTo({ top: 0, behavior: "smooth" }); }));
  return show;
}

export function fillSelect(select, options, { placeholder } = {}) {
  select.innerHTML = (placeholder ? `<option value="">${esc(placeholder)}</option>` : "") +
    options.map((o) => `<option value="${esc(String(o.value))}">${esc(o.label)}</option>`).join("");
}

export const matchClass = (p) => (p >= 70 ? "" : p >= 40 ? "mid" : "low");

/** Animate a number from 0 to `target`. `format` turns the number into display text. */
export function countUp(el, target, format = (n) => String(n)) {
  if (!Number.isFinite(target)) return;
  if (reduceMotion || target === 0) { el.textContent = format(target); return; }
  const t0 = performance.now(), dur = 1000;
  const tick = (t) => {
    const p = Math.min((t - t0) / dur, 1);
    el.textContent = format(Math.round(target * (1 - Math.pow(1 - p, 3))));
    if (p < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

/** Expandable sections. Markup: .acc-item[data-key] > button.acc-q + .acc-a > .acc-in */
export function initAccordions(root, { single = false } = {}) {
  $$(".acc-q", root).forEach((btn) => btn.addEventListener("click", () => {
    const item = btn.closest(".acc-item");
    const open = !item.classList.contains("open");
    if (single) $$(".acc-item.open", root).forEach((i) => { i.classList.remove("open"); $(".acc-q", i).setAttribute("aria-expanded", "false"); });
    item.classList.toggle("open", open);
    btn.setAttribute("aria-expanded", String(open));
  }));
}

/** Prevent the page behind a modal from scrolling. */
export const lockScroll = (on) => document.body.classList.toggle("no-scroll", on);
