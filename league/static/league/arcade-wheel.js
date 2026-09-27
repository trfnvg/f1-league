(() => {
  "use strict";

  const panel = document.getElementById("arcade-wheel-panel");
  const disc = document.getElementById("arcade-wheel-disc");
  const configNode = document.getElementById("arcade-wheel-config");
  if (!panel || !disc || !configNode) return;

  const sectors = JSON.parse(configNode.textContent || "[]");
  const csrfToken = document.querySelector("#arcade-csrf-form input[name=csrfmiddlewaretoken]")?.value || "";
  const status = document.getElementById("arcade-wheel-status");
  const feedback = document.getElementById("arcade-wheel-feedback");
  const spinButton = document.getElementById("arcade-wheel-spin");
  const activationForm = document.getElementById("arcade-wheel-activation");
  const weightsTotal = sectors.reduce((sum, sector) => sum + Number(sector.weight || 0), 0);
  const centers = new Map();
  let cumulative = 0;
  const gradientStops = [];

  sectors.forEach((sector, index) => {
    const span = weightsTotal ? Number(sector.weight) / weightsTotal * 360 : 0;
    const center = cumulative + span / 2;
    centers.set(sector.key, center);
    gradientStops.push(`${sector.color} ${cumulative}deg ${Math.max(cumulative, cumulative + span - .8)}deg`);
    if (span > .8) gradientStops.push(`#101923 ${cumulative + span - .8}deg ${cumulative + span}deg`);

    const label = document.createElement("span");
    label.className = "arcade-wheel-label";
    label.dataset.prize = sector.key;
    label.textContent = String(index + 1).padStart(2, "0");
    label.setAttribute("aria-hidden", "true");
    label.style.setProperty("--label-angle", `${center}deg`);
    disc.append(label);
    cumulative += span;
  });

  disc.style.background = `conic-gradient(from 0deg, ${gradientStops.join(",")})`;

  function rotationFor(prize, turns = 0) {
    const center = centers.get(prize);
    if (center === undefined) return 0;
    return turns * 360 + ((360 - center) % 360);
  }

  const currentPrize = panel.dataset.selectedPrize;
  if (currentPrize) {
    disc.style.transition = "none";
    disc.style.transform = `rotate(${rotationFor(currentPrize)}deg)`;
    const selectedLabel = disc.querySelector(`.arcade-wheel-label[data-prize="${CSS.escape(currentPrize)}"]`);
    selectedLabel?.classList.add("is-selected");
    panel.querySelector(`.arcade-wheel-rule[data-prize="${CSS.escape(currentPrize)}"]`)?.classList.add("is-selected");
  }

  async function submit(url, formData) {
    const response = await fetch(url, {
      method: "POST",
      body: formData,
      headers: {
        "X-CSRFToken": csrfToken,
        "X-Requested-With": "XMLHttpRequest",
      },
      credentials: "same-origin",
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "Не удалось сохранить результат.");
    return data;
  }

  spinButton?.addEventListener("click", async () => {
    spinButton.disabled = true;
    disc.classList.add("is-spinning");
    if (status) status.textContent = "Колесо набирает скорость…";
    const formData = new FormData();
    formData.set("event_id", panel.dataset.eventId);

    try {
      const data = await submit(panel.dataset.spinUrl, formData);
      const turns = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 6;
      disc.style.transition = turns ? "" : "none";
      disc.style.transform = `rotate(${rotationFor(data.prize, turns)}deg)`;
      const duration = turns ? 5200 : 20;
      window.setTimeout(() => window.location.reload(), duration + 150);
    } catch (error) {
      disc.classList.remove("is-spinning");
      spinButton.disabled = false;
      if (status) status.textContent = error.message;
    }
  });

  activationForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = activationForm.querySelector("button[type=submit]");
    if (button) button.disabled = true;
    if (feedback) feedback.textContent = "Сохраняю активацию…";
    const formData = new FormData(activationForm);

    try {
      await submit(panel.dataset.activateUrl, formData);
      window.location.reload();
    } catch (error) {
      if (button) button.disabled = false;
      if (feedback) feedback.textContent = error.message;
    }
  });
})();
