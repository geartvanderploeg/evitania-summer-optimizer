// Top-left menu: toggle on button click, close on outside click,
// highlight the link matching the current page (using browser-resolved URLs).

(function () {
  function normalize(p) {
    return p.replace(/\/+$/, "") || "/";
  }

  function init() {
    const button = document.querySelector(".menu-button");
    const panel = document.querySelector(".menu-panel");
    if (!button || !panel) return;

    button.addEventListener("click", (e) => {
      e.stopPropagation();
      panel.classList.toggle("open");
      button.setAttribute("aria-expanded", panel.classList.contains("open"));
    });

    document.addEventListener("click", (e) => {
      if (!panel.contains(e.target) && e.target !== button) {
        panel.classList.remove("open");
        button.setAttribute("aria-expanded", "false");
      }
    });

    // Active link by absolute resolved path.
    const here = normalize(window.location.pathname);
    panel.querySelectorAll("a").forEach((a) => {
      const linkPath = normalize(new URL(a.href).pathname);
      if (linkPath === here) a.classList.add("active");
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
