import { api } from "./api.js";
import { $, $$, esc, rwf, toast, initTabs, fillSelect, countUp } from "./ui.js";

const state = { meta: null, ingredients: [], current: null };
const MAX_IMAGE_MB = 5;
const MAX_VIDEO_MB = 50;

async function boot() {
  state.meta = await api.get("/api/meta/");
  state.ingredients = (await api.get("/api/ingredients/")).ingredients;

  fillSelect($("#r-meal"), state.meta.meal_types);
  fillSelect($("#i-cat"), state.meta.categories);
  fillSelect($("#i-unit"), state.meta.units);
  $("#r-focuses").innerHTML = state.meta.focuses.map((f) =>
    `<label class="check"><input type="checkbox" value="${esc(f.slug)}"> ${f.icon} ${esc(f.name)}</label>`).join("");
  resetForm();

  const show = initTabs((tab) => {
    if (tab === "recipes") loadRecipes();
    if (tab === "ingredients") renderIngredients();
    if (tab === "orders") loadOrders();
    loadStats();
  });
  show("publish");
  loadStats();
  bind();

  const bar = $("#topbar");
  const onScroll = () => bar.classList.toggle("scrolled", window.scrollY > 8);
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });
}

/* ---------------------------------------------------------------- stats */
let statsAnimated = false;
async function loadStats() {
  const s = await api.get("/api/admin/stats/");
  const items = [
    ["📚 Recipes", s.recipes, String], ["✅ Published", s.published, String], ["🥬 Ingredients", s.ingredients, String],
    ["📦 Orders", s.orders, String], ["💰 Revenue", s.revenue_rwf, rwf], ["👥 Customers", s.users, String],
  ];
  $("#stats").innerHTML = items.map(([l]) => `<div class="stat"><b>0</b><span>${l}</span></div>`).join("");
  $$("#stats .stat b").forEach((b, i) => {
    const [, value, fmt] = items[i];
    // count up on the first load only; later refreshes just update the number
    if (statsAnimated) b.textContent = fmt(value); else countUp(b, value, fmt);
  });
  statsAnimated = true;
}

/* ---------------------------------------------------------------- recipe form */
function ingredientOptions(selected) {
  return state.ingredients.map((i) =>
    `<option value="${i.id}" ${i.id === selected ? "selected" : ""}>${esc(i.name)} (${i.unit})</option>`).join("");
}

function addItemRow(ingredientId = null, quantity = "") {
  const row = document.createElement("div");
  row.className = "irow";
  row.innerHTML = `<select>${ingredientOptions(ingredientId)}</select>
    <input type="number" min="0.01" step="any" placeholder="Qty" value="${quantity}" required>
    <button type="button" class="btn small danger" aria-label="Remove">×</button>`;
  row.querySelector("button").addEventListener("click", () => row.remove());
  $("#r-items").append(row);
}

function resetForm() {
  $("#recipe-form").reset();
  $("#r-id").value = "";
  $("#r-items").innerHTML = "";
  $("#form-title").textContent = "Publish a new meal kit";
  state.current = null;
  $("#r-existing").innerHTML = "";
  $("#r-existing-video").innerHTML = "";
  clearPreviews();
  addItemRow();
  addItemRow();
}

/* ---------------------------------------------------------------- photos & video */
function clearPreviews() {
  $$("#r-previews img").forEach((i) => URL.revokeObjectURL(i.src));
  $("#r-previews").innerHTML = "";
}

function renderExistingMedia(r) {
  $("#r-existing").innerHTML = r.images.map((i) => `
    <figure class="thumb" data-img="${i.id}"><img src="${esc(i.url)}" alt="Recipe photo">
      <button type="button" class="x" aria-label="Remove photo">×</button></figure>`).join("");
  $("#r-existing-video").innerHTML = r.video
    ? `<div class="notice">🎬 Current demo video: ${r.has_video_file ? "uploaded file" : esc(r.video_url)}
        <button type="button" class="btn small danger" id="rm-video">Remove video</button></div>`
    : "";
}

function previewSelected() {
  clearPreviews();
  const files = [...$("#r-images").files];
  const existing = state.current?.images.length ?? 0;
  if (existing + files.length > 8) {
    toast("A recipe can have at most 8 photos", "err");
    $("#r-images").value = "";
    return;
  }
  const tooBig = files.find((f) => f.size > MAX_IMAGE_MB * 1024 * 1024);
  if (tooBig) {
    toast(`"${tooBig.name}" is larger than ${MAX_IMAGE_MB} MB`, "err");
    $("#r-images").value = "";
    return;
  }
  $("#r-previews").innerHTML = files
    .map((f) => `<figure class="thumb"><img src="${URL.createObjectURL(f)}" alt="New photo preview"></figure>`).join("");
}

async function uploadMedia(recipe) {
  const files = [...$("#r-images").files];
  if (files.length) {
    const fd = new FormData();
    files.forEach((f) => fd.append("images", f));
    await api.post(`/api/admin/recipes/${recipe.id}/images/`, fd);
  }
  const videoFile = $("#r-video").files[0];
  const url = $("#r-video-url").value.trim();
  const before = state.current?.video_url ?? "";
  if (videoFile || url !== before) {
    const fd = new FormData();
    if (videoFile) fd.append("video", videoFile);
    else if (url) fd.append("video_url", url);
    else fd.append("clear", "1");
    await api.post(`/api/admin/recipes/${recipe.id}/video/`, fd);
  }
}

function editRecipe(r) {
  $("#r-id").value = r.id;
  $("#r-title").value = r.title;
  $("#r-emoji").value = r.emoji;
  $("#r-desc").value = r.description;
  $("#r-meal").value = r.meal_type;
  $("#r-prep").value = r.prep_minutes;
  $("#r-serv").value = r.base_servings;
  $("#r-kcal").value = r.calories_per_serving;
  $("#r-note").value = r.doctor_note;
  $("#r-steps").value = r.instructions;
  $("#r-pub").checked = r.is_published;
  $$("#r-focuses input").forEach((c) => (c.checked = r.focuses.includes(c.value)));
  $("#r-items").innerHTML = "";
  r.items.forEach((i) => addItemRow(i.ingredient_id, i.quantity));
  state.current = r;
  renderExistingMedia(r);
  clearPreviews();
  $("#r-images").value = "";
  $("#r-video").value = "";
  $("#r-video-url").value = r.video_url || "";
  $("#form-title").textContent = `Editing: ${r.title}`;
  $$("#tabs button")[0].click();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function saveRecipe(e) {
  e.preventDefault();
  const items = $$("#r-items .irow").map((row) => ({
    ingredient_id: Number(row.querySelector("select").value),
    quantity: row.querySelector("input").value,
  }));
  try {
    const { recipe } = await api.post("/api/admin/recipes/", {
      id: $("#r-id").value || null,
      title: $("#r-title").value,
      emoji: $("#r-emoji").value,
      description: $("#r-desc").value,
      meal_type: $("#r-meal").value,
      prep_minutes: $("#r-prep").value,
      base_servings: $("#r-serv").value,
      calories_per_serving: $("#r-kcal").value,
      doctor_note: $("#r-note").value,
      instructions: $("#r-steps").value,
      is_published: $("#r-pub").checked,
      focuses: $$("#r-focuses input:checked").map((c) => c.value),
      items,
    });
    // The recipe now exists, so photos/video can be attached to it.
    $("#r-id").value = recipe.id;
    try {
      await uploadMedia(recipe);
    } catch (err) {
      // Keep the form open (now in edit mode) so the admin can retry just the media.
      state.current = recipe;
      renderExistingMedia(recipe);
      toast(`Recipe saved, but the photo/video upload failed: ${err.message}`, "err");
      return;
    }
    toast(`"${recipe.title}" saved. Live for users now.`, "ok");
    resetForm();
    loadStats();
  } catch (err) { toast(err.message, "err"); }
}

/* ---------------------------------------------------------------- recipe list */
async function loadRecipes() {
  const { recipes } = await api.get("/api/admin/recipes/");
  const byId = Object.fromEntries(recipes.map((r) => [r.id, r]));
  $("#recipe-table").innerHTML = recipes.map((r) => `
    <div class="item" data-id="${r.id}">
      <span style="font-size:1.6rem">${esc(r.emoji)}</span>
      <div class="grow-1"><strong>${esc(r.title)}</strong>
        <span class="muted tiny">${esc(r.meal_type)} · ${r.items.length} ingredients · ${r.focuses.join(", ") || "no tags"}</span></div>
      <span class="pill ${r.is_published ? "" : "warn"}">${r.is_published ? "Published" : "Draft"}</span>
      <button class="btn small" data-act="edit">Edit</button>
      <button class="btn small" data-act="toggle">${r.is_published ? "Unpublish" : "Publish"}</button>
      <button class="btn small danger" data-act="delete">Delete</button>
    </div>`).join("") || `<div class="empty">No recipes yet.</div>`;

  $("#recipe-table").onclick = async (e) => {
    const btn = e.target.closest("[data-act]");
    if (!btn) return;
    const r = byId[btn.closest(".item").dataset.id];
    try {
      if (btn.dataset.act === "edit") return editRecipe(r);
      if (btn.dataset.act === "toggle") await api.patch(`/api/admin/recipes/${r.id}/`, { is_published: !r.is_published });
      if (btn.dataset.act === "delete") {
        if (!confirm(`Delete "${r.title}"? This cannot be undone.`)) return;
        await api.del(`/api/admin/recipes/${r.id}/`);
      }
      loadRecipes(); loadStats();
    } catch (err) { toast(err.message, "err"); }
  };
}

/* ---------------------------------------------------------------- ingredients */
function renderIngredients() {
  $("#ing-table").innerHTML = state.ingredients.map((i) => `
    <div class="item">
      <div class="grow-1"><strong>${esc(i.name)}</strong><span class="muted tiny">${esc(i.kinyarwanda_name)} · ${esc(i.category_label)}</span></div>
      <span class="pill">${i.price_per_unit_rwf} RWF / ${i.unit}</span>
      ${i.is_local ? `<span class="pill blue">Local</span>` : ""}
    </div>`).join("");
}

async function saveIngredient(e) {
  e.preventDefault();
  try {
    await api.post("/api/admin/ingredients/", {
      name: $("#i-name").value, kinyarwanda_name: $("#i-kiny").value, category: $("#i-cat").value,
      unit: $("#i-unit").value, price_per_unit_rwf: $("#i-price").value, is_local: $("#i-local").checked,
    });
    state.ingredients = (await api.get("/api/ingredients/")).ingredients;
    $("#ing-form").reset();
    renderIngredients();
    toast("Ingredient saved", "ok");
  } catch (err) { toast(err.message, "err"); }
}

/* ---------------------------------------------------------------- orders */
async function loadOrders() {
  const { orders, statuses } = await api.get("/api/admin/orders/");
  $("#order-table").innerHTML = orders.map((o) => `
    <div class="card">
      <div class="item" style="border:0;padding:0">
        <div class="grow-1"><strong>#${o.id} · ${esc(o.recipe_title)} ×${o.servings}</strong>
          <span class="muted tiny">${esc(o.customer)} · ${esc(o.zone_name)} · ${esc(o.payment_method)} · ${new Date(o.created_at).toLocaleString()}</span></div>
        <b>${rwf(o.total_rwf)}</b>
        <select data-order="${o.id}" style="width:auto">${statuses.map((s) =>
          `<option value="${s.value}" ${s.value === o.status ? "selected" : ""}>${esc(s.label)}</option>`).join("")}</select>
      </div>
      <div class="muted tiny" style="margin-top:.4rem">${o.items.map((i) => `${i.quantity}${i.unit} ${esc(i.name)}`).join(" · ")}</div>
    </div>`).join("") || `<div class="empty">No orders yet.</div>`;
  $$("[data-order]").forEach((s) => s.addEventListener("change", async () => {
    await api.post("/api/admin/orders/", { id: Number(s.dataset.order), status: s.value });
    toast("Order status updated", "ok");
    loadStats();
  }));
}

/* ---------------------------------------------------------------- events */
function bind() {
  $("#recipe-form").addEventListener("submit", saveRecipe);
  $("#add-item").addEventListener("click", () => addItemRow());
  $("#reset-form").addEventListener("click", resetForm);
  $("#r-images").addEventListener("change", previewSelected);
  $("#r-video").addEventListener("change", () => {
    const f = $("#r-video").files[0];
    if (f && f.size > MAX_VIDEO_MB * 1024 * 1024) {
      toast(`Video is larger than ${MAX_VIDEO_MB} MB. Upload it to YouTube and paste the link instead.`, "err");
      $("#r-video").value = "";
    }
  });
  $("#r-existing").addEventListener("click", async (e) => {
    const btn = e.target.closest(".x");
    if (!btn || !state.current) return;
    const fig = btn.closest("[data-img]");
    if (!confirm("Remove this photo?")) return;
    try {
      await api.del(`/api/admin/recipes/${state.current.id}/images/${fig.dataset.img}/`);
      state.current.images = state.current.images.filter((i) => String(i.id) !== fig.dataset.img);
      fig.remove();
    } catch (err) { toast(err.message, "err"); }
  });
  $("#r-existing-video").addEventListener("click", async (e) => {
    if (e.target.id !== "rm-video" || !state.current) return;
    const fd = new FormData();
    fd.append("clear", "1");
    try {
      await api.post(`/api/admin/recipes/${state.current.id}/video/`, fd);
      Object.assign(state.current, { video: null, video_url: "", has_video_file: false });
      $("#r-video-url").value = "";
      renderExistingMedia(state.current);
    } catch (err) { toast(err.message, "err"); }
  });
  $("#ing-form").addEventListener("submit", saveIngredient);
}

boot().catch((e) => toast(e.message, "err"));
