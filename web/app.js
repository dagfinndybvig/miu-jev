const state = {
  current: "MI",
  history: [{ value: "MI", label: "Axiom" }],
  moves: [],
  probabilities: {},
  selectedId: null,
  busy: false,
  auto: false,
  providers: {},
};
const SERVER_MAX_LENGTH = 8192;

const $ = (id) => document.getElementById(id);
const elements = {
  current: $("currentString"),
  goal: $("goal"),
  model: $("model"),
  provider: $("provider"),
  policy: $("policy"),
  moves: $("moves"),
  history: $("history"),
  stepCount: $("stepCount"),
  lengthCount: $("lengthCount"),
  moveCount: $("moveCount"),
  iModulo: $("iModulo"),
  invariantNotice: $("invariantNotice"),
  jevStep: $("jevStep"),
  autoRun: $("autoRun"),
  undo: $("undo"),
  reset: $("reset"),
  thinking: $("thinking"),
  error: $("errorBox"),
  status: $("engineStatus"),
  statusText: $("engineStatusText"),
  delay: $("delay"),
  maxSteps: $("maxSteps"),
  maxLength: $("maxLength"),
  stagnationLimit: $("stagnationLimit"),
  exploreImpossible: $("exploreImpossible"),
  runNotice: $("runNotice"),
};

function validMiu(value) {
  return /^[MIU]+$/.test(value);
}

function targetDistance(value, target) {
  const previous = Array.from({ length: target.length + 1 }, (_, index) => index);
  for (let row = 1; row <= value.length; row += 1) {
    const current = [row];
    for (let column = 1; column <= target.length; column += 1) {
      current[column] = Math.min(
        current[column - 1] + 1,
        previous[column] + 1,
        previous[column - 1] + (value[row - 1] === target[column - 1] ? 0 : 1),
      );
    }
    previous.splice(0, previous.length, ...current);
  }
  return previous[target.length];
}

async function api(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function setError(message = "") {
  elements.error.textContent = message;
  elements.error.classList.toggle("hidden", !message);
}

function setRunNotice(message = "") {
  elements.runNotice.textContent = message;
  elements.runNotice.classList.toggle("hidden", !message);
}

function updateInvariantNotice() {
  const goal = elements.goal.value.trim().toUpperCase();
  if (!validMiu(goal)) {
    elements.invariantNotice.textContent =
      "Invariant watch: enter a non-empty target containing only M, I, and U.";
    return;
  }
  const iCount = [...goal].filter((character) => character === "I").length;
  elements.invariantNotice.textContent =
    iCount % 3 === 0
      ? `Invariant watch: ${goal} has ${iCount} I symbol${iCount === 1 ? "" : "s"}, so it is unreachable from MI.`
      : `Invariant watch: ${goal} is not ruled out by the modulo-3 test; a derivation is still not guaranteed.`;
}

function updateEngineStatus() {
  const provider = state.providers[elements.provider.value];
  if (!provider) return;
  const providerName =
    elements.provider.value === "typesafe" ? "TypeSafe" : "Ollama";
  const model = elements.model.value.trim() || provider.default_model;
  elements.statusText.textContent = `${providerName} · ${model}`;
}

function setBusy(busy) {
  state.busy = busy;
  elements.thinking.classList.toggle("hidden", !busy);
  elements.jevStep.disabled = busy || state.auto || state.moves.length === 0;
  elements.undo.disabled = busy || state.history.length <= 1;
  elements.reset.disabled = busy;
  elements.goal.disabled = busy || state.auto;
  elements.model.disabled = busy || state.auto;
  elements.provider.disabled = busy || state.auto;
  elements.policy.disabled = busy || state.auto;
  elements.maxSteps.disabled = busy || state.auto;
  elements.maxLength.disabled = busy || state.auto;
  elements.stagnationLimit.disabled = busy || state.auto;
  elements.exploreImpossible.disabled = busy || state.auto;
  for (const button of elements.moves.querySelectorAll("button.move")) {
    button.disabled = busy || state.auto;
  }
}

function render() {
  updateInvariantNotice();
  elements.current.textContent = state.current;
  elements.stepCount.textContent = state.history.length - 1;
  elements.lengthCount.textContent = state.current.length;
  elements.moveCount.textContent = state.moves.length;
  elements.iModulo.textContent =
    [...state.current].filter((char) => char === "I").length % 3;
  elements.autoRun.textContent = state.auto ? "Stop auto-run" : "Auto-run";
  elements.autoRun.classList.toggle("primary", state.auto);

  elements.moves.replaceChildren();
  if (!state.moves.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "No legal rewrites from this string.";
    elements.moves.append(empty);
  } else {
    for (const move of state.moves) {
      const button = document.createElement("button");
      button.className = `move${move.id === state.selectedId ? " selected" : ""}`;
      const probability = state.probabilities[move.id];
      button.innerHTML = `
        <span class="rule-number">${move.rule}</span>
        <span class="move-copy">
          <span class="move-result">${move.result}</span>
          <span class="move-detail">${move.detail}</span>
        </span>
        <span class="probability">${
          probability === undefined ? "" : `${Math.round(probability * 100)}%`
        }</span>`;
      button.disabled = state.busy || state.auto;
      button.addEventListener("click", () => {
        if (!state.busy && !state.auto) applyMove(move);
      });
      elements.moves.append(button);
    }
  }

  elements.history.replaceChildren();
  for (const entry of state.history) {
    const item = document.createElement("li");
    item.innerHTML = `<span><span class="history-value">${entry.value}</span>
      <span class="history-rule">${entry.label}</span></span>`;
    elements.history.append(item);
  }
  elements.history.scrollTop = elements.history.scrollHeight;
  setBusy(state.busy);
}

async function refreshMoves() {
  const payload = await api("/api/moves", { current: state.current });
  state.moves = payload.moves;
  state.probabilities = {};
  state.selectedId = null;
  render();
}

async function applyMove(move, source = "Manual choice") {
  if (move.result.length > SERVER_MAX_LENGTH) {
    setError(
      `That move would exceed the server limit of ${SERVER_MAX_LENGTH} characters.`,
    );
    return false;
  }
  state.current = move.result;
  state.history.push({ value: move.result, label: `${move.label} · ${source}` });
  state.selectedId = move.id;
  render();
  await refreshMoves();
  return true;
}

async function jevStep(autoMode = false) {
  if (state.busy || !state.moves.length) return false;
  const requestedCurrent = state.current;
  const goal = elements.goal.value.trim().toUpperCase();
  if (!validMiu(goal)) {
    setError("Target must contain only M, I, and U.");
    return false;
  }
  setError();
  setBusy(true);
  try {
    const payload = await api("/api/choose", {
      current: requestedCurrent,
      goal,
      provider: elements.provider.value,
      model: elements.model.value.trim(),
      policy: elements.policy.value,
      history: state.history.map((entry) => entry.value),
      max_length: Math.max(
        8,
        Math.min(SERVER_MAX_LENGTH, Number(elements.maxLength.value) || 64),
      ),
    });
    if (state.current !== requestedCurrent) {
      setRunNotice("Decision discarded because the current string changed.");
      state.auto = false;
      return false;
    }
    state.moves = payload.moves;
    state.selectedId = payload.move.id;
    state.probabilities = Object.assign(
      {},
      ...payload.rounds.map((round) => round.probabilities),
    );
    render();
    await new Promise((resolve) => setTimeout(resolve, state.auto ? 100 : 450));
    if (autoMode && !state.auto) {
      setRunNotice("Auto-run stopped.");
      return false;
    }
    if (payload.move.result.length > Number(elements.maxLength.value)) {
      setRunNotice(
        `Model move not applied: it would grow the string to ${payload.move.result.length} characters.`,
      );
      state.auto = false;
      return false;
    }
    if (
      autoMode &&
      state.history.some((entry) => entry.value === payload.move.result)
    ) {
      setRunNotice("Auto-run stopped before revisiting an earlier string.");
      state.auto = false;
      return false;
    }
    const providerName =
      payload.provider === "typesafe" ? "TypeSafe Jev" : "Local Nimble";
    const source =
      payload.policy === "guided" ? `${providerName} · guided` : `${providerName} · model only`;
    return await applyMove(payload.move, source);
  } catch (error) {
    setError(error.message);
    state.auto = false;
    render();
    return false;
  } finally {
    setBusy(false);
  }
}

async function autoRun() {
  if (state.busy && !state.auto) return;
  state.auto = !state.auto;
  if (!state.auto) {
    render();
    return;
  }
  setError();
  setRunNotice();
  const goal = elements.goal.value.trim().toUpperCase();
  const goalICount = [...goal].filter((character) => character === "I").length;
  if (goalICount % 3 === 0 && !elements.exploreImpossible.checked) {
    state.auto = false;
    setRunNotice(
      `Auto-run skipped: the modulo-3 invariant proves ${goal} is unreachable from MI. Enable exploratory auto-run to override.`,
    );
    render();
    return;
  }
  if (goalICount % 3 === 0) {
    setRunNotice(
      `Exploratory run: the modulo-3 invariant proves ${goal} is unreachable. The run will stop on its safety budgets.`,
    );
  }
  const startingStep = state.history.length - 1;
  const maxSteps = Math.max(
    1,
    Math.min(500, Number(elements.maxSteps.value) || 40),
  );
  const maxLength = Math.max(
    8,
    Math.min(SERVER_MAX_LENGTH, Number(elements.maxLength.value) || 64),
  );
  const stagnationLimit = Math.max(
    1,
    Math.min(100, Number(elements.stagnationLimit.value) || 10),
  );
  elements.maxSteps.value = maxSteps;
  elements.maxLength.value = maxLength;
  elements.stagnationLimit.value = stagnationLimit;
  let bestDistance = targetDistance(state.current, goal);
  let stagnantSteps = 0;
  render();
  while (state.auto && state.moves.length && state.current !== elements.goal.value.trim().toUpperCase()) {
    if (state.history.length - 1 - startingStep >= maxSteps) {
      setRunNotice(`Auto-run stopped after its ${maxSteps}-step budget.`);
      break;
    }
    const moved = await jevStep(true);
    if (!moved) break;
    const distance = targetDistance(state.current, goal);
    if (distance < bestDistance) {
      bestDistance = distance;
      stagnantSteps = 0;
    } else {
      stagnantSteps += 1;
    }
    if (stagnantSteps >= stagnationLimit) {
      setRunNotice(
        `Auto-run stopped after ${stagnationLimit} steps without getting closer to ${goal}.`,
      );
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, Number(elements.delay.value)));
  }
  state.auto = false;
  render();
}

elements.jevStep.addEventListener("click", () => jevStep(false));
elements.autoRun.addEventListener("click", autoRun);
elements.undo.addEventListener("click", async () => {
  if (state.history.length <= 1 || state.busy) return;
  state.history.pop();
  state.current = state.history.at(-1).value;
  setError();
  setRunNotice();
  await refreshMoves();
});
elements.reset.addEventListener("click", async () => {
  state.auto = false;
  state.current = "MI";
  state.history = [{ value: "MI", label: "Axiom" }];
  setError();
  setRunNotice();
  await refreshMoves();
});
elements.goal.addEventListener("input", () => {
  elements.goal.value = elements.goal.value.toUpperCase().replace(/[^MIU]/g, "");
  updateInvariantNotice();
});
elements.provider.addEventListener("change", () => {
  const provider = state.providers[elements.provider.value];
  if (provider) {
    elements.model.value = provider.default_model;
    updateEngineStatus();
  }
});
elements.model.addEventListener("input", updateEngineStatus);

async function boot() {
  try {
    const health = await fetch("/api/health");
    if (!health.ok) throw new Error();
    const payload = await health.json();
    state.providers = payload.providers;
    for (const option of elements.provider.options) {
      const provider = state.providers[option.value];
      option.disabled = !provider?.available;
      if (!provider?.available) option.textContent += " · not configured";
    }
    elements.provider.value = payload.default_provider;
    elements.model.value = state.providers[payload.default_provider].default_model;
    elements.status.classList.add("online");
    updateEngineStatus();
    await refreshMoves();
  } catch {
    elements.statusText.textContent = "Engine unavailable";
    setError("Could not connect to the local MIU server.");
  }
}

boot();
