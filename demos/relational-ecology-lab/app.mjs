import {
  CONFIG,
  Simulation,
  WORLD_HEIGHT,
  WORLD_WIDTH,
  clamp,
  normalizeSeed,
} from "./core.mjs";

const canvas = document.querySelector("#world-canvas");
const context = canvas.getContext("2d");

const elements = {
  runToggle: document.querySelector("#run-toggle"),
  runLabel: document.querySelector("#run-label"),
  speed: document.querySelector("#speed-select"),
  seed: document.querySelector("#seed-input"),
  reset: document.querySelector("#reset-button"),
  focus: document.querySelector("#focus-select"),
  overlay: document.querySelector("#overlay-select"),
  fieldMode: document.querySelector("#field-mode"),
  focusKind: document.querySelector("#focus-kind"),
  focusId: document.querySelector("#focus-id"),
  focusStatus: document.querySelector("#focus-status"),
  decisionLabel: document.querySelector("#decision-label"),
  decisionHeading: document.querySelector("#decision-heading"),
  decisionReason: document.querySelector("#decision-reason"),
  predictionValues: document.querySelector("#prediction-values"),
  thetaValue: document.querySelector("#theta-value"),
  xiValue: document.querySelector("#xi-value"),
  reliabilityValues: document.querySelector("#reliability-values"),
  leapCount: document.querySelector("#leap-count"),
  eventLog: document.querySelector("#event-log"),
  observerEvent: document.querySelector("#observer-event"),
  metricTick: document.querySelector("#metric-tick"),
  metricEpisode: document.querySelector("#metric-episode"),
  metricLiving: document.querySelector("#metric-living"),
  metricDormant: document.querySelector("#metric-dormant"),
  metricRelocations: document.querySelector("#metric-relocations"),
  metricLeaps: document.querySelector("#metric-leaps"),
  needsHeading: document.querySelector("#needs-heading"),
};

const needMeters = [
  {
    label: document.querySelector("#need-1-label"),
    value: document.querySelector("#hunger-value"),
    bar: document.querySelector("#hunger-bar"),
  },
  {
    label: document.querySelector("#need-2-label"),
    value: document.querySelector("#thirst-value"),
    bar: document.querySelector("#thirst-bar"),
  },
  {
    label: document.querySelector("#need-3-label"),
    value: document.querySelector("#fear-value"),
    bar: document.querySelector("#fear-bar"),
  },
  {
    label: document.querySelector("#need-4-label"),
    value: document.querySelector("#fatigue-value"),
    bar: document.querySelector("#fatigue-bar"),
  },
];

const hMeters = [
  {
    label: document.querySelector("#h-1-label"),
    value: document.querySelector("#h-resource-value"),
    bar: document.querySelector("#h-resource-bar"),
  },
  {
    label: document.querySelector("#h-2-label"),
    value: document.querySelector("#h-danger-value"),
    bar: document.querySelector("#h-danger-bar"),
  },
  {
    label: document.querySelector("#h-3-label"),
    value: document.querySelector("#h-motion-value"),
    bar: document.querySelector("#h-motion-bar"),
  },
];

const rabbitColors = ["#eef5e8", "#cce8df", "#f1dfb7", "#d9cef0", "#bdd7ed"];
const decisionLabels = {
  explore: "explore",
  escape: "escape",
  chase: "chase",
  search: "search",
  water: "hydrate",
  food: "forage",
  rest: "rest",
  cover: "cover",
};

const query = new URLSearchParams(window.location.search);
let simulation = new Simulation({ seed: normalizeSeed(query.get("seed") ?? 2401) });
let focusedAgentKey = simulation.rabbits[0].focusKey;
let running = true;
let speed = 1;
let lastFrame = performance.now();
let accumulator = 0;
let lastUiTick = -1;
let eventSignature = "";
let observerSignature = "";
let deviceScale = 1;

elements.seed.value = String(simulation.seed);

function configureCanvas() {
  deviceScale = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(WORLD_WIDTH * deviceScale);
  canvas.height = Math.round(WORLD_HEIGHT * deviceScale);
  context.setTransform(deviceScale, 0, 0, deviceScale, 0, 0);
  context.imageSmoothingEnabled = true;
}

function buildFocusOptions() {
  elements.focus.replaceChildren();
  for (const agent of simulation.relationalAgents()) {
    const option = document.createElement("option");
    option.value = agent.focusKey;
    option.textContent = agent.profile.kind === "rabbit"
      ? `Rabbit ${agent.id + 1}`
      : "Predator 1";
    elements.focus.append(option);
  }
  elements.focus.value = focusedAgentKey;
}

function focusAgent() {
  return simulation.relationalAgents().find((agent) => agent.focusKey === focusedAgentKey)
    ?? simulation.rabbits[0];
}

function rebuildOverlayOptions(agent, preferred = elements.overlay.value) {
  elements.overlay.replaceChildren();
  for (const overlay of agent.profile.overlays) {
    const option = document.createElement("option");
    option.value = overlay.value;
    option.textContent = overlay.option;
    elements.overlay.append(option);
  }
  const available = agent.profile.overlays.some((overlay) => overlay.value === preferred);
  elements.overlay.value = available ? preferred : "actual";
}

function setFocusedAgent(key) {
  const next = simulation.relationalAgents().find((agent) => agent.focusKey === key);
  if (!next) return;
  focusedAgentKey = next.focusKey;
  elements.focus.value = focusedAgentKey;
  rebuildOverlayOptions(next);
  eventSignature = "";
  lastUiTick = -1;
  updateInterface(true);
}

function setMeter(meter, value, maximum = 1) {
  const safeValue = Number.isFinite(value) ? value : 0;
  const normalized = clamp(safeValue / maximum);
  meter.value.textContent = safeValue.toFixed(2);
  meter.bar.style.width = `${(normalized * 100).toFixed(1)}%`;
}

function rebuildSimulation() {
  const seed = normalizeSeed(elements.seed.value);
  simulation = new Simulation({ seed });
  elements.seed.value = String(seed);
  if (!simulation.relationalAgents().some((agent) => agent.focusKey === focusedAgentKey)) {
    focusedAgentKey = simulation.rabbits[0].focusKey;
  }
  buildFocusOptions();
  rebuildOverlayOptions(focusAgent());
  accumulator = 0;
  eventSignature = "";
  observerSignature = "";
  lastUiTick = -1;
  const nextUrl = new URL(window.location.href);
  nextUrl.searchParams.set("seed", String(seed));
  window.history.replaceState(null, "", nextUrl);
  updateInterface(true);
  drawScene();
}

function setRunning(nextRunning) {
  running = nextRunning;
  elements.runToggle.setAttribute("aria-pressed", String(running));
  elements.runLabel.textContent = running ? "実行中" : "一時停止";
  lastFrame = performance.now();
}

function drawRoundedLabel(text, x, y, color = "#a8b4ac") {
  context.save();
  context.font = "10px ui-monospace, SFMono-Regular, Consolas, monospace";
  const width = context.measureText(text).width + 16;
  context.fillStyle = "rgba(7, 11, 10, 0.78)";
  context.strokeStyle = "rgba(97, 116, 107, 0.45)";
  context.lineWidth = 1;
  context.beginPath();
  context.roundRect(x, y - 15, width, 22, 5);
  context.fill();
  context.stroke();
  context.fillStyle = color;
  context.fillText(text, x + 8, y);
  context.restore();
}

function drawBackground() {
  const gradient = context.createLinearGradient(0, 0, WORLD_WIDTH, WORLD_HEIGHT);
  gradient.addColorStop(0, "#0c1210");
  gradient.addColorStop(0.55, "#0a100f");
  gradient.addColorStop(1, "#0e1311");
  context.fillStyle = gradient;
  context.fillRect(0, 0, WORLD_WIDTH, WORLD_HEIGHT);

  context.save();
  context.strokeStyle = "rgba(165, 184, 169, 0.045)";
  context.lineWidth = 1;
  for (let x = 0; x <= WORLD_WIDTH; x += 40) {
    context.beginPath();
    context.moveTo(x, 0);
    context.lineTo(x, WORLD_HEIGHT);
    context.stroke();
  }
  for (let y = 0; y <= WORLD_HEIGHT; y += 40) {
    context.beginPath();
    context.moveTo(0, y);
    context.lineTo(WORLD_WIDTH, y);
    context.stroke();
  }
  context.restore();
}

function drawMemoryOverlay(agent) {
  const mode = elements.overlay.value;
  if (mode === "actual" || !agent) return;
  const memory = agent.memory;
  const cellWidth = WORLD_WIDTH / memory.columns;
  const cellHeight = WORLD_HEIGHT / memory.rows;

  context.save();
  context.globalCompositeOperation = "screen";
  for (let row = 0; row < memory.rows; row += 1) {
    for (let column = 0; column < memory.columns; column += 1) {
      const index = memory.index(column, row);
      const x = column * cellWidth;
      const y = row * cellHeight;
      if (mode === "resource") {
        const food = memory.food[index];
        const water = memory.water[index];
        if (food > 0.015) {
          context.fillStyle = `rgba(92, 196, 102, ${food * 0.3})`;
          context.fillRect(x + 1, y + 1, cellWidth - 2, cellHeight - 2);
        }
        if (water > 0.015) {
          context.fillStyle = `rgba(76, 179, 222, ${water * 0.32})`;
          context.fillRect(x + 1, y + 1, cellWidth - 2, cellHeight - 2);
        }
      } else if (mode === "prey") {
        const prey = memory.prey[index];
        if (prey < 0.015) continue;
        context.fillStyle = `rgba(242, 101, 88, ${prey * 0.34})`;
        context.fillRect(x + 1, y + 1, cellWidth - 2, cellHeight - 2);
      } else {
        const value = mode === "danger"
          ? memory.danger[index]
          : mode === "motion"
            ? memory.motion[index]
            : memory.visits[index];
        if (value < 0.015) continue;
        const color = mode === "danger"
          ? `rgba(230, 73, 69, ${value * 0.33})`
          : mode === "motion"
            ? `rgba(226, 160, 72, ${value * 0.32})`
            : `rgba(144, 124, 204, ${value * 0.25})`;
        context.fillStyle = color;
        context.fillRect(x + 1, y + 1, cellWidth - 2, cellHeight - 2);
      }
    }
  }
  context.restore();
}

function drawObstacle(obstacle) {
  const radius = obstacle.radius;
  const idNumber = Number.parseInt(obstacle.id.slice(1), 10) || 1;
  context.save();
  context.shadowColor = "rgba(0, 0, 0, 0.5)";
  context.shadowBlur = 13;
  context.shadowOffsetY = 7;
  const stone = context.createRadialGradient(
    obstacle.x - radius * 0.32,
    obstacle.y - radius * 0.38,
    radius * 0.08,
    obstacle.x,
    obstacle.y,
    radius,
  );
  stone.addColorStop(0, "#78817b");
  stone.addColorStop(0.45, "#4c5651");
  stone.addColorStop(1, "#252d2a");
  context.fillStyle = stone;
  context.strokeStyle = "rgba(168, 181, 172, 0.28)";
  context.lineWidth = 1.2;
  context.beginPath();
  for (let index = 0; index < 12; index += 1) {
    const angle = (index / 12) * Math.PI * 2;
    const variation = 0.9 + Math.sin(index * 2.7 + idNumber * 1.9) * 0.055;
    const x = obstacle.x + Math.cos(angle) * radius * variation;
    const y = obstacle.y + Math.sin(angle) * radius * variation;
    if (index === 0) context.moveTo(x, y);
    else context.lineTo(x, y);
  }
  context.closePath();
  context.fill();
  context.shadowColor = "transparent";
  context.stroke();

  context.strokeStyle = "rgba(198, 209, 201, 0.13)";
  context.beginPath();
  context.arc(
    obstacle.x - radius * 0.08,
    obstacle.y - radius * 0.06,
    radius * 0.54,
    Math.PI * 1.08,
    Math.PI * 1.7,
  );
  context.stroke();
  context.restore();
}

function drawObstacles() {
  for (const obstacle of simulation.world.obstacles) drawObstacle(obstacle);
}

function drawDormantResource(resource) {
  context.save();
  context.setLineDash([4, 5]);
  context.lineWidth = 1;
  context.strokeStyle = resource.kind === "grass"
    ? "rgba(134, 157, 130, 0.34)"
    : "rgba(105, 163, 180, 0.34)";
  context.beginPath();
  context.arc(resource.x, resource.y, Math.max(12, resource.radius * 0.55), 0, Math.PI * 2);
  context.stroke();
  context.setLineDash([]);
  context.fillStyle = "rgba(176, 188, 178, 0.45)";
  context.font = "9px ui-monospace, SFMono-Regular, Consolas, monospace";
  context.textAlign = "center";
  context.fillText(String(Math.max(0, resource.dormantFor)), resource.x, resource.y + 3);
  context.restore();
}

function drawGrass(resource) {
  const radius = resource.radius;
  const alpha = 0.2 + resource.amount * 0.42;
  context.save();
  const glow = context.createRadialGradient(
    resource.x,
    resource.y,
    radius * 0.1,
    resource.x,
    resource.y,
    radius * 1.2,
  );
  glow.addColorStop(0, `rgba(128, 211, 122, ${alpha})`);
  glow.addColorStop(0.55, `rgba(67, 142, 76, ${alpha * 0.7})`);
  glow.addColorStop(1, "rgba(42, 91, 55, 0)");
  context.fillStyle = glow;
  context.beginPath();
  context.arc(resource.x, resource.y, radius * 1.25, 0, Math.PI * 2);
  context.fill();

  context.strokeStyle = `rgba(166, 224, 145, ${0.2 + resource.cover * 0.28})`;
  context.lineWidth = 1;
  for (let index = 0; index < 7; index += 1) {
    const angle = (index / 7) * Math.PI * 2 + resource.x * 0.001;
    const inner = radius * 0.18;
    const outer = radius * (0.54 + (index % 3) * 0.09);
    context.beginPath();
    context.moveTo(
      resource.x + Math.cos(angle) * inner,
      resource.y + Math.sin(angle) * inner,
    );
    context.quadraticCurveTo(
      resource.x + Math.cos(angle + 0.2) * outer * 0.72,
      resource.y + Math.sin(angle + 0.2) * outer * 0.72,
      resource.x + Math.cos(angle) * outer,
      resource.y + Math.sin(angle) * outer,
    );
    context.stroke();
  }
  context.restore();
}

function drawWater(resource) {
  const radius = resource.radius;
  context.save();
  const water = context.createRadialGradient(
    resource.x - radius * 0.2,
    resource.y - radius * 0.22,
    1,
    resource.x,
    resource.y,
    radius,
  );
  water.addColorStop(0, `rgba(133, 215, 235, ${0.34 + resource.amount * 0.35})`);
  water.addColorStop(0.55, `rgba(54, 133, 165, ${0.26 + resource.amount * 0.28})`);
  water.addColorStop(1, "rgba(32, 82, 104, 0.08)");
  context.fillStyle = water;
  context.beginPath();
  context.ellipse(resource.x, resource.y, radius, radius * 0.76, -0.12, 0, Math.PI * 2);
  context.fill();
  context.strokeStyle = `rgba(157, 224, 238, ${0.22 + resource.amount * 0.28})`;
  context.lineWidth = 1;
  for (const scale of [0.42, 0.72]) {
    context.beginPath();
    context.ellipse(resource.x, resource.y, radius * scale, radius * scale * 0.56, -0.12, 0, Math.PI * 2);
    context.stroke();
  }
  context.restore();
}

function drawResources() {
  for (const resource of simulation.world.resources) {
    if (resource.dormant) {
      drawDormantResource(resource);
    } else if (resource.kind === "grass") {
      drawGrass(resource);
    } else {
      drawWater(resource);
    }
  }
}

function drawFocusRelations(agent) {
  if (!agent?.alive) return;
  context.save();
  context.setLineDash([5, 7]);
  context.lineWidth = 1;
  context.strokeStyle = "rgba(209, 225, 209, 0.13)";
  context.beginPath();
  context.arc(agent.x, agent.y, agent.profile.visionRange, 0, Math.PI * 2);
  context.stroke();

  if (agent.decision) {
    context.setLineDash([8, 6]);
    context.strokeStyle = agent.decision.label === "escape"
      ? "rgba(237, 113, 106, 0.72)"
      : agent.profile.kind === "predator"
        ? "rgba(242, 132, 94, 0.65)"
        : "rgba(225, 236, 205, 0.58)";
    context.beginPath();
    context.moveTo(agent.x, agent.y);
    context.lineTo(
      clamp(agent.decision.target.x, 0, WORLD_WIDTH),
      clamp(agent.decision.target.y, 0, WORLD_HEIGHT),
    );
    context.stroke();
  }

  const perception = agent.lastPerception;
  if (perception?.heardThreat && !perception.visibleThreat) {
    context.setLineDash([2, 7]);
    context.strokeStyle = "rgba(237, 113, 106, 0.5)";
    context.beginPath();
    context.moveTo(agent.x, agent.y);
    context.lineTo(
      agent.x + perception.heardThreat.x * 94,
      agent.y + perception.heardThreat.y * 94,
    );
    context.stroke();
  }

  context.setLineDash([]);
  for (const resource of perception?.visibleResources ?? []) {
    context.strokeStyle = resource.kind === "grass"
      ? "rgba(132, 205, 118, 0.18)"
      : "rgba(104, 199, 221, 0.2)";
    context.beginPath();
    context.moveTo(agent.x, agent.y);
    context.lineTo(resource.x, resource.y);
    context.stroke();
  }
  for (const obstacle of perception?.visibleObstacles ?? []) {
    context.strokeStyle = "rgba(177, 187, 181, 0.17)";
    context.beginPath();
    context.moveTo(agent.x, agent.y);
    context.lineTo(obstacle.x, obstacle.y);
    context.stroke();
  }
  for (const rabbit of perception?.visiblePrey ?? []) {
    context.strokeStyle = "rgba(242, 113, 98, 0.26)";
    context.beginPath();
    context.moveTo(agent.x, agent.y);
    context.lineTo(rabbit.x, rabbit.y);
    context.stroke();
  }
  context.restore();
}

function drawThreat(focused = false) {
  const threat = simulation.threat;
  const color = threat.state === "attack"
    ? "#ffb15d"
    : threat.state === "recover"
      ? "#9f7770"
      : threat.state === "chase"
        ? "#ff716a"
        : "#cc615d";
  const active = threat.state === "chase" || threat.state === "attack";
  context.save();
  context.strokeStyle = active
    ? "rgba(244, 99, 92, 0.2)"
    : "rgba(211, 104, 98, 0.11)";
  context.lineWidth = 1;
  context.beginPath();
  context.arc(threat.x, threat.y, 30 + Math.sin(simulation.tick * 0.08) * 3, 0, Math.PI * 2);
  context.stroke();

  if (focused) {
    context.strokeStyle = "rgba(232, 183, 104, 0.9)";
    context.lineWidth = 1.5;
    context.beginPath();
    context.arc(threat.x, threat.y, 18, 0, Math.PI * 2);
    context.stroke();
  }
  if (threat.leapPulse > 0) {
    const progress = 1 - threat.leapPulse / 34;
    context.strokeStyle = `rgba(186, 155, 231, ${1 - progress})`;
    context.lineWidth = 2;
    context.beginPath();
    context.arc(threat.x, threat.y, 20 + progress * 28, 0, Math.PI * 2);
    context.stroke();
  }

  context.translate(threat.x, threat.y);
  context.rotate(Math.atan2(threat.vy, threat.vx));
  context.fillStyle = color;
  context.shadowColor = color;
  context.shadowBlur = threat.state === "attack" ? 20 : active ? 14 : 7;
  context.beginPath();
  context.moveTo(13, 0);
  context.lineTo(-9, -7);
  context.lineTo(-5, 0);
  context.lineTo(-9, 7);
  context.closePath();
  context.fill();
  context.restore();

  if (threat.state !== "wander") {
    drawRoundedLabel(threat.state, threat.x + 13, threat.y - 13, color);
  }
}

function drawRabbit(rabbit, focused) {
  const color = rabbitColors[rabbit.id % rabbitColors.length];
  context.save();
  context.translate(rabbit.x, rabbit.y);

  if (!rabbit.alive) {
    context.strokeStyle = "rgba(184, 119, 111, 0.55)";
    context.lineWidth = 1.5;
    context.beginPath();
    context.moveTo(-6, -6);
    context.lineTo(6, 6);
    context.moveTo(6, -6);
    context.lineTo(-6, 6);
    context.stroke();
    context.restore();
    return;
  }

  if (focused) {
    context.strokeStyle = "rgba(232, 183, 104, 0.9)";
    context.lineWidth = 1.5;
    context.beginPath();
    context.arc(0, 0, 15, 0, Math.PI * 2);
    context.stroke();
  }

  if (rabbit.leapPulse > 0) {
    const progress = 1 - rabbit.leapPulse / 34;
    context.strokeStyle = `rgba(186, 155, 231, ${1 - progress})`;
    context.lineWidth = 2;
    context.beginPath();
    context.arc(0, 0, 17 + progress * 25, 0, Math.PI * 2);
    context.stroke();
  }

  context.rotate(Math.atan2(rabbit.vy, rabbit.vx));
  context.fillStyle = color;
  context.shadowColor = color;
  context.shadowBlur = focused ? 10 : 4;
  context.beginPath();
  context.ellipse(-1, 0, 8, 6, 0, 0, Math.PI * 2);
  context.fill();
  context.beginPath();
  context.ellipse(5, -4.5, 5.8, 2, -0.55, 0, Math.PI * 2);
  context.ellipse(5, 4.5, 5.8, 2, 0.55, 0, Math.PI * 2);
  context.fill();
  context.fillStyle = "#121917";
  context.beginPath();
  context.arc(3.5, -2.3, 1, 0, Math.PI * 2);
  context.fill();
  context.restore();

  context.save();
  context.fillStyle = focused ? "#e8b768" : "rgba(214, 223, 214, 0.62)";
  context.font = "9px ui-monospace, SFMono-Regular, Consolas, monospace";
  context.textAlign = "center";
  context.fillText(String(rabbit.id + 1), rabbit.x, rabbit.y + 21);
  context.restore();
}

function drawBoundary() {
  context.save();
  context.strokeStyle = "rgba(130, 151, 139, 0.33)";
  context.lineWidth = 2;
  context.strokeRect(
    CONFIG.worldMargin,
    CONFIG.worldMargin,
    WORLD_WIDTH - CONFIG.worldMargin * 2,
    WORLD_HEIGHT - CONFIG.worldMargin * 2,
  );
  context.restore();
}

function drawScene() {
  context.setTransform(deviceScale, 0, 0, deviceScale, 0, 0);
  context.clearRect(0, 0, WORLD_WIDTH, WORLD_HEIGHT);
  drawBackground();
  const focused = focusAgent();
  drawMemoryOverlay(focused);
  drawObstacles();
  drawResources();
  drawFocusRelations(focused);
  drawThreat(focused === simulation.threat);
  for (const rabbit of simulation.rabbits) drawRabbit(rabbit, rabbit.focusKey === focusedAgentKey);
  drawBoundary();

  context.save();
  context.fillStyle = "rgba(213, 223, 214, 0.55)";
  context.font = "10px ui-monospace, SFMono-Regular, Consolas, monospace";
  context.fillText(`seed ${simulation.seed} · fixed tick ${simulation.tick}`, 31, 39);
  context.restore();
}

function renderEventLog(agent) {
  const signature = `${agent.focusKey}:${agent.events.map((event) => `${event.tick}-${event.type}`).join("|")}`;
  if (signature === eventSignature) return;
  eventSignature = signature;
  elements.eventLog.replaceChildren();

  if (agent.events.length === 0) {
    const empty = document.createElement("li");
    empty.className = "empty-event";
    empty.textContent = "最初の意思決定を待っています。";
    elements.eventLog.append(empty);
    return;
  }

  for (const event of agent.events.slice(0, 8)) {
    const item = document.createElement("li");
    item.className = event.type;
    const meta = document.createElement("div");
    meta.className = "event-meta";
    const title = document.createElement("span");
    title.textContent = event.title;
    const time = document.createElement("time");
    time.textContent = `t ${event.tick}`;
    meta.append(title, time);
    item.append(meta);
    if (event.detail) {
      const detail = document.createElement("p");
      detail.className = "event-detail";
      detail.textContent = event.detail;
      item.append(detail);
    }
    elements.eventLog.append(item);
  }
}

function updateFocusOptionLabels() {
  const agents = simulation.relationalAgents();
  for (const option of elements.focus.options) {
    const agent = agents.find((candidate) => candidate.focusKey === option.value);
    if (!agent) continue;
    option.textContent = agent.profile.kind === "rabbit"
      ? `Rabbit ${agent.id + 1}${agent.alive ? "" : " · stopped"}`
      : `Predator 1 · ${agent.state}`;
  }
}

function updateInterface(force = false) {
  if (!force && simulation.tick === lastUiTick) return;
  lastUiTick = simulation.tick;
  const agent = focusAgent();
  const metrics = simulation.metrics();

  elements.focusKind.textContent = agent.profile.name;
  elements.focusId.textContent = agent.profile.kind === "rabbit" ? String(agent.id + 1) : "1";
  elements.focusStatus.textContent = agent.profile.status(agent);
  elements.focusStatus.classList.toggle("dead", !agent.alive);
  const overlay = agent.profile.overlays.find((candidate) => candidate.value === elements.overlay.value);
  elements.fieldMode.textContent = overlay?.label ?? "観測: 物理環境";
  updateFocusOptionLabels();

  elements.needsHeading.textContent = agent.profile.needHeading;
  const needs = agent.profile.needIndicators(agent);
  for (let index = 0; index < needMeters.length; index += 1) {
    needMeters[index].label.textContent = needs[index]?.label ?? "—";
    setMeter(needMeters[index], needs[index]?.value ?? 0);
  }

  const hMaximum = Math.max(1.05, agent.thetaEffective * 1.25);
  for (let index = 0; index < hMeters.length; index += 1) {
    const dimension = agent.profile.errorDimensions[index];
    hMeters[index].label.textContent = dimension;
    setMeter(hMeters[index], agent.H[dimension], hMaximum);
  }
  elements.thetaValue.textContent = agent.thetaEffective.toFixed(2);
  elements.xiValue.textContent = agent.xi.toFixed(2);
  elements.reliabilityValues.textContent = agent.profile.errorDimensions
    .map((dimension) => (
      `${agent.profile.dimensionLabels[dimension]} ${agent.reliability[dimension].toFixed(2)}`
    ))
    .join(" · ");
  elements.leapCount.textContent = String(agent.leapCount);

  if (agent.alive && agent.decision) {
    elements.decisionLabel.textContent = decisionLabels[agent.decision.label] ?? agent.decision.label;
    elements.decisionHeading.textContent = agent.decision.title;
    elements.decisionReason.textContent = agent.decision.reason;
    const predicted = agent.decision.prediction;
    elements.predictionValues.textContent = agent.profile.errorDimensions
      .map((dimension) => (
        `${agent.profile.dimensionLabels[dimension]} ${predicted[dimension].toFixed(2)}`
      ))
      .join(" / ");
  } else if (!agent.alive) {
    elements.decisionLabel.textContent = "stopped";
    elements.decisionHeading.textContent = "行動停止";
    elements.decisionReason.textContent = agent.causeOfDeath ?? "この個体は更新対象から外れました。";
    elements.predictionValues.textContent = "予測更新なし";
  } else {
    elements.decisionLabel.textContent = "perceive";
    elements.decisionHeading.textContent = "初期知覚を構成中";
    elements.decisionReason.textContent = "最初の fixed tick で行動候補を比較します。";
    elements.predictionValues.textContent = "予測構成中";
  }

  renderEventLog(agent);
  elements.metricTick.textContent = metrics.tick.toLocaleString("ja-JP");
  elements.metricEpisode.textContent = String(metrics.episode);
  elements.metricLiving.textContent = `${metrics.living} / ${CONFIG.rabbitCount}`;
  elements.metricDormant.textContent = String(metrics.dormant);
  elements.metricRelocations.textContent = String(metrics.relocations);
  elements.metricLeaps.textContent = String(metrics.leaps);

  const observerEvent = simulation.observerEvents[0];
  const nextObserverSignature = observerEvent
    ? `${observerEvent.tick}:${observerEvent.type}:${observerEvent.title}`
    : "none";
  if (nextObserverSignature !== observerSignature) {
    observerSignature = nextObserverSignature;
    elements.observerEvent.textContent = observerEvent
      ? `t ${observerEvent.tick} · ${observerEvent.title} — ${observerEvent.detail}`
      : "観測イベントはまだありません。";
  }
}

elements.runToggle.addEventListener("click", () => setRunning(!running));
elements.speed.addEventListener("change", () => {
  speed = Number(elements.speed.value) || 1;
});
elements.reset.addEventListener("click", rebuildSimulation);
elements.seed.addEventListener("keydown", (event) => {
  if (event.key === "Enter") rebuildSimulation();
});
elements.focus.addEventListener("change", () => setFocusedAgent(elements.focus.value));
elements.overlay.addEventListener("change", () => {
  const agent = focusAgent();
  const overlay = agent.profile.overlays.find((candidate) => candidate.value === elements.overlay.value);
  elements.fieldMode.textContent = overlay?.label ?? "観測: 物理環境";
  drawScene();
});

canvas.addEventListener("pointerdown", (event) => {
  const bounds = canvas.getBoundingClientRect();
  const x = ((event.clientX - bounds.left) / bounds.width) * WORLD_WIDTH;
  const y = ((event.clientY - bounds.top) / bounds.height) * WORLD_HEIGHT;
  let nearest = null;
  let nearestDistance = Infinity;
  for (const agent of simulation.relationalAgents()) {
    const currentDistance = Math.hypot(x - agent.x, y - agent.y);
    if (currentDistance < nearestDistance) {
      nearest = agent;
      nearestDistance = currentDistance;
    }
  }
  if (nearest && nearestDistance <= 42) setFocusedAgent(nearest.focusKey);
});

window.addEventListener("keydown", (event) => {
  const target = event.target;
  const isEditing = target instanceof HTMLInputElement
    || target instanceof HTMLSelectElement
    || target instanceof HTMLTextAreaElement;
  if (event.code === "Space" && !isEditing) {
    event.preventDefault();
    setRunning(!running);
  }
});

window.addEventListener("resize", () => {
  const nextScale = Math.min(window.devicePixelRatio || 1, 2);
  if (nextScale !== deviceScale) configureCanvas();
  drawScene();
});

document.addEventListener("visibilitychange", () => {
  lastFrame = performance.now();
  accumulator = 0;
});

function animationFrame(now) {
  const elapsed = Math.min(100, now - lastFrame);
  lastFrame = now;
  if (running) {
    accumulator += elapsed * speed;
    const fixedDuration = 1000 / 60;
    let steps = 0;
    while (accumulator >= fixedDuration && steps < 12) {
      simulation.step();
      accumulator -= fixedDuration;
      steps += 1;
    }
  }
  drawScene();
  if (simulation.tick % 4 === 0 || !running) updateInterface();
  requestAnimationFrame(animationFrame);
}

configureCanvas();
buildFocusOptions();
rebuildOverlayOptions(focusAgent());
updateInterface(true);
drawScene();
requestAnimationFrame(animationFrame);
