(() => {
  const screen = document.getElementById("minesweeper-game-screen");
  if (!screen) return;

  const machine = document.getElementById("minesweeper-machine");
  const boardNode = document.getElementById("minesweeper-board");
  const overlay = document.getElementById("minesweeper-overlay");
  const overlayTitle = document.getElementById("minesweeper-overlay-title");
  const overlayCopy = document.getElementById("minesweeper-overlay-copy");
  const startButton = document.getElementById("minesweeper-start");
  const statusNode = document.getElementById("minesweeper-status");
  const clockNode = document.getElementById("minesweeper-clock");
  const minesLeftNode = document.getElementById("minesweeper-mines-left");
  const attemptsNode = document.getElementById("minesweeper-attempts");
  const flagModeButton = document.getElementById("minesweeper-flag-mode");
  const fullScreenButton = document.getElementById("minesweeper-fullscreen");
  const leaderboardNode = document.getElementById("minesweeper-leaderboard-list");
  const totalAttemptsNode = document.getElementById("minesweeper-total-attempts");
  const csrfToken = document.querySelector("#minesweeper-csrf-form [name=csrfmiddlewaretoken]")?.value || "";
  const rows = 16;
  const columns = 30;
  const mineTotal = 99;
  const mineHazards = ["oil", "wheel", "carbon"];
  const mineHazardLabels = {
    oil: "масляное пятно",
    wheel: "оторвавшееся колесо",
    carbon: "обломки карбона",
  };
  const cellTotal = rows * columns;
  const cells = [];
  let field = null;
  let mode = "ready";
  let runId = null;
  let startedAt = null;
  let timerId = null;
  let flagMode = false;
  let revealedSafeCount = 0;
  let flagCount = 0;
  let attempts = Number(screen.dataset.attempts) || 0;

  const formatTime = (milliseconds) => {
    const totalSeconds = Math.floor(Math.max(0, milliseconds) / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  };

  const currentElapsed = () => startedAt === null ? 0 : performance.now() - startedAt;

  function updateClock() {
    clockNode.textContent = formatTime(currentElapsed());
  }

  function setFlagMode(enabled) {
    flagMode = Boolean(enabled);
    flagModeButton?.setAttribute("aria-pressed", flagMode ? "true" : "false");
    boardNode.classList.toggle("is-flag-mode", flagMode);
  }

  function startClock() {
    if (startedAt !== null) return;
    startedAt = performance.now();
    updateClock();
    timerId = window.setInterval(updateClock, 1000);
  }

  function shuffle(list) {
    for (let index = list.length - 1; index > 0; index -= 1) {
      const other = Math.floor(Math.random() * (index + 1));
      [list[index], list[other]] = [list[other], list[index]];
    }
    return list;
  }

  function neighborIndexes(index) {
    const row = Math.floor(index / columns);
    const column = index % columns;
    const neighbors = [];
    for (let rowOffset = -1; rowOffset <= 1; rowOffset += 1) {
      for (let columnOffset = -1; columnOffset <= 1; columnOffset += 1) {
        if (rowOffset === 0 && columnOffset === 0) continue;
        const nextRow = row + rowOffset;
        const nextColumn = column + columnOffset;
        if (nextRow >= 0 && nextRow < rows && nextColumn >= 0 && nextColumn < columns) {
          neighbors.push(nextRow * columns + nextColumn);
        }
      }
    }
    return neighbors;
  }

  function generateField(firstIndex) {
    const safe = new Set([firstIndex, ...neighborIndexes(firstIndex)]);
    const possibleMines = shuffle(Array.from({ length: cellTotal }, (_, index) => index).filter((index) => !safe.has(index)));
    const mineIndexes = new Set(possibleMines.slice(0, mineTotal));
    const shuffledHazards = shuffle(Array.from({ length: mineTotal }, (_, index) => mineHazards[index % mineHazards.length]));
    const hazardByIndex = new Map(Array.from(mineIndexes, (index, mineIndex) => [index, shuffledHazards[mineIndex]]));
    field = Array.from({ length: cellTotal }, (_, index) => ({
      mine: mineIndexes.has(index),
      hazard: hazardByIndex.get(index) || "",
      opened: false,
      flagged: false,
      count: 0,
    }));
    field.forEach((cell, index) => {
      if (!cell.mine) cell.count = neighborIndexes(index).filter((neighbor) => field[neighbor].mine).length;
    });
  }

  function setCellAccessibleName(button, cell, index, revealMines = false) {
    const row = Math.floor(index / columns) + 1;
    const column = index % columns + 1;
    if (!cell) {
      button.setAttribute("aria-label", `Закрытая клетка, ряд ${row}, столбец ${column}`);
    } else if (revealMines && cell.mine) {
      button.setAttribute("aria-label", `Мина — ${mineHazardLabels[cell.hazard]}, ряд ${row}, столбец ${column}`);
    } else if (cell.flagged) {
      button.setAttribute("aria-label", `Флаг, ряд ${row}, столбец ${column}`);
    } else if (cell.opened) {
      if (cell.mine) button.setAttribute("aria-label", `Мина, ряд ${row}, столбец ${column}`);
      else button.setAttribute("aria-label", cell.count ? `${cell.count} рядом, ряд ${row}, столбец ${column}` : `Пусто, ряд ${row}, столбец ${column}`);
    } else {
      button.setAttribute("aria-label", `Закрытая клетка, ряд ${row}, столбец ${column}`);
    }
  }

  function paint() {
    boardNode.classList.toggle("is-active", mode === "playing");
    cells.forEach((button, index) => {
      button.className = "minesweeper-cell";
      button.textContent = "";
      button.removeAttribute("data-number");
      button.disabled = mode !== "playing";
      const cell = field?.[index];
      if (!cell) {
        setCellAccessibleName(button, null, index);
        return;
      }
      const showLostMine = mode === "lost" && cell.mine;

      if (cell.opened) {
        button.classList.add("is-open");
        if (cell.mine) {
          button.classList.add(mode === "lost" && index === lastExplodedIndex ? "is-exploded" : "is-mine-revealed");
          button.classList.add(`hazard-${cell.hazard}`);
        } else if (cell.count > 0) {
          button.textContent = String(cell.count);
          button.classList.add(`number-${cell.count}`);
          button.dataset.number = String(cell.count);
        }
      } else if (showLostMine) {
        button.classList.add("is-open", "is-mine-revealed", `hazard-${cell.hazard}`);
      } else if (cell.flagged) {
        button.classList.add("is-flagged");
        if (mode === "lost" && !cell.mine) button.classList.add("is-wrong-flag");
      }
      setCellAccessibleName(button, cell, index, mode === "lost");
    });
    minesLeftNode.textContent = String(Math.max(0, mineTotal - flagCount)).padStart(3, "0");
  }

  function buildBoard() {
    if (cells.length) return;
    const fragment = document.createDocumentFragment();
    for (let index = 0; index < cellTotal; index += 1) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "minesweeper-cell";
      button.setAttribute("role", "gridcell");
      button.tabIndex = index === 0 ? 0 : -1;
      button.dataset.index = String(index);
      button.setAttribute("aria-label", `Закрытая клетка, ряд ${Math.floor(index / columns) + 1}, столбец ${index % columns + 1}`);
      button.addEventListener("click", () => {
        if (mode !== "playing") return;
        if (flagMode) toggleFlag(index);
        else reveal(index);
      });
      button.addEventListener("contextmenu", (event) => {
        event.preventDefault();
        if (mode === "playing") toggleFlag(index);
      });
      fragment.appendChild(button);
      cells.push(button);
    }
    boardNode.appendChild(fragment);
  }

  async function postJSON(url, payload = {}) {
    const response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "Не удалось сохранить результат.");
    return data;
  }

  function applyStats(data) {
    if (!data) return;
    if (Number.isFinite(data.attempts)) {
      attempts = data.attempts;
      attemptsNode.textContent = String(attempts).padStart(2, "0");
    }
    if (Number.isFinite(data.total_attempts)) totalAttemptsNode.textContent = String(data.total_attempts);
    if (Array.isArray(data.records)) renderLeaderboard(data.records);
  }

  function renderLeaderboard(records) {
    if (!leaderboardNode) return;
    leaderboardNode.replaceChildren();
    if (!records.length) {
      const empty = document.createElement("li");
      empty.className = "minesweeper-board-empty";
      empty.textContent = "Поле ещё никто не прошёл — первым рекордом можешь стать ты.";
      leaderboardNode.appendChild(empty);
      return;
    }
    records.forEach((record) => {
      const item = document.createElement("li");
      if (record.is_current_user) item.classList.add("is-current-user");
      const rank = document.createElement("span");
      rank.className = "minesweeper-rank";
      rank.textContent = String(record.rank).padStart(2, "0");
      const username = document.createElement("strong");
      username.className = "minesweeper-driver-name";
      username.textContent = record.username;
      const time = document.createElement("span");
      time.className = "minesweeper-record-time";
      time.textContent = formatTime(record.best_time_ms);
      const meta = document.createElement("span");
      meta.className = "minesweeper-record-meta";
      meta.textContent = `${record.wins} прохожд. · ${record.attempts} попыток`;
      item.append(rank, username, time, meta);
      leaderboardNode.appendChild(item);
    });
  }

  async function refreshLeaderboard() {
    try {
      const response = await fetch(screen.dataset.leaderboardUrl, {
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      if (response.ok) applyStats(await response.json());
    } catch (error) {
      // Keep the last rendered board available during a temporary network issue.
    }
  }

  async function finishAttempt(completed) {
    if (!runId) return;
    if (timerId) window.clearInterval(timerId);
    timerId = null;
    const elapsed = Math.round(currentElapsed());
    const payload = { attempt_id: runId, completed };
    if (completed) payload.elapsed_ms = elapsed;
    try {
      const data = await postJSON(screen.dataset.finishUrl, payload);
      applyStats(data);
    } catch (error) {
      statusNode.textContent = `${error.message} Результат отображён локально.`;
    }
    runId = null;
  }

  let lastExplodedIndex = -1;

  function lose(index) {
    if (mode !== "playing") return;
    startClock();
    lastExplodedIndex = index;
    field[index].opened = true;
    mode = "lost";
    paint();
    statusNode.textContent = "Мина! Попытка завершена — поле откроется заново.";
    overlayTitle.textContent = "Жёлтые флаги!";
    overlayCopy.textContent = "Попытка завершена. На поле раскрыты типы мин: масло, колесо и обломки карбона. Запускай новый заезд.";
    startButton.innerHTML = "Ещё попытка <span aria-hidden=\"true\">↻</span>";
    overlay.hidden = false;
    finishAttempt(false);
  }

  function win() {
    if (mode !== "playing") return;
    startClock();
    field.forEach((cell) => { if (cell.mine) cell.flagged = true; });
    flagCount = mineTotal;
    mode = "won";
    paint();
    statusNode.textContent = "Поле чистое — результат сохранён в рейтинге недели.";
    overlayTitle.textContent = "Чистый круг!";
    overlayCopy.textContent = `Поле пройдено за ${formatTime(currentElapsed())}. Попробуй побить это время в следующей попытке.`;
    startButton.innerHTML = "Новый заезд <span aria-hidden=\"true\">↻</span>";
    overlay.hidden = false;
    finishAttempt(true);
  }

  function revealFlood(startIndex) {
    const queue = [startIndex];
    const seen = new Set();
    while (queue.length) {
      const index = queue.shift();
      if (seen.has(index)) continue;
      seen.add(index);
      const cell = field[index];
      if (!cell || cell.opened || cell.flagged || cell.mine) continue;
      cell.opened = true;
      revealedSafeCount += 1;
      if (cell.count === 0) queue.push(...neighborIndexes(index));
    }
  }

  function reveal(index) {
    if (mode !== "playing") return;
    if (!field) generateField(index);
    startClock();
    const cell = field[index];
    if (cell.flagged || cell.opened) return;
    if (cell.mine) {
      lose(index);
      return;
    }
    revealFlood(index);
    paint();
    if (revealedSafeCount >= cellTotal - mineTotal) win();
  }

  function toggleFlag(index) {
    if (mode !== "playing") return;
    if (!field) generateField(index);
    const cell = field[index];
    if (cell.opened) return;
    if (cell.flagged) {
      cell.flagged = false;
      flagCount -= 1;
    } else {
      if (flagCount >= mineTotal) return;
      cell.flagged = true;
      flagCount += 1;
    }
    paint();
  }

  async function startGame() {
    if (mode === "starting") return;
    mode = "starting";
    startButton.disabled = true;
    statusNode.textContent = "Готовим поле…";
    try {
      const data = await postJSON(screen.dataset.startUrl);
      runId = data.attempt_id;
      applyStats(data);
      mode = "playing";
      field = null;
      revealedSafeCount = 0;
      flagCount = 0;
      lastExplodedIndex = -1;
      startedAt = null;
      if (timerId) window.clearInterval(timerId);
      timerId = null;
      clockNode.textContent = "00:00";
      statusNode.textContent = "Новая карта готова. Открой первую клетку.";
      overlay.hidden = true;
      setFlagMode(false);
      startButton.disabled = false;
      paint();
      cells[0]?.focus({ preventScroll: true });
    } catch (error) {
      mode = "ready";
      statusNode.textContent = error.message;
      overlayCopy.textContent = error.message;
      startButton.disabled = false;
    }
  }

  function handleGridKeydown(event) {
    const current = document.activeElement;
    if (!current?.classList.contains("minesweeper-cell")) return;
    const index = Number(current.dataset.index);
    let next = index;
    if (event.key === "ArrowLeft") next = index % columns === 0 ? index : index - 1;
    else if (event.key === "ArrowRight") next = index % columns === columns - 1 ? index : index + 1;
    else if (event.key === "ArrowUp") next = index < columns ? index : index - columns;
    else if (event.key === "ArrowDown") next = index + columns >= cellTotal ? index : index + columns;
    else if (event.key.toLowerCase() === "f") {
      event.preventDefault();
      toggleFlag(index);
      return;
    } else if (event.code === "Space") {
      event.preventDefault();
      flagMode ? toggleFlag(index) : reveal(index);
      return;
    } else {
      return;
    }
    event.preventDefault();
    cells[next]?.focus();
  }

  function syncFullscreen() {
    const isFullscreen = document.fullscreenElement === machine || machine.classList.contains("is-fullscreen");
    machine.classList.toggle("is-fullscreen", isFullscreen);
    fullScreenButton.setAttribute("aria-pressed", isFullscreen ? "true" : "false");
    fullScreenButton.setAttribute("aria-label", isFullscreen ? "Выйти из полного экрана" : "На весь экран");
  }

  function toggleFullscreen() {
    if (document.fullscreenElement === machine) {
      document.exitFullscreen?.();
    } else if (machine.requestFullscreen) {
      machine.requestFullscreen().catch(() => machine.classList.toggle("is-fullscreen"));
    } else {
      machine.classList.toggle("is-fullscreen");
    }
    window.setTimeout(syncFullscreen, 50);
  }

  buildBoard();
  paint();
  attemptsNode.textContent = String(attempts).padStart(2, "0");
  document.querySelectorAll(".minesweeper-record-time[data-time-ms]").forEach((node) => {
    const time = Number(node.dataset.timeMs);
    node.textContent = Number.isFinite(time) ? formatTime(time) : "—";
  });
  startButton?.addEventListener("click", startGame);
  flagModeButton?.addEventListener("click", () => setFlagMode(!flagMode));
  fullScreenButton?.addEventListener("click", toggleFullscreen);
  document.addEventListener("fullscreenchange", syncFullscreen);
  document.addEventListener("keydown", (event) => {
    if (event.code === "Space" && mode !== "playing" && !overlay.hidden && !event.target.closest("button, a, input, textarea, select")) {
      event.preventDefault();
      startGame();
    }
  });
  boardNode.addEventListener("keydown", handleGridKeydown);
  if (screen.dataset.authenticated === "true") refreshLeaderboard();
})();
