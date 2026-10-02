const state = {
  current: "MI",
  history: [{ value: "MI", label: "Axiom" }],
  moves: [],
  probabilities: {},
  selectedId: null,
  busy: false,
  auto: false,
};

const $ = (id) => document.getElementById(id);
const elements = {
  current: $("currentString"),
  goal: $("goal"),
  model: $("model"),
  moves: $("moves"),
  history: $("history"),
  stepCount: $("stepCount"),
  lengthCount: $("lengthCount"),
  moveCount: $("moveCount"),
  iModulo: $("iModulo"),
  jevStep: $("jevStep"),
  autoRun: $("autoRun"),
  undo: $("undo"),
  reset: $("reset"),
  thinking: $("thinking"),
  error: $("errorBox"),
  status: $("ollamaStatus"),
  delay: $("delay"),
};

function validMiu(value) {
  return /^[MIU]+$/.test(value);
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

function setBusy(busy) {
  state.busy = busy;
  elements.thinking.classList.toggle("hidden", !busy);
  elements.jevStep.disabled = busy || state.moves.length === 0;
  elements.undo.disabled = busy || state.history.length <= 1;
  elements.reset.disabled = busy;
  elements.goal.disabled = busy || state.auto;
  elements.model.disabled = busy || state.auto;
}

function render() {
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
      button.addEventListener("click", () => applyMove(move));
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
  state.current = move.result;
  state.history.push({ value: move.result, label: `${move.label} · ${source}` });
  state.selectedId = move.id;
  render();
  await refreshMoves();
}

async function jevStep() {
  if (state.busy || !state.moves.length) return false;
  const goal = elements.goal.value.trim().toUpperCase();
  if (!validMiu(goal)) {
    setError("Target must contain only M, I, and U.");
    return false;
  }
  setError();
  setBusy(true);
  try {
    const payload = await api("/api/choose", {
      current: state.current,
      goal,
      model: elements.model.value.trim(),
      history: state.history.map((entry) => entry.value),
    });
    state.moves = payload.moves;
    state.selectedId = payload.move.id;
    state.probabilities = Object.assign(
      {},
      ...payload.rounds.map((round) => round.probabilities),
    );
    render();
    await new Promise((resolve) => setTimeout(resolve, state.auto ? 100 : 450));
    await applyMove(payload.move, "Jev");
    return true;
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
  state.auto = !state.auto;
  render();
  while (state.auto && state.moves.length && state.current !== elements.goal.value.trim().toUpperCase()) {
    const moved = await jevStep();
    if (!moved) break;
    await new Promise((resolve) => setTimeout(resolve, Number(elements.delay.value)));
  }
  state.auto = false;
  render();
}

elements.jevStep.addEventListener("click", jevStep);
elements.autoRun.addEventListener("click", autoRun);
elements.undo.addEventListener("click", async () => {
  if (state.history.length <= 1 || state.busy) return;
  state.history.pop();
  state.current = state.history.at(-1).value;
  setError();
  await refreshMoves();
});
elements.reset.addEventListener("click", async () => {
  state.auto = false;
  state.current = "MI";
  state.history = [{ value: "MI", label: "Axiom" }];
  setError();
  await refreshMoves();
});
elements.goal.addEventListener("input", () => {
  elements.goal.value = elements.goal.value.toUpperCase().replace(/[^MIU]/g, "");
});

async function boot() {
  try {
    const health = await fetch("/api/health");
    if (!health.ok) throw new Error();
    elements.status.classList.add("online");
    elements.status.lastElementChild.textContent = "Local engine ready";
    await refreshMoves();
  } catch {
    elements.status.lastElementChild.textContent = "Engine unavailable";
    setError("Could not connect to the local MIU server.");
  }
}

boot();
