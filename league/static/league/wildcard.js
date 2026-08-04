(function () {
  const root = document.querySelector("[data-wildcard-root]");
  if (!root) return;

  const wait = (milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));

  async function postForm(form, submitter) {
    const data = new FormData(form);
    if (submitter && submitter.name) data.set(submitter.name, submitter.value);

    const response = await fetch(form.action, {
      method: "POST",
      body: data,
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    let payload;
    try {
      payload = await response.json();
    } catch (_error) {
      payload = { ok: false, error: "Не удалось получить ответ сервера." };
    }
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "Не удалось сохранить выбор.");
    }
    return payload;
  }

  const drawForm = root.querySelector("[data-wildcard-draw-form]");
  if (drawForm) {
    drawForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const picked = event.submitter;
      if (!picked || picked.classList.contains("is-picked")) return;

      const cards = Array.from(drawForm.querySelectorAll(".wildcard-card"));
      const status = drawForm.querySelector("[data-wildcard-status]");
      drawForm.setAttribute("aria-busy", "true");
      cards.forEach((card) => { card.disabled = true; });
      picked.classList.add("is-picked");
      if (status) status.textContent = "Карта поднимается…";

      window.setTimeout(() => {
        cards.forEach((card) => {
          if (card !== picked) card.classList.add("is-dismissed");
        });
      }, 150);

      try {
        const [payload] = await Promise.all([postForm(drawForm, picked), wait(430)]);
        const question = picked.querySelector("[data-wildcard-question]");
        const points = picked.querySelector("[data-wildcard-points]");
        const cardOptionA = picked.querySelector('[data-wildcard-card-option="a"]');
        const cardOptionB = picked.querySelector('[data-wildcard-card-option="b"]');
        if (question) question.textContent = payload.question;
        if (points) points.textContent = `${payload.points} PTS`;
        if (cardOptionA) cardOptionA.textContent = payload.option_a;
        if (cardOptionB) cardOptionB.textContent = payload.option_b;

        if (status) status.textContent = "Твоя личная карта";
        picked.classList.add("is-revealed");

        const answerPanel = root.querySelector("[data-wildcard-answer-panel]");
        if (answerPanel) {
          const answerA = answerPanel.querySelector('[data-option-label="a"]');
          const answerB = answerPanel.querySelector('[data-option-label="b"]');
          if (answerA) answerA.textContent = payload.option_a;
          if (answerB) answerB.textContent = payload.option_b;
          await wait(730);
          answerPanel.hidden = false;
          window.requestAnimationFrame(() => answerPanel.classList.add("is-visible"));
        }
      } catch (error) {
        drawForm.removeAttribute("aria-busy");
        cards.forEach((card) => {
          card.disabled = false;
          card.classList.remove("is-picked", "is-dismissed", "is-revealed");
        });
        if (status) status.textContent = error.message;
      }
    });
  }

  root.querySelectorAll("[data-wildcard-answer-form]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const selectedButton = event.submitter;
      if (!selectedButton) return;

      const buttons = Array.from(form.querySelectorAll(".wildcard-option"));
      const canEdit = buttons.some((button) => !button.disabled);
      if (!canEdit) return;
      const status = form.querySelector("[data-wildcard-status]");
      form.setAttribute("aria-busy", "true");
      buttons.forEach((button) => { button.disabled = true; });
      if (status) status.textContent = "Сохраняем выбор…";

      try {
        const payload = await postForm(form, selectedButton);
        buttons.forEach((button) => {
          button.classList.toggle("is-selected", button.value === payload.selected_option);
          button.disabled = false;
        });
        form.dataset.selected = payload.selected_option;
        if (status) status.textContent = `Сохранено: ${payload.selected_answer}. Можно изменить до дедлайна.`;
      } catch (error) {
        buttons.forEach((button) => { button.disabled = false; });
        if (status) status.textContent = error.message;
      } finally {
        form.removeAttribute("aria-busy");
      }
    });
  });
})();
