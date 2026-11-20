// Shared sliding carousel: scroll-snap track + arrows, optional dots, mouse drag, keyboard, gentle autoplay.
// Markup: <div data-carousel> <div class="track">…slides…</div> <button class="car-prev"> <button class="car-next"> [<div class="dots">] </div>
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function initCarousel(root) {
  if (root.dataset.ready) return;
  root.dataset.ready = "1";
  const track = root.querySelector(".track");
  const prev = root.querySelector(".car-prev");
  const next = root.querySelector(".car-next");
  const dotsBox = root.querySelector(".dots");
  const autoMs = Number(root.dataset.autoplay || 0);

  const slides = () => [...track.children];
  const gap = () => parseFloat(getComputedStyle(track).columnGap) || 16;
  const step = () => (track.firstElementChild ? track.firstElementChild.getBoundingClientRect().width + gap() : 300);
  const index = () => Math.round(track.scrollLeft / step());
  const atEnd = () => track.scrollLeft + track.clientWidth >= track.scrollWidth - 4;
  const perClick = dotsBox ? 1 : 2; // dotted carousels move one slide, card rows move two cards

  let dots = [];
  if (dotsBox) {
    dots = slides().map((_, i) => {
      const b = document.createElement("button");
      b.setAttribute("aria-label", `Go to step ${i + 1}`);
      b.addEventListener("click", () => { stopAuto(); track.scrollTo({ left: i * step() }); });
      dotsBox.append(b);
      return b;
    });
  }

  const update = () => {
    prev.disabled = track.scrollLeft <= 4;
    next.disabled = !dotsBox && atEnd();
    dots.forEach((d, i) => d.classList.toggle("on", i === Math.min(index(), dots.length - 1)));
  };
  const move = (dir) => {
    if (dir > 0 && dotsBox && atEnd()) track.scrollTo({ left: 0 }); // dotted carousels wrap around
    else track.scrollBy({ left: dir * step() * perClick });
  };

  // ---- autoplay (pauses on hover, stops for good after the visitor interacts)
  let timer = null, stopped = false, hovering = false;
  const stopAuto = () => { stopped = true; clearInterval(timer); timer = null; };
  const startAuto = () => { if (autoMs && !reduceMotion && !stopped && !hovering && !timer) timer = setInterval(() => move(1), autoMs); };
  const pauseAuto = () => { clearInterval(timer); timer = null; };

  prev.addEventListener("click", () => { stopAuto(); move(-1); });
  next.addEventListener("click", () => { stopAuto(); move(1); });
  track.addEventListener("scroll", () => requestAnimationFrame(update), { passive: true });
  window.addEventListener("resize", update);
  track.tabIndex = 0;
  track.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight") { stopAuto(); move(1); }
    if (e.key === "ArrowLeft") { stopAuto(); move(-1); }
  });

  // ---- mouse drag (touch scrolling is already native)
  let down = false, startX = 0, startLeft = 0, dragged = false;
  track.addEventListener("pointerdown", (e) => {
    if (e.pointerType !== "mouse" || e.button !== 0) return;
    down = true; dragged = false; startX = e.clientX; startLeft = track.scrollLeft;
  });
  window.addEventListener("pointermove", (e) => {
    if (!down) return;
    const dx = e.clientX - startX;
    if (Math.abs(dx) > 5 && !dragged) { dragged = true; stopAuto(); track.style.scrollSnapType = "none"; track.style.scrollBehavior = "auto"; }
    if (dragged) track.scrollLeft = startLeft - dx;
  });
  window.addEventListener("pointerup", () => {
    if (!down) return;
    down = false;
    track.style.scrollSnapType = ""; track.style.scrollBehavior = "";
    if (dragged) track.scrollTo({ left: Math.round(track.scrollLeft / step()) * step() });
  });
  track.addEventListener("click", (e) => { if (dragged) { e.preventDefault(); e.stopPropagation(); dragged = false; } }, true);

  if (autoMs) {
    root.addEventListener("mouseenter", () => { hovering = true; pauseAuto(); });
    root.addEventListener("mouseleave", () => { hovering = false; startAuto(); });
    root.addEventListener("focusin", stopAuto);
    root.addEventListener("touchstart", stopAuto, { passive: true });
    new IntersectionObserver(([e]) => (e.isIntersecting ? startAuto() : pauseAuto()), { threshold: 0.5 }).observe(root);
  }
  update();
  return { update };
}
