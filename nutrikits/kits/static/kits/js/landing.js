// Landing page interactions: menus, carousels, reveal-on-scroll, count-up, meal finder, FAQ accordion.
import { $, $$, esc, countUp, reduceMotion } from "./ui.js";
import { initCarousel } from "./carousel.js";

let DATA = { recipes: [], focuses: [], cta_url: "/register/" };
try { DATA = JSON.parse($("#landing-data").textContent); } catch (_) { /* page still works without the finder */ }

/* ---------- announcement bar ---------- */
const bar = $("#announce");
try { if (sessionStorage.getItem("nk-announce") === "off") bar?.classList.add("gone"); } catch (_) {}
$("#announce-close")?.addEventListener("click", () => {
  bar.classList.add("gone");
  try { sessionStorage.setItem("nk-announce", "off"); } catch (_) {}
});

/* ---------- nav: shadow on scroll, mobile menu, dropdown ---------- */
const nav = $("#lnav");
const onScroll = () => nav.classList.toggle("scrolled", window.scrollY > 8);
onScroll();
window.addEventListener("scroll", onScroll, { passive: true });

const burger = $("#burger"), menu = $("#lmenu");
const setMenu = (open) => { menu.classList.toggle("open", open); burger.setAttribute("aria-expanded", String(open)); };
burger.addEventListener("click", () => setMenu(!menu.classList.contains("open")));
$$("#lmenu a").forEach((a) => a.addEventListener("click", () => setMenu(false)));

const dd = $(".has-dd"), ddBtn = $("#dd-toggle");
const setDD = (open) => { dd.classList.toggle("open", open); ddBtn.setAttribute("aria-expanded", String(open)); };
ddBtn.addEventListener("click", (e) => { e.stopPropagation(); setDD(!dd.classList.contains("open")); });
document.addEventListener("click", (e) => { if (!dd.contains(e.target)) setDD(false); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") { setDD(false); setMenu(false); } });
$$("#dd-menu a").forEach((a) => a.addEventListener("click", () => { setDD(false); selectFocus(a.dataset.focus); }));

/* ---------- carousels (steps + meal rows) ---------- */
$$("[data-carousel]").forEach(initCarousel);

/* ---------- reveal on scroll ---------- */
const reveals = $$(".reveal");
if (reduceMotion || !("IntersectionObserver" in window)) {
  reveals.forEach((el) => el.classList.add("in"));
} else {
  const io = new IntersectionObserver((entries) => {
    entries.forEach((en) => {
      if (!en.isIntersecting) return;
      en.target.classList.add("in");
      $$(".count", en.target).forEach((c) => countUp(c, Number(c.dataset.count)));
      io.unobserve(en.target);
    });
  }, { threshold: 0.12, rootMargin: "0px 0px -6% 0px" });
  reveals.forEach((el) => io.observe(el));
}
$$(".pl-bar i").forEach((i) => { i.style.setProperty("--w", i.style.width); i.style.width = ""; });

/* ---------- meal finder ---------- */
const chipsBox = $("#find-chips"), panel = $("#find-panel");
let activeFocus = "all";

function renderChips() {
  const all = [{ slug: "all", name: "All meals", icon: "🍽️" }, ...DATA.focuses];
  chipsBox.innerHTML = all.map((f) =>
    `<button class="fchip ${f.slug === activeFocus ? "on" : ""}" data-slug="${esc(f.slug)}" aria-pressed="${f.slug === activeFocus}">${f.icon} ${esc(f.name)}</button>`).join("");
}
function renderPanel() {
  const focus = DATA.focuses.find((f) => f.slug === activeFocus);
  const list = DATA.recipes.filter((r) => activeFocus === "all" || r.focuses.some((f) => f.slug === activeFocus));
  const shown = list.slice(0, 4);
  const title = focus ? `${focus.icon} ${esc(focus.name)}` : "🍽️ Every meal, one place";
  const blurb = focus ? esc(focus.description) : "Browse the full menu, then narrow it down by focus.";
  panel.innerHTML = `
    <div class="fp-main"><h3>${title}</h3><p>${blurb}</p>
      <p><b>${list.length}</b> meal${list.length === 1 ? "" : "s"} to choose from</p>
      <a class="lbtn solid" style="width:fit-content" href="${esc(DATA.cta_url)}">See my matches</a>
      <p class="tiny-l">A filter to help you browse. Not a diagnosis, and not a substitute for your doctor's advice.</p></div>
    <div class="fp-list">${shown.map((r, i) => `
      <a class="fp-item" style="animation-delay:${i * 60}ms" href="${esc(DATA.cta_url)}">
        <span class="e">${r.cover ? `<img src="${esc(r.cover)}" alt="">` : esc(r.emoji)}</span>
        <span><b>${esc(r.title)}</b><small>${r.prep} min · ${r.kcal} kcal · ~${esc(r.cost_label)} RWF/serving</small></span></a>`).join("") ||
      `<p class="muted">No meals tagged for this focus yet.</p>`}</div>`;
}
function selectFocus(slug) {
  activeFocus = DATA.focuses.some((f) => f.slug === slug) ? slug : "all";
  renderChips(); renderPanel();
}
chipsBox.addEventListener("click", (e) => { const b = e.target.closest(".fchip"); if (b) selectFocus(b.dataset.slug); });
renderChips(); renderPanel();

/* ---------- FAQ accordion ---------- */
$$(".faq-q").forEach((btn) => btn.addEventListener("click", () => {
  const item = btn.closest(".faq-item");
  const open = !item.classList.contains("open");
  $$(".faq-item.open").forEach((i) => { i.classList.remove("open"); $(".faq-q", i).setAttribute("aria-expanded", "false"); });
  item.classList.toggle("open", open);
  btn.setAttribute("aria-expanded", String(open));
}));
