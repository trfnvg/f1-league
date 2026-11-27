(() => {
  "use strict";

  // Each point is [x, back row, front row] in the matching background's viewBox.
  const grandstands = {
    wide: {
      rows: [[-4, 207, 233], [49, 218, 241], [95, 230, 248], [151, 240, 255],
        [209, 252, 261], [262, 261, 265], [316, 268, 269]],
      aisles: [42, 102, 164, 230],
      flags: [[15, 228, 1.4, "#df6346"], [69, 239, 1.2, "#e6caaa"], [122, 247, 1, "#67b4ad"],
        [183, 253, .84, "#df6346"], [221, 260, .71, "#edc98e"], [263, 264, .59, "#79bdb7"],
        [291, 267, .45, "#df6346"]],
    },
    portrait: {
      rows: [[-4, 326, 345], [28, 334, 352], [63, 346, 361], [102, 360, 369],
        [128, 366, 375], [157, 375, 380]],
      aisles: [15, 59, 107],
      flags: [[9, 342, 1.28, "#df6346"], [35, 349, 1.15, "#edc98e"], [67, 358, 1.04, "#67b4ad"],
        [91, 366, .84, "#df6346"], [123, 372, .68, "#e6caaa"], [144, 377, .48, "#79bdb7"]],
    },
  };
  const shirts = ["#36242a", "#634348", "#a34e39", "#ceb092", "#664739", "#44676b", "#9a7e65", "#332d36"];
  const skinTones = ["#dec0a1", "#bc9073", "#8d6558", "#6e5248"];
  const svgNS = "http://www.w3.org/2000/svg";

  function shape(parent, name, attributes) {
    const node = document.createElementNS(svgNS, name);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
    parent.append(node);
    return node;
  }

  // Keep the stands visually consistent when a player reloads for another attempt.
  let seed = 2879;
  function variation() {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed / 4294967296;
  }

  function animate(node, minSeconds, maxSeconds) {
    const duration = minSeconds + variation() * (maxSeconds - minSeconds);
    node.style.setProperty("--tempo", duration + "s");
    node.style.setProperty("--stagger", -variation() * duration + "s");
  }

  function spectator(parent, x, y, size, cheering) {
    const shirt = shirts[Math.floor(variation() * shirts.length)];
    const skin = skinTones[Math.floor(variation() * skinTones.length)];
    const fan = shape(parent, "g", { transform: `translate(${x} ${y}) scale(${size})` });
    if (cheering) {
      const arms = shape(fan, "path", {
        class: "lights-out-fan-motion",
        d: variation() < .5 ? "M-1 0 -2.2-1.4 -2.8-3.7 M1 0 2.1-1.5 2.5-3.9" : "M1 0 2.4-1.1 3.2-3.5",
        fill: "none", stroke: shirt, "stroke-width": 1, "stroke-linecap": "round",
      });
      animate(arms, 2, 5.5);
    }
    shape(fan, "path", { d: "M-1.7 1.3 -1.4-.7Q0-1.6 1.4-.7L1.7 1.3Z", fill: shirt });
    shape(fan, "circle", { cy: -2, r: .92, fill: skin });
  }

  function flag(parent, x, y, size, color) {
    const flag = shape(parent, "g", { transform: `translate(${x} ${y}) scale(${size})`, opacity: .83 });
    shape(flag, "path", { d: "M0 0V-13", stroke: "#b6a198", "stroke-width": .8 });
    const cloth = shape(flag, "g", { class: "lights-out-flag-cloth" });
    shape(cloth, "path", { d: "M0-13C4-15 7-12 11-14L10-8C6-6 4-9 0-7Z", fill: color });
    shape(cloth, "path", { d: "M0-10.5C4-12 7-9 10.5-11.5L10.3-10C7-7.5 4-10.5 0-9Z", fill: "#fff1d7", opacity: .5 });
    animate(cloth, 1.15, 2.7);
  }

  for (const overlay of document.querySelectorAll("[data-grandstand]")) {
    const { rows, aisles, flags } = grandstands[overlay.dataset.grandstand];
    const lastX = rows.at(-1)[0];
    const crowd = shape(overlay, "g", { opacity: .86 });
    for (const depth of [.13, .32, .52, .73, .91]) {
      let segment = 1;
      for (let x = rows[0][0] + variation() * 8; x < lastX; x += 4 + variation() * 5 - 2.6 * x / lastX) {
        if (aisles.some(aisle => Math.abs(x - aisle) < 2.1) || variation() < .14) continue;
        while (x > rows[segment][0]) segment++;
        const [left, backLeft, frontLeft] = rows[segment - 1];
        const [right, backRight, frontRight] = rows[segment];
        const progress = (x - left) / (right - left);
        const back = backLeft + (backRight - backLeft) * progress;
        const front = frontLeft + (frontRight - frontLeft) * progress;
        const y = back + (front - back) * depth + variation() * 1.1;
        const size = (1.12 - .82 * x / lastX) * (.76 + .3 * depth + variation() * .21);
        spectator(crowd, x, y, size, variation() < .39);
      }
    }
    for (const position of flags) flag(overlay, ...position);
  }
})();
