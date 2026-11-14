(() => {
  "use strict";

  const picker = document.querySelector(".lab-stage-picker");
  const select = picker?.querySelector("[name=event]");
  const content = document.querySelector("#lab-stage-content");
  const status = document.querySelector("#lab-stage-status");
  if (!select || !content || !window.fetch) return;
  let controller;
  let loading = false;
  let saving = false;
  let pendingNavigation;
  let displayedEvent = select.value;

  function enhanceEditor() {
    const form = content.querySelector(".lab-competition-form");
    if (!form) return;
    const game = form.querySelector("#arcade-game-select");
    const retry = form.querySelector('[value="select"]');
    const publish = form.querySelector('[value="publish"]');
    const note = form.querySelector(".lab-save-status");
    retry.hidden = true;
    if (!game.disabled) note.textContent = "Выбор игры сохраняется автоматически. Запуск — отдельной кнопкой.";
    const publishBlocked = publish.disabled;
    let dirty = false;
    async function save() {
      if (saving || loading || !game.value || game.disabled) return;
      dirty = true;
      saving = true;
      // Capture values before disabling controls. Never publish via autosave.
      const data = new FormData(form);
      data.set("action", "select");
      game.disabled = true;
      select.disabled = true;
      publish.disabled = true;
      retry.hidden = true;
      form.setAttribute("aria-busy", "true");
      note.textContent = "Сохраняем выбор…";
      const timeout = new AbortController();
      const timer = setTimeout(() => timeout.abort(), 15000);
      try {
        // Controls named "action" shadow form.action with a RadioNodeList.
        // Read the HTML attribute so autosave always reaches the real endpoint.
        const response = await fetch(form.getAttribute("action") || location.href, {
          method: "POST", body: data, credentials: "same-origin",
          signal: timeout.signal,
          headers: {"X-Requested-With": "XMLHttpRequest"},
        });
        if (response.status === 401 || (response.redirected && new URL(response.url).pathname === "/accounts/login/")) {
          throw new Error("Нужно войти в аккаунт заново, затем повторить сохранение.");
        }
        if (response.status === 403) throw new Error("Сервер отклонил запрос: проверь права администратора и обнови страницу для проверки безопасности.");
        if (response.status === 404) throw new Error("Адрес сохранения не найден (HTTP 404). Обнови страницу.");
        if (response.status >= 500) throw new Error(`Ошибка сервера (HTTP ${response.status}). Попробуй чуть позже.`);
        if (!response.headers.get("Content-Type")?.includes("application/json")) throw new Error(`Сервер вернул неожиданный ответ (HTTP ${response.status}). Обнови страницу.`);
        const result = await response.json();
        if (!response.ok || !result.ok) throw new Error(result.message || "Не удалось сохранить выбор.");
        dirty = false;
        note.textContent = "Сохранено. Соревнование ещё не запущено.";
        // Refresh the plan list and heading, not the focused editor or other forms.
        try {
          const doc = await readStage(stageURL(displayedEvent));
          updateSummary(doc);
          const plans = doc.querySelector(".lab-season-plans");
          const oldPlans = content.querySelector(".lab-season-plans");
          if (plans) {
            if (oldPlans) { plans.open = oldPlans.open; oldPlans.replaceWith(plans); }
            else content.append(plans);
          }
        } catch (_) { /* A failed read must not report lost data after a successful POST. */ }
      } catch (error) {
        note.textContent = `Не удалось подтвердить сохранение. ${error.name === "AbortError" ? "Сервер долго не отвечает." : error.message} Повтори сохранение.`;
        retry.textContent = "Повторить сохранение";
        retry.hidden = false;
      } finally {
        clearTimeout(timer);
        saving = false;
        game.disabled = false;
        select.disabled = false;
        publish.disabled = dirty || publishBlocked;
        form.removeAttribute("aria-busy");
        if (pendingNavigation) {
          const url = pendingNavigation;
          pendingNavigation = null;
          loadStage(url, false);
        }
      }
    }
    game.addEventListener("change", save);
    retry.addEventListener("click", (event) => { event.preventDefault(); save(); });
    form.addEventListener("submit", (event) => {
      if (saving || loading || (dirty && event.submitter?.value !== "close")) event.preventDefault();
    });
  }

  function stageURL(id) {
    const url = new URL(picker.action);
    url.search = new URLSearchParams({season: picker.elements.season.value, event: id});
    return url;
  }
  async function readStage(url, signal) {
    const timeout = new AbortController();
    const abort = () => timeout.abort();
    signal?.addEventListener("abort", abort, {once: true});
    if (signal?.aborted) abort();
    const timer = setTimeout(abort, 15000);
    try {
      const response = await fetch(url, {credentials: "same-origin", signal: timeout.signal, cache: "no-store"});
      if (!response.ok || response.redirected) throw new Error("Не удалось загрузить этап. Проверь подключение и вход в аккаунт.");
      const doc = new DOMParser().parseFromString(await response.text(), "text/html");
      if (!doc.querySelector("#lab-stage-content")) throw new Error("Ответ сервера не содержит настроек этапа.");
      return doc;
    } catch (error) {
      if (error.name === "AbortError" && !signal?.aborted) throw new Error("Сервер долго не отвечает. Выбери этап ещё раз.");
      throw error;
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
    }
  }
  function updateSummary(doc) {
    const current = document.querySelector("#lab-competition > summary");
    const next = doc.querySelector("#lab-competition > summary");
    if (current && next) current.replaceChildren(...next.childNodes);
  }
  async function loadStage(url, historyChange = true) {
    if (saving) {
      if (!historyChange) pendingNavigation = url;
      return;
    }
    controller?.abort();
    const request = new AbortController();
    controller = request;
    loading = true;
    content.inert = true;
    content.setAttribute("aria-busy", "true");
    status.textContent = "Загружаем настройки этапа…";
    try {
      const doc = await readStage(url, request.signal);
      if (request.signal.aborted) return;
      const next = doc.querySelector("#lab-stage-content");
      content.replaceChildren(...next.childNodes);
      updateSummary(doc);
      displayedEvent = doc.querySelector("#arcade-event-select").value;
      select.value = displayedEvent;
      const libraryEvent = document.querySelector('[name="library_event"]');
      if (libraryEvent) libraryEvent.value = displayedEvent;
      if (historyChange) history.pushState(null, "", url);
      enhanceEditor();
      status.textContent = "";
    } catch (error) {
      if (request.signal.aborted) return;
      select.value = displayedEvent;
      if (!historyChange) history.replaceState(null, "", stageURL(displayedEvent));
      status.textContent = error.message;
    } finally {
      if (controller === request) {
        loading = false;
        content.inert = false;
        content.removeAttribute("aria-busy");
      }
    }
  }
  select.addEventListener("change", () => { if (select.value) loadStage(stageURL(select.value)); });
  picker.addEventListener("submit", (event) => { event.preventDefault(); loadStage(stageURL(select.value)); });
  content.addEventListener("click", (event) => {
    const link = event.target.closest(".lab-plan-row");
    if (!link || event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    loadStage(new URL(link.href));
  });
  window.addEventListener("popstate", () => loadStage(new URL(location.href), false));
  picker.classList.add("is-auto");
  picker.querySelector("button[type=submit]").hidden = true;
  enhanceEditor();
})();
