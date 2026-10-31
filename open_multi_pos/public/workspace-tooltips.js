"use strict";
(() => {
  const tip = document.createElement("div");
  tip.id = "workspace-tooltip";
  tip.className = "workspace-tooltip";
  tip.setAttribute("role", "tooltip");
  tip.hidden = true;
  document.body.append(tip);
  let owner = null,
    timer;
  function hide() {
    clearTimeout(timer);
    if (owner) {
      const ids = (owner.getAttribute("aria-describedby") || "")
        .split(/\s+/)
        .filter((id) => id && id !== tip.id);
      if (ids.length) owner.setAttribute("aria-describedby", ids.join(" "));
      else owner.removeAttribute("aria-describedby");
    }
    owner = null;
    tip.hidden = true;
  }
  function show(node) {
    if (!node || node.disabled) return;
    clearTimeout(timer);
    if (owner === node) return;
    hide();
    owner = node;
    tip.textContent = window.OMPWorkspace.t(node.dataset.tooltip);
    const ids = node.getAttribute("aria-describedby");
    node.setAttribute(
      "aria-describedby",
      [ids, tip.id].filter(Boolean).join(" "),
    );
    tip.hidden = false;
    const rect = node.getBoundingClientRect();
    const left = Math.max(
      8,
      Math.min(rect.left, innerWidth - tip.offsetWidth - 8),
    );
    const top =
      rect.bottom + tip.offsetHeight + 8 <= innerHeight
        ? rect.bottom + 4
        : Math.max(8, rect.top - tip.offsetHeight - 4);
    tip.style.left = left + "px";
    tip.style.top = top + "px";
  }
  const leave = () => {
    timer = setTimeout(hide, 150);
  };
  document.addEventListener("focusin", (event) => {
    const node = event.target.closest("[data-tooltip]");
    if (node) show(node);
    else hide();
  });
  document.addEventListener("focusout", hide);
  document.addEventListener("pointerover", (event) => {
    if (tip.contains(event.target)) clearTimeout(timer);
    else show(event.target.closest("[data-tooltip]"));
  });
  document.addEventListener("pointerout", (event) => {
    if (owner?.contains(event.target) || tip.contains(event.target)) leave();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hide();
  });
  document.addEventListener("click", hide);
  document.addEventListener("scroll", hide, true);
  window.addEventListener("resize", hide);
})();
