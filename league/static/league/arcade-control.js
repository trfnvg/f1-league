(() => {
  "use strict";

  const form = document.querySelector(".lab-stage-picker");
  const select = form?.querySelector("[name=event]");
  if (!select || typeof form.requestSubmit !== "function") return;

  // This is the read-only GET picker, never the competition publishing form.
  select.addEventListener("change", () => {
    if (!select.value || !select.checkValidity()) return;
    form.setAttribute("aria-busy", "true");
    form.requestSubmit();
  });
  form.classList.add("is-auto");
  form.querySelector("button[type=submit]")?.setAttribute("hidden", "");
  window.addEventListener("pageshow", () => {
    form.removeAttribute("aria-busy");
    // Back/forward caches must not restore a different select value over the
    // server-rendered stage whose publishing form is shown below it.
    const selected = select.querySelector("option[selected]");
    if (selected) select.value = selected.value;
  });
})();
