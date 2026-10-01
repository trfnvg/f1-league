(() => {
  "use strict";

  // The admin preview is intentionally client-only: it has no live endpoint or form submission.

  const panel = document.getElementById("arcade-wheel-test");
  const disc = document.getElementById("test-wheel-disc");
  const configNode = document.getElementById("test-wheel-config");
  const driverNode = document.getElementById("test-driver-config");
  if (!panel || !disc || !configNode || !driverNode) return;

  const sectors = JSON.parse(configNode.textContent || "[]");
  const drivers = JSON.parse(driverNode.textContent || "[]");
  const centerAngles = new Map();
  const gradientStops = [];
  const weightsTotal = sectors.reduce((sum, sector) => sum + Number(sector.weight || 0), 0);
  const outcomeSelect = document.getElementById("test-wheel-outcome");
  const spinButton = document.getElementById("test-wheel-spin");
  const applyButton = document.getElementById("test-wheel-apply");
  const resetButton = document.getElementById("test-wheel-reset");
  const status = document.getElementById("test-wheel-status");
  const prizeCard = document.getElementById("test-wheel-prize");
  const prizeKicker = document.getElementById("test-wheel-prize-kicker");
  const prizeTitle = document.getElementById("test-wheel-prize-title");
  const prizeDescription = document.getElementById("test-wheel-prize-description");
  const fieldsRoot = document.getElementById("test-wheel-fields");
  const summary = document.getElementById("test-wheel-outcome-summary");
  let selectedPrize = null;
  let isSpinning = false;

  let cumulativeAngle = 0;
  const wheelLabels = sectors.map((sector, index) => {
    const angle = weightsTotal ? Number(sector.weight) / weightsTotal * 360 : 0;
    centerAngles.set(sector.key, cumulativeAngle + angle / 2);
    gradientStops.push(`${sector.color} ${cumulativeAngle}deg ${Math.max(cumulativeAngle, cumulativeAngle + angle - .8)}deg`);
    if (angle > .8) gradientStops.push(`#101923 ${cumulativeAngle + angle - .8}deg ${cumulativeAngle + angle}deg`);
    cumulativeAngle += angle;

    const label = document.createElement("span");
    label.className = "arcade-wheel-label";
    label.dataset.prize = sector.key;
    label.textContent = String(index + 1).padStart(2, "0");
    label.setAttribute("aria-hidden", "true");
    label.style.setProperty("--label-angle", `${centerAngles.get(sector.key)}deg`);
    disc.append(label);
    return label;
  });
  disc.style.background = `conic-gradient(from 0deg, ${gradientStops.join(",")})`;

  function drawWeightedPrize() {
    let target = Math.random() * weightsTotal;
    for (const sector of sectors) {
      target -= Number(sector.weight || 0);
      if (target < 0) return sector;
    }
    return sectors[sectors.length - 1];
  }

  function rotationFor(prizeKey, turns = 0) {
    const center = centerAngles.get(prizeKey);
    return center === undefined ? 0 : turns * 360 + ((360 - center) % 360);
  }

  function addSelect(labelText, name, options) {
    const label = document.createElement("label");
    label.className = "arcade-wheel-demo-field";
    label.textContent = labelText;
    const select = document.createElement("select");
    select.name = name;
    select.required = true;
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Выбери вариант";
    placeholder.selected = true;
    select.append(placeholder);
    options.forEach(([value, text]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = text;
      select.append(option);
    });
    label.append(select);
    fieldsRoot.append(label);
    return select;
  }

  function renderActivationFields(sector) {
    fieldsRoot.replaceChildren();
    if (sector.key === "podium_edit") {
      addSelect("Какое место подиума изменить?", "slot", [
        ["p1", "Победитель · P1"],
        ["p2", "Второе место · P2"],
        ["p3", "Третье место · P3"],
      ]);
      addSelect("Новый пилот в прогнозе", "driver", drivers.map(([value, label]) => [value, label]));
    } else if (sector.key === "va_bank") {
      addSelect("Какой сохранённый прогноз поставить на кон?", "field", [
        ["p1", "Победитель гонки"], ["p2", "Пилот на P2"], ["p3", "Пилот на P3"],
        ["pole", "Обладатель поула"], ["fastest_lap", "Fastest Lap"],
        ["driver_of_day", "Driver of the Day"], ["safety_car_count", "Количество Safety Car"],
        ["dnf_count", "Количество DNF"], ["crazy_prediction", "Crazy Prediction"],
      ]);
    } else if (sector.key === "ruel_v_govne" || sector.key === "crazy_block") {
      const label = sector.key === "ruel_v_govne" ? "Кому назначить штраф −3?" : "Чей Crazy Prediction заблокировать?";
      addSelect(label, "target_user", [["demo_1", "Сэмпл Макс"], ["demo_2", "Пилот Папайя"], ["demo_3", "Демо Оскар"]]);
    }
  }

  function showPrize(sector) {
    selectedPrize = sector;
    prizeTitle.textContent = sector.title;
    prizeDescription.textContent = sector.description;
    prizeKicker.textContent = "РЕЗУЛЬТАТ ДЕМО-РОЗЫГРЫША";
    renderActivationFields(sector);
    prizeCard.hidden = false;
    prizeCard.classList.remove("is-applied");
    applyButton.hidden = false;
    applyButton.disabled = false;
    resetButton.hidden = true;
    summary.hidden = true;
    summary.textContent = "";
    outcomeSelect.disabled = true;
    status.textContent = `В демо выпало: ${sector.title}. Проверь экран активации ниже.`;
  }

  spinButton.addEventListener("click", () => {
    if (isSpinning) return;
    isSpinning = true;
    spinButton.disabled = true;
    disc.classList.add("is-spinning");
    status.textContent = "Колесо набирает скорость…";

    const requestedKey = outcomeSelect.value;
    const sector = requestedKey === "random"
      ? drawWeightedPrize()
      : sectors.find((item) => item.key === requestedKey);
    if (!sector) {
      isSpinning = false;
      spinButton.disabled = false;
      disc.classList.remove("is-spinning");
      status.textContent = "Не удалось выбрать демо-сектор. Попробуй ещё раз.";
      return;
    }

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const turns = reducedMotion ? 0 : 6;
    disc.style.transition = reducedMotion ? "none" : "";
    disc.style.transform = `rotate(${rotationFor(sector.key, turns)}deg)`;
    window.setTimeout(() => {
      wheelLabels.forEach((label) => label.classList.toggle("is-selected", label.dataset.prize === sector.key));
      panel.querySelectorAll(".arcade-wheel-rule[data-test-prize]").forEach((card) => {
        card.classList.toggle("is-selected", card.dataset.testPrize === sector.key);
      });
      disc.classList.remove("is-spinning");
      showPrize(sector);
      isSpinning = false;
    }, reducedMotion ? 80 : 5150);
  });

  applyButton.addEventListener("click", () => {
    if (!selectedPrize) return;
    const values = Object.fromEntries([...fieldsRoot.querySelectorAll("select")].map((select) => [select.name, select.value]));
    const missingField = [...fieldsRoot.querySelectorAll("select")].find((select) => !select.value);
    if (missingField) {
      missingField.focus();
      status.textContent = "Заполни параметры демо-бонуса, затем повтори симуляцию.";
      return;
    }

    const driverLabels = Object.fromEntries(drivers.map(([value, label]) => [value, label]));
    const outcomes = {
      pit_wall: "Победителю недели добавились бы +2 очка к результату этапа.",
      card_boost: "За верную личную карту победитель получил бы ещё +3 очка.",
      podium_edit: `В демо-прогнозе слот ${values.slot.toUpperCase()} изменён на ${driverLabels[values.driver] || values.driver}. Реальный прогноз не менялся.`,
      va_bank: `Прогноз «${fieldsRoot.querySelector('[name="field"] option:checked')?.textContent || values.field}» записан бы как Ва-банк: +4 за верный ответ или −1 за неверный после гонки.`,
      ruel_v_govne: `Для демо выбран игрок «${fieldsRoot.querySelector('[name="target_user"] option:checked')?.textContent || "участник"}»: после подсчёта с него снялись бы 3 очка.`,
      crazy_block: `Для демо выбран игрок «${fieldsRoot.querySelector('[name="target_user"] option:checked')?.textContent || "участник"}»: его Crazy Prediction дал бы 0 очков даже при совпадении.`,
    };
    summary.textContent = outcomes[selectedPrize.key] || "Бонус активирован в демо-режиме.";
    summary.hidden = false;
    prizeCard.classList.add("is-applied");
    prizeKicker.textContent = "ДЕМО-АКТИВАЦИЯ ЗАВЕРШЕНА";
    applyButton.hidden = true;
    resetButton.hidden = false;
    fieldsRoot.querySelectorAll("select").forEach((select) => { select.disabled = true; });
    status.textContent = "Готово — это только локальная демонстрация, на сервер ничего не отправлено.";
  });

  resetButton.addEventListener("click", () => {
    if (isSpinning) return;
    selectedPrize = null;
    outcomeSelect.disabled = false;
    spinButton.disabled = false;
    prizeCard.hidden = true;
    prizeCard.classList.remove("is-applied");
    fieldsRoot.replaceChildren();
    summary.hidden = true;
    summary.textContent = "";
    resetButton.hidden = true;
    disc.classList.remove("is-spinning");
    disc.style.transition = "none";
    disc.style.transform = "rotate(0deg)";
    disc.offsetWidth;
    disc.style.transition = "";
    wheelLabels.forEach((label) => label.classList.remove("is-selected"));
    panel.querySelectorAll(".arcade-wheel-rule[data-test-prize]").forEach((card) => card.classList.remove("is-selected"));
    status.textContent = "Нажми кнопку, чтобы начать демонстрацию.";
  });
})();
