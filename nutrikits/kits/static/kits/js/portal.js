import { api } from "./api.js";
import { $, $$, esc, rwf, qty, toast, initTabs, fillSelect, matchClass, countUp, initAccordions, lockScroll } from "./ui.js";
import { initCarousel } from "./carousel.js";

const state = {
  meta: null,
  ingredients: [],
  profile: null,
  activeFocus: new Set(),
  version: null,
  orderCount: 0,
  lastFocus: null,
  closestCarousel: null,
};

const CAT_EMOJI = { veg: "🥬", fruit: "🍎", grain: "🌾", legume: "🫘", protein: "🍗", dairy: "🥛", pantry: "🧂" };
const STAGES = [["placed", "Placed"], ["packing", "Packing"], ["out", "On the way"], ["delivered", "Delivered"]];
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const setStat = (sel, n) => countUp($(sel), n);

/* ------------------------------------------------------------------ boot */
async function boot() {
  state.meta = await api.get("/api/meta/");
  const [ing, profile, pantry, orders] = await Promise.all([
    api.get("/api/ingredients/"), api.get("/api/profile/"), api.get("/api/pantry/"), api.get("/api/orders/"),
  ]);
  state.ingredients = ing.ingredients;
  state.profile = profile;
  state.orderCount = orders.orders.length;

  $("#who").textContent = state.meta.user.username;
  $("#hello").textContent = state.meta.user.username;
  setStat("#st-pantry", pantry.pantry.length);
  setStat("#st-orders", state.orderCount);

  renderFocusChips();
  fillSelect($("#meal-filter"), state.meta.meal_types, { placeholder: "All meals" });
  fillSelect($("#pantry-ingredient"), state.ingredients.map((i) => ({ value: i.id, label: `${i.name} (${i.unit})` })));
  renderProfileForm();
  state.closestCarousel = initCarousel($("#closest"));
  bindEvents();

  const show = initTabs((tab) => {
    if (tab === "pantry") loadPantry();
    if (tab === "orders") loadOrders();
    if (tab === "meals") loadRecipes();
  });
  show("meals");
  startLiveSync();

  const bar = $("#topbar");
  const onScroll = () => bar.classList.toggle("scrolled", window.scrollY > 8);
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });
}

/* ------------------------------------------------------------------ live sync
   Django has no push channel by default, so the portal polls a tiny version
   endpoint every 8s and reloads the menu when an admin publishes or edits. */
function startLiveSync() {
  const tick = async () => {
    try {
      const v = await api.get("/api/version/");
      const stamp = `${v.recipes}|${v.recipe_count}`;
      if (state.version && state.version !== stamp) {
        toast("🍲 The menu was just updated", "ok");
        if (!$("#tab-meals").hidden) loadRecipes();
      }
      state.version = stamp;
    } catch (_) { /* offline: try again next tick */ }
  };
  tick();
  setInterval(tick, 8000);
}

/* ------------------------------------------------------------------ meals */
function renderFocusChips() {
  $("#focus-chips").innerHTML = state.meta.focuses
    .map((f) => `<button class="chip" data-slug="${esc(f.slug)}" aria-pressed="false" title="${esc(f.description)}">${f.icon} ${esc(f.name)}</button>`)
    .join("");
}

async function loadRecipes() {
  const params = new URLSearchParams();
  let focuses = [...state.activeFocus];
  if ($("#use-profile").checked) focuses = [...new Set([...focuses, ...state.profile.focuses])];
  if (focuses.length) params.set("focus", focuses.join(","));
  if ($("#meal-filter").value) params.set("meal", $("#meal-filter").value);
  if ($("#search").value.trim()) params.set("q", $("#search").value.trim());
  params.set("sort", $("#sort").value);

  const [{ recipes }] = await Promise.all([api.get(`/api/recipes/?${params}`), loadClosest()]);
  $("#result-count").innerHTML = `<b>${recipes.length}</b> meal${recipes.length === 1 ? "" : "s"}`;
  $("#recipes").innerHTML = recipes.length
    ? recipes.map(recipeCard).join("")
    : `<div class="empty"><span class="big-e">🔎</span>No meals match these filters yet.<br>Try removing a health focus or an ingredient restriction.</div>`;
}

/** The sliding row: meals needing the fewest extra ingredients. Always uses the whole menu, not the filters. */
async function loadClosest() {
  const { recipes } = await api.get("/api/recipes/?sort=match");
  const ready = recipes.filter((r) => r.missing_count === 0).length;
  setStat("#st-ready", ready);
  const near = recipes.filter((r) => r.missing_count <= 3).slice(0, 8);
  const box = $("#closest");
  box.hidden = near.length === 0;
  if (!near.length) return;
  $("#closest-title").textContent = ready ? "Ready to cook now" : "Closest to ready";
  $("#closest-track").innerHTML = near.map(recipeCard).join("");
  $("#closest-track").scrollLeft = 0;
  state.closestCarousel?.update();
}

function recipeCard(r, i = 0) {
  const tags = r.focuses.slice(0, 3).map((f) => `<span class="tag">${f.icon} ${esc(f.name)}</span>`).join("");
  return `
  <article class="rcard recipe pop" style="--i:${Math.min(i, 12)}" data-id="${r.id}" tabindex="0" role="button" aria-label="Open ${esc(r.title)}">
    <div class="rmedia tone-${esc(r.meal_type)}">
      ${r.cover ? `<img src="${esc(r.cover)}" alt="" loading="lazy">` : `<span class="remoji" aria-hidden="true">${esc(r.emoji)}</span>`}
      <span class="rtime">⏱ ${r.prep_minutes} min</span>
      ${r.missing_count === 0 ? `<span class="ready">Ready to cook!</span>` : ""}
    </div>
    <div class="rbody">
      <h3>${esc(r.title)}</h3>
      <div class="meta">${esc(cap(r.meal_type))} · ${r.calories_per_serving} kcal/serving</div>
      <div class="tags">${tags}</div>
      <div class="note">${esc(r.doctor_note)}</div>
      <div>
        <div class="match"><span>Pantry match</span><span>${r.match_percent}%</span></div>
        <div class="bar ${matchClass(r.match_percent)}"><span style="width:${r.match_percent}%"></span></div>
      </div>
      <div class="price">${r.missing_count === 0 ? "Nothing to buy" : `Buy ${r.missing_count} item${r.missing_count > 1 ? "s" : ""}: ${rwf(r.missing_cost_rwf)}`}
        ${r.savings_rwf > 0 ? `<s>${rwf(r.full_cost_rwf)}</s>` : ""}</div>
    </div>
  </article>`;
}

/* ------------------------------------------------------------------ gallery + video */
function galleryHTML(r) {
  if (!r.images.length) return `<div class="mhead tone-${esc(r.meal_type)}"><span class="big-emoji" aria-hidden="true">${esc(r.emoji)}</span></div>`;
  const thumbs = r.images.length > 1
    ? `<div class="thumbs">${r.images.map((i, n) =>
        `<img src="${esc(i.url)}" alt="Photo ${n + 1} of ${esc(r.title)}" data-full="${esc(i.url)}" class="${n === 0 ? "on" : ""}" loading="lazy">`).join("")}</div>`
    : "";
  return `<div class="gallery"><img class="main" src="${esc(r.images[0].url)}" alt="${esc(r.title)}">${thumbs}</div>`;
}

function videoHTML(r) {
  const player = r.video.type === "file"
    ? `<video controls preload="metadata" playsinline src="${esc(r.video.url)}">Your browser can't play this video.</video>`
    : `<iframe src="${esc(r.video.url)}" title="How to cook ${esc(r.title)}" loading="lazy" allowfullscreen
         allow="accelerometer; encrypted-media; gyroscope; picture-in-picture" referrerpolicy="strict-origin-when-cross-origin"></iframe>`;
  return `<div class="video-wrap">${player}</div>`;
}

const accItem = (key, icon, title, sub, inner, open) => `
  <div class="acc-item ${open ? "open" : ""}" data-key="${key}">
    <button class="acc-q" aria-expanded="${open}"><span>${icon} ${esc(title)}${sub ? ` <span class="muted tiny">· ${esc(sub)}</span>` : ""}</span><i class="plus">+</i></button>
    <div class="acc-a"><div class="acc-in">${inner}</div></div>
  </div>`;

/* ------------------------------------------------------------------ recipe modal / shopping list */
async function openRecipe(id, servings, keepOpen) {
  const wasHidden = $("#modal").hidden;
  if (wasHidden) state.lastFocus = document.activeElement;
  const r = await api.get(`/api/recipes/${id}/${servings ? `?servings=${servings}` : ""}`);
  const open = new Set(keepOpen ?? ["list"]);

  const zoneOptions = state.meta.zones
    .map((z) => `<option value="${z.id}" ${z.id === state.profile.delivery_zone ? "selected" : ""}>${esc(z.name)} · ${rwf(z.fee_rwf)} · ~${z.eta_minutes} min</option>`)
    .join("");
  const payOptions = state.meta.payments.map((p) => `<option value="${p.value}">${esc(p.label)}</option>`).join("");
  const fee = state.meta.zones.find((z) => z.id === state.profile.delivery_zone)?.fee_rwf ?? state.meta.zones[0]?.fee_rwf ?? 0;

  const lines = r.lines.map((l) => `
    <div class="ing-line">
      <span>${esc(l.name)} ${l.kinyarwanda_name ? `<span class="muted tiny">(${esc(l.kinyarwanda_name)})</span>` : ""}</span>
      <span>${l.in_pantry ? `<span class="ok">✓ in pantry</span>`
        : `<span class="need">need ${qty(l.missing, l.unit)}</span> <span class="muted tiny">· ${rwf(l.cost_rwf)}</span>`}
        <span class="muted tiny"> / ${qty(l.needed, l.unit)} total</span></span>
    </div>`).join("");

  const shopping = `
    ${lines}
    <div class="summary">
      <div class="line"><span>Ingredients to buy (${r.missing_count})</span><span>${rwf(r.missing_cost_rwf)}</span></div>
      <div class="line"><span>You save by using your pantry</span><span>${rwf(r.savings_rwf)}</span></div>
      <div class="line"><span>Delivery</span><span id="fee">${r.missing_count ? rwf(fee) : "-"}</span></div>
      <div class="line total"><span>Total</span><span id="total">${rwf(r.missing_cost_rwf + (r.missing_count ? fee : 0))}</span></div>
    </div>
    ${r.missing_count ? `
    <div class="row">
      <label>Deliver to <select id="o-zone">${zoneOptions}</select></label>
      <label>Pay with <select id="o-pay">${payOptions}</select></label>
    </div>
    <button id="order-btn" class="btn primary block" style="margin-top:.8rem">Order missing ingredients</button>`
      : `<div class="alert" style="background:var(--mint);color:var(--green-dark)">You have everything. Time to cook! 🎉</div>`}`;

  const steps = `<ol class="steps">${r.instructions.map((s) => `<li><span>${esc(s)}</span></li>`).join("")}</ol>`;
  const note = `<div class="note"><b>Nutrition note:</b> ${esc(r.doctor_note)}</div>
    <p class="muted tiny" style="margin:.6rem 0 0">General guidance only. It does not replace your doctor's or dietitian's advice.</p>`;

  $("#modal-body").innerHTML = `
    ${galleryHTML(r)}
    <div class="mbody">
      <h2>${esc(r.emoji)} ${esc(r.title)}</h2>
      <p class="muted" style="margin:0">${esc(r.description)}</p>
      <div class="mchips">
        <span class="pill">⏱ ${r.prep_minutes} min</span><span class="pill">🔥 ${r.calories_per_serving} kcal/serving</span>
        ${r.focuses.map((f) => `<span class="pill blue">${f.icon} ${esc(f.name)}</span>`).join("")}
      </div>
      <div style="display:flex;align-items:center;gap:.8rem;flex-wrap:wrap">
        <div class="stepper"><span><b>Servings</b></span>
          <button data-step="-1" aria-label="Fewer servings">−</button><b id="serv">${r.servings}</b><button data-step="1" aria-label="More servings">+</button></div>
        <span class="pill ${r.match_percent >= 70 ? "" : "warn"}">Pantry match ${r.match_percent}%</span>
      </div>
      <p class="notice" style="margin:.8rem 0 0">⚕️ General guidance only. Follow your own doctor's or dietitian's plan, and check labels if you have allergies. Calories and quantities are estimates.</p>
      <div class="acc">
        ${accItem("list", "🛒", "Your shopping list", r.missing_count ? `${r.missing_count} to buy` : "all in your pantry", shopping, open.has("list"))}
        ${r.video ? accItem("video", "🎬", "Watch how to cook it", "", videoHTML(r), open.has("video")) : ""}
        ${accItem("steps", "👩‍🍳", "How to cook", `${r.instructions.length} steps`, steps, open.has("steps"))}
        ${accItem("note", "🩺", "Nutrition note", "", note, open.has("note"))}
      </div>
    </div>`;
  $("#modal").hidden = false;
  lockScroll(true);
  initAccordions($("#modal-body"));
  if (wasHidden) $("#modal-close").focus({ preventScroll: true });

  $$(".gallery .thumbs img", $("#modal-body")).forEach((t) =>
    t.addEventListener("click", () => {
      $(".gallery .main", $("#modal-body")).src = t.dataset.full;
      $$(".gallery .thumbs img", $("#modal-body")).forEach((x) => x.classList.toggle("on", x === t));
    }));

  $$("[data-step]", $("#modal-body")).forEach((b) =>
    b.addEventListener("click", () => {
      const next = Math.max(1, Math.min(20, r.servings + Number(b.dataset.step)));
      const keep = $$(".acc-item.open", $("#modal-body")).map((i) => i.dataset.key);
      openRecipe(id, next, keep);
    }));

  const zoneSel = $("#o-zone");
  zoneSel?.addEventListener("change", () => {
    const z = state.meta.zones.find((x) => x.id === Number(zoneSel.value));
    $("#fee").textContent = rwf(z.fee_rwf);
    $("#total").textContent = rwf(r.missing_cost_rwf + z.fee_rwf);
  });

  $("#order-btn")?.addEventListener("click", async (e) => {
    e.target.disabled = true;
    try {
      const { order } = await api.post("/api/orders/", {
        recipe_id: id, servings: r.servings, zone_id: Number(zoneSel.value), payment_method: $("#o-pay").value,
      });
      closeModal();
      state.orderCount += 1;
      setStat("#st-orders", state.orderCount);
      toast(`Order #${order.id} placed · ${rwf(order.total_rwf)} total`, "ok");
    } catch (err) {
      toast(err.message, "err");
      e.target.disabled = false;
    }
  });
}

function closeModal() {
  $("#modal").hidden = true;
  $("#modal-body").innerHTML = ""; // also stops any playing video
  lockScroll(false);
  state.lastFocus?.focus?.({ preventScroll: true });
}

/* ------------------------------------------------------------------ pantry */
async function loadPantry() {
  const { pantry } = await api.get("/api/pantry/");
  $("#st-pantry").textContent = pantry.length;
  if (!pantry.length) {
    $("#pantry-list").innerHTML = `<div class="empty"><span class="big-e">🧺</span>Your pantry is empty.<br>Add what you have at home to see how much you can save.</div>`;
    return;
  }
  const groups = new Map();
  pantry.forEach((p) => {
    const key = p.ingredient.category_label;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(p);
  });
  let n = 0;
  $("#pantry-list").innerHTML = [...groups].map(([label, items]) => `
    <h3 style="font-size:1rem;margin:1.1rem 0 .5rem;color:var(--muted)">${esc(label)}</h3>
    <div class="pantry-grid">${items.map((p) => `
      <div class="ptile pop" style="--i:${Math.min(n++, 12)}" data-id="${p.ingredient.id}" data-qty="${p.quantity}" tabindex="0" role="button" aria-label="Edit ${esc(p.ingredient.name)}">
        <span class="pe c-${esc(p.ingredient.category)}" aria-hidden="true">${CAT_EMOJI[p.ingredient.category] ?? "🥣"}</span>
        <div><b>${esc(p.ingredient.name)}</b><small>${esc(p.ingredient.kinyarwanda_name)}</small><br><span class="pill">${qty(p.quantity, p.ingredient.unit)}</span></div>
        <button class="rm" data-remove="${p.ingredient.id}" aria-label="Remove ${esc(p.ingredient.name)}">×</button>
      </div>`).join("")}</div>`).join("");
}

/* ------------------------------------------------------------------ orders */
function trackerHTML(o) {
  if (o.status === "cancelled") return `<p style="margin:.8rem 0 0"><span class="pill bad">Cancelled</span></p>`;
  const idx = Math.max(0, STAGES.findIndex(([s]) => s === o.status));
  return `<div class="track-steps" style="--p:${idx}"><span class="fillbar"></span>${STAGES.map(([, label], i) =>
    `<div class="ts ${i <= idx ? "done" : ""} ${i === idx && o.status !== "delivered" ? "now" : ""}"><i>${i <= idx && (i < idx || o.status === "delivered") ? "✓" : i + 1}</i>${label}</div>`).join("")}</div>`;
}

async function loadOrders() {
  const { orders } = await api.get("/api/orders/");
  state.orderCount = orders.length;
  $("#st-orders").textContent = orders.length;
  $("#orders-list").innerHTML = orders.length
    ? orders.map((o, i) => `
      <div class="card order pop" style="--i:${Math.min(i, 10)}">
        <div class="order-top">
          <div class="grow-1"><strong>#${o.id} · ${esc(o.recipe_title)}</strong>
            <span class="muted tiny">${new Date(o.created_at).toLocaleString()} · ${esc(o.zone_name)} · ${esc(o.payment_method)}</span></div>
          <span class="pill ${o.status === "delivered" ? "" : o.status === "cancelled" ? "bad" : "blue"}">${esc(o.status_label)}</span>
          <b>${rwf(o.total_rwf)}</b>
        </div>
        ${trackerHTML(o)}
        <div class="order-items">${o.items.map((it) => `${qty(it.quantity, it.unit)} ${esc(it.name)}`).join(" · ")}</div>
      </div>`).join("")
    : `<div class="empty"><span class="big-e">📦</span>No orders yet.<br>Pick a meal and order only the missing ingredients.</div>`;
}

/* ------------------------------------------------------------------ profile */
function renderProfileForm() {
  $("#profile-focuses").innerHTML = state.meta.focuses.map((f) => `
    <label class="check"><input type="checkbox" value="${esc(f.slug)}" ${state.profile.focuses.includes(f.slug) ? "checked" : ""}> ${f.icon} ${esc(f.name)}</label>`).join("");
  fillSelect($("#p-zone"), state.meta.zones.map((z) => ({ value: z.id, label: `${z.name} (${rwf(z.fee_rwf)})` })), { placeholder: "Choose your area…" });
  $("#p-zone").value = state.profile.delivery_zone ?? "";
  $("#p-allergies").value = state.profile.allergies;
  $("#p-phone").value = state.profile.phone;
  $("#p-note").value = state.profile.address_note;
  $("#use-profile").checked = state.profile.focuses.length > 0;
}

/* ------------------------------------------------------------------ events */
function bindEvents() {
  $("#focus-chips").addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    const s = chip.dataset.slug;
    state.activeFocus.has(s) ? state.activeFocus.delete(s) : state.activeFocus.add(s);
    chip.classList.toggle("on");
    chip.setAttribute("aria-pressed", String(state.activeFocus.has(s)));
    loadRecipes();
  });
  ["#meal-filter", "#sort", "#use-profile"].forEach((s) => $(s).addEventListener("change", loadRecipes));
  let t;
  $("#search").addEventListener("input", () => { clearTimeout(t); t = setTimeout(loadRecipes, 250); });

  // One delegated handler for both the main grid and the sliding row
  const openFrom = (e) => { const c = e.target.closest(".recipe"); if (c) openRecipe(c.dataset.id); };
  ["#recipes", "#closest-track"].forEach((sel) => {
    $(sel).addEventListener("click", openFrom);
    $(sel).addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openFrom(e); } });
  });

  $("#modal-close").addEventListener("click", closeModal);
  $("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#modal").hidden) closeModal(); });

  const syncUnit = () => {
    const ing = state.ingredients.find((i) => i.id === Number($("#pantry-ingredient").value));
    $("#pantry-unit").textContent = ing ? ing.unit : "";
  };
  $("#pantry-ingredient").addEventListener("change", syncUnit);
  syncUnit();
  $("#pantry-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api.post("/api/pantry/", { ingredient_id: Number($("#pantry-ingredient").value), quantity: $("#pantry-qty").value });
      $("#pantry-qty").value = "";
      toast("Pantry updated", "ok");
      loadPantry();
    } catch (err) { toast(err.message, "err"); }
  });
  $("#pantry-list").addEventListener("click", async (e) => {
    const rm = e.target.closest("[data-remove]");
    if (rm) {
      e.stopPropagation();
      await api.del(`/api/pantry/${rm.dataset.remove}/`);
      toast("Removed from pantry");
      loadPantry();
      return;
    }
    const tile = e.target.closest(".ptile"); // tap a tile to edit it in the form
    if (tile) {
      $("#pantry-ingredient").value = tile.dataset.id;
      $("#pantry-qty").value = tile.dataset.qty;
      syncUnit();
      $("#pantry-qty").focus();
      $("#pantry-form").scrollIntoView({ behavior: "smooth", block: "center" });
    }
  });
  $("#pantry-list").addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.classList.contains("ptile")) e.target.click(); });

  $("#profile-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      state.profile = await api.post("/api/profile/", {
        focuses: $$("#profile-focuses input:checked").map((i) => i.value),
        allergies: $("#p-allergies").value,
        delivery_zone: $("#p-zone").value || null,
        phone: $("#p-phone").value,
        address_note: $("#p-note").value,
      });
      $("#use-profile").checked = state.profile.focuses.length > 0;
      toast("Health profile saved", "ok");
    } catch (err) { toast(err.message, "err"); }
  });
}

boot().catch((e) => toast(e.message, "err"));
