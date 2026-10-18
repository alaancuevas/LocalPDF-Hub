// Movement that CSS cannot do on its own: sliding rows and the sidebar bar to
// their new place after a redraw (FLIP), and the fade between tools.
// Every animation is named "lpdf-*" and none runs when the system asks for
// reduced motion. The CSP forbids inline styles: animate with
// element.animate() or element.style, never setAttribute("style") or cssText.

const EASE_OUT = "cubic-bezier(0.2, 0, 0, 1)";
const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");

export function motionAllowed() {
  return !reduced.matches;
}

/** Positions to compare after a redraw, keyed by any object that survives it. */
export function measure(items) {
  const boxes = new Map();
  for (const [key, node] of items) {
    if (node?.isConnected) boxes.set(key, node.getBoundingClientRect());
  }
  return boxes;
}

/** Slides each node from where its key was measured to where it is now. */
export function slide(boxes, items, duration = 200) {
  if (!motionAllowed()) return;
  for (const [key, node] of items) {
    const before = boxes.get(key);
    if (!before || !node?.isConnected) continue;
    const after = node.getBoundingClientRect();
    const dy = before.top - after.top;
    if (!dy) continue;
    node.animate([{ transform: `translateY(${dy}px)` }, { transform: "none" }], {
      duration,
      easing: EASE_OUT,
      id: "lpdf-slide",
    });
  }
}

export function fadeIn(node, duration = 150) {
  if (!motionAllowed() || !node) return;
  node.animate([{ opacity: 0 }, { opacity: 1 }], { duration, easing: EASE_OUT, id: "lpdf-fade" });
}
