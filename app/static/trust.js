(() => {
  "use strict";

  const list = document.getElementById("platform-list");
  const search = document.getElementById("guide-search");
  const empty = document.getElementById("empty-state");
  const cards = list ? Array.from(list.querySelectorAll(".platform-card")) : [];

  if (search && cards.length) {
    search.addEventListener("input", () => {
      const query = search.value.trim().toLocaleLowerCase();
      let visible = 0;

      cards.forEach((card) => {
        const matches = !query || card.textContent.toLocaleLowerCase().includes(query);
        card.hidden = !matches;
        if (matches) visible += 1;
      });

      if (empty) empty.classList.toggle("visible", visible === 0);
    });
  }

  document.querySelectorAll("[data-expand-all]").forEach((button) => {
    button.addEventListener("click", () => {
      cards.forEach((card) => {
        if (!card.hidden) card.open = true;
      });
    });
  });

  document.querySelectorAll("[data-collapse-all]").forEach((button) => {
    button.addEventListener("click", () => {
      cards.forEach((card) => { card.open = false; });
    });
  });

  async function copyText(value) {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(value);
      return;
    }

    const helper = document.createElement("textarea");
    helper.value = value;
    helper.setAttribute("readonly", "");
    helper.style.position = "fixed";
    helper.style.opacity = "0";
    helper.style.pointerEvents = "none";
    document.body.appendChild(helper);
    helper.select();
    const copied = document.execCommand("copy");
    helper.remove();

    if (!copied) throw new Error("Copy unavailable");
  }

  document.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-copy-target]");
    if (!button) return;

    const target = document.querySelector(button.getAttribute("data-copy-target"));
    const status = button.parentElement.querySelector(".copy-status");
    if (!target) return;

    const value = target.textContent.trim();
    const original = button.dataset.originalLabel || button.textContent.trim();
    button.dataset.originalLabel = original;

    try {
      await copyText(value);
      button.textContent = "کپی شد ✓";
      if (status) status.textContent = "متن با موفقیت کپی شد.";
    } catch (_) {
      button.textContent = "کپی نشد";
      if (status) status.textContent = "متن را انتخاب و به‌صورت دستی کپی کنید.";
    }

    window.setTimeout(() => {
      button.textContent = original;
      if (status) status.textContent = "";
    }, 2200);
  });
})();