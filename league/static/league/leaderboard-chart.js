(function () {
  "use strict";

  const dataElement = document.getElementById("leaderboard-chart-data");
  const svg = document.getElementById("pointsChart");
  const canvas = document.getElementById("pointsChartCanvas");
  const tooltip = document.getElementById("pointsChartTooltip");
  const legend = document.getElementById("pointsChartLegend");

  if (!dataElement || !svg || !canvas || !tooltip || !legend) return;

  const data = JSON.parse(dataElement.textContent);
  if (!data.events.length || !data.series.length) return;

  const SVG_NS = "http://www.w3.org/2000/svg";
  const hiddenSeries = new Set();
  const height = 470;
  const margin = { top: 34, right: 34, bottom: 72, left: 68 };

  function svgNode(tag, attributes, text) {
    const element = document.createElementNS(SVG_NS, tag);
    Object.entries(attributes || {}).forEach(([name, value]) => {
      element.setAttribute(name, String(value));
    });
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function niceStep(value) {
    if (value <= 0) return 2;
    const magnitude = Math.pow(10, Math.floor(Math.log10(value)));
    const normalized = value / magnitude;
    const factor = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
    return factor * magnitude;
  }

  function renderLegend() {
    const fragment = document.createDocumentFragment();
    data.series.forEach((series) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "points-chart-legend-item";
      button.dataset.userId = String(series.user_id);
      button.setAttribute("aria-pressed", "true");

      const dot = document.createElement("span");
      dot.className = "points-chart-legend-dot";
      dot.style.background = series.color;

      const name = document.createElement("span");
      name.textContent = series.name;
      button.append(dot, name);

      button.addEventListener("click", () => {
        const key = String(series.user_id);
        if (hiddenSeries.has(key)) {
          hiddenSeries.delete(key);
          button.classList.remove("is-muted");
          button.setAttribute("aria-pressed", "true");
        } else {
          hiddenSeries.add(key);
          button.classList.add("is-muted");
          button.setAttribute("aria-pressed", "false");
        }
        drawChart();
      });

      fragment.appendChild(button);
    });
    legend.replaceChildren(fragment);
  }

  function showTooltip(eventIndex, x, width) {
    const visible = data.series
      .filter((series) => !hiddenSeries.has(String(series.user_id)))
      .map((series) => ({
        name: series.name,
        color: series.color,
        points: series.points[eventIndex] || 0,
      }))
      .sort((a, b) => b.points - a.points || a.name.localeCompare(b.name, "ru"));

    const event = data.events[eventIndex];
    const title = document.createElement("div");
    title.className = "chart-tooltip-title";
    title.textContent = `R${event.round} · ${event.name}`;

    const fragment = document.createDocumentFragment();
    fragment.appendChild(title);
    visible.forEach((series) => {
      const row = document.createElement("div");
      row.className = "chart-tooltip-row";

      const dot = document.createElement("span");
      dot.className = "chart-tooltip-dot";
      dot.style.background = series.color;

      const name = document.createElement("span");
      name.className = "chart-tooltip-name";
      name.textContent = series.name;

      const points = document.createElement("span");
      points.className = "chart-tooltip-points";
      points.textContent = `${series.points} очк.`;

      row.append(dot, name, points);
      fragment.appendChild(row);
    });

    tooltip.replaceChildren(fragment);
    tooltip.hidden = false;
    tooltip.classList.remove("is-edge-left", "is-edge-right");
    if (x < 150) tooltip.classList.add("is-edge-left");
    if (x > width - 150) tooltip.classList.add("is-edge-right");
    tooltip.style.left = `${x}px`;
  }

  function hideTooltip() {
    tooltip.hidden = true;
  }

  function drawChart() {
    const width = Math.max(920, data.events.length * 86 + margin.left + margin.right);
    const plotWidth = width - margin.left - margin.right;
    const plotHeight = height - margin.top - margin.bottom;
    const allPoints = data.series.flatMap((series) => series.points);
    const rawMax = Math.max(0, ...allPoints);
    const step = niceStep(Math.max(rawMax, 10) / 5);
    let maxY = Math.max(10, Math.ceil(rawMax / step) * step);
    if (maxY <= rawMax) maxY += step;

    const xAt = (index) => {
      if (data.events.length === 1) return margin.left + plotWidth / 2;
      return margin.left + (plotWidth * index) / (data.events.length - 1);
    };
    const yAt = (value) => margin.top + plotHeight - (value / maxY) * plotHeight;

    canvas.style.width = `${width}px`;
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.replaceChildren();
    svg.append(
      svgNode("title", { id: "pointsChartTitle" }, "Динамика очков игроков по этапам"),
      svgNode(
        "desc",
        { id: "pointsChartDescription" },
        "Линейный график накопленных очков каждого игрока.",
      ),
    );

    const defs = svgNode("defs");
    const areaGradient = svgNode("linearGradient", {
      id: "leaderAreaGradient",
      x1: "0",
      y1: "0",
      x2: "0",
      y2: "1",
    });
    const leadingSeries = data.series.find(
      (series) => !hiddenSeries.has(String(series.user_id)),
    );
    if (leadingSeries) {
      areaGradient.append(
        svgNode("stop", { offset: "0%", "stop-color": leadingSeries.color, "stop-opacity": "0.17" }),
        svgNode("stop", { offset: "100%", "stop-color": leadingSeries.color, "stop-opacity": "0" }),
      );
    }
    defs.appendChild(areaGradient);
    svg.appendChild(defs);

    const tickCount = Math.round(maxY / step);
    for (let index = 0; index <= tickCount; index += 1) {
      const value = index * step;
      const y = yAt(value);
      svg.appendChild(svgNode("line", {
        x1: margin.left,
        y1: y,
        x2: width - margin.right,
        y2: y,
        class: "chart-grid-line",
      }));
      svg.appendChild(svgNode("text", {
        x: margin.left - 12,
        y: y + 4,
        "text-anchor": "end",
        class: "chart-axis-label",
      }, value));
    }

    svg.appendChild(svgNode("line", {
      x1: margin.left,
      y1: margin.top,
      x2: margin.left,
      y2: margin.top + plotHeight,
      class: "chart-axis-line",
    }));
    svg.appendChild(svgNode("line", {
      x1: margin.left,
      y1: margin.top + plotHeight,
      x2: width - margin.right,
      y2: margin.top + plotHeight,
      class: "chart-axis-line",
    }));

    data.events.forEach((event, index) => {
      const x = xAt(index);
      svg.appendChild(svgNode("text", {
        x,
        y: height - 39,
        "text-anchor": "middle",
        class: "chart-axis-label",
      }, `R${event.round}`));
    });
    svg.appendChild(svgNode("text", {
      x: 16,
      y: margin.top + plotHeight / 2,
      transform: `rotate(-90 16 ${margin.top + plotHeight / 2})`,
      "text-anchor": "middle",
      class: "chart-axis-title",
    }, "НАКОПЛЕННЫЕ ОЧКИ"));
    svg.appendChild(svgNode("text", {
      x: margin.left + plotWidth / 2,
      y: height - 13,
      "text-anchor": "middle",
      class: "chart-axis-title",
    }, "ПРОШЕДШИЕ ЭТАПЫ"));

    const visibleSeries = data.series.filter(
      (series) => !hiddenSeries.has(String(series.user_id)),
    );

    if (visibleSeries.length) {
      const leader = visibleSeries[0];
      const leaderCoordinates = leader.points.map((value, index) => [xAt(index), yAt(value)]);
      const leaderLine = leaderCoordinates
        .map(([x, y], index) => `${index === 0 ? "M" : "L"}${x},${y}`)
        .join(" ");
      const areaPath = `${leaderLine} L${leaderCoordinates.at(-1)[0]},${margin.top + plotHeight} L${leaderCoordinates[0][0]},${margin.top + plotHeight} Z`;
      svg.appendChild(svgNode("path", {
        d: areaPath,
        fill: "url(#leaderAreaGradient)",
        class: "chart-series-area",
      }));
    }

    visibleSeries.slice().reverse().forEach((series) => {
      const coordinates = series.points.map((value, index) => [xAt(index), yAt(value)]);
      const pathData = coordinates
        .map(([x, y], index) => `${index === 0 ? "M" : "L"}${x},${y}`)
        .join(" ");
      svg.appendChild(svgNode("path", {
        d: pathData,
        stroke: series.color,
        class: "chart-series-line",
        pathLength: "1",
      }));
      coordinates.forEach(([x, y]) => {
        svg.appendChild(svgNode("circle", {
          cx: x,
          cy: y,
          r: 4.2,
          fill: series.color,
          class: "chart-series-point",
        }));
      });
    });

    const focusLine = svgNode("line", {
      y1: margin.top,
      y2: margin.top + plotHeight,
      class: "chart-focus-line",
      visibility: "hidden",
    });
    svg.appendChild(focusLine);

    data.events.forEach((event, index) => {
      const x = xAt(index);
      const previousX = index === 0 ? margin.left : (xAt(index - 1) + x) / 2;
      const nextX = index === data.events.length - 1
        ? width - margin.right
        : (x + xAt(index + 1)) / 2;
      const hitArea = svgNode("rect", {
        x: previousX,
        y: margin.top,
        width: nextX - previousX,
        height: plotHeight,
        class: "chart-hit-area",
        tabindex: "0",
        role: "button",
        "aria-label": `R${event.round}, ${event.name}`,
      });

      const activate = () => {
        focusLine.setAttribute("x1", x);
        focusLine.setAttribute("x2", x);
        focusLine.setAttribute("visibility", "visible");
        showTooltip(index, x, width);
      };
      hitArea.addEventListener("pointerenter", activate);
      hitArea.addEventListener("focus", activate);
      hitArea.addEventListener("pointerleave", () => {
        focusLine.setAttribute("visibility", "hidden");
        hideTooltip();
      });
      hitArea.addEventListener("blur", () => {
        focusLine.setAttribute("visibility", "hidden");
        hideTooltip();
      });
      svg.appendChild(hitArea);
    });
  }

  renderLegend();
  drawChart();
})();
