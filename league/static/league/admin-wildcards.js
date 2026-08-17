(function () {
  "use strict";

  const fieldIds = ["id_wildcard_card_1", "id_wildcard_card_2", "id_wildcard_card_3"];

  function textElement(className, text) {
    const element = document.createElement("span");
    element.className = className;
    element.textContent = text;
    return element;
  }

  function renderPreview(select, preview) {
    const option = select.options[select.selectedIndex];
    preview.replaceChildren();

    if (!option || !option.value) {
      preview.classList.add("is-empty");
      preview.textContent = "После выбора здесь появятся вопрос и варианты ответа";
      return;
    }

    preview.classList.remove("is-empty");
    preview.append(
      textElement("wildcard-admin-preview__title", option.dataset.cardTitle || "Карта"),
      textElement("wildcard-admin-preview__question", option.dataset.cardQuestion || "")
    );

    const answers = document.createElement("div");
    answers.className = "wildcard-admin-preview__answers";
    [
      ["A", option.dataset.cardOptionA],
      ["B", option.dataset.cardOptionB],
      ["C", option.dataset.cardOptionC],
    ].forEach(([letter, answer]) => {
      if (answer) {
        answers.append(textElement("wildcard-admin-preview__answer", `${letter}: ${answer}`));
      }
    });
    preview.append(answers);
  }

  function setupPreview(select) {
    const preview = document.createElement("div");
    preview.className = "wildcard-admin-preview";
    select.insertAdjacentElement("afterend", preview);
    renderPreview(select, preview);
    select.addEventListener("change", () => renderPreview(select, preview));
  }

  document.addEventListener("DOMContentLoaded", () => {
    fieldIds.forEach((fieldId) => {
      const select = document.getElementById(fieldId);
      if (select) {
        setupPreview(select);
      }
    });
  });
})();
