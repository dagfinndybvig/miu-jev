const state = {
  system: "miu",
  initial: "MI",
  analysis: null,
  current: "MI",
  history: [{ value: "MI", label: "Axiom" }],
  moves: [],
  revision: 0,
  movesRevision: null,
  movesRequest: 0,
  probabilities: {},
  selectedId: null,
  busy: false,
  auto: false,
  autoRunId: 0,
  providers: {},
  events: [],
  nextEventId: 1,
  storageAvailable: true,
  launched: false,
  onLanding: true,
};
const SERVER_MAX_LENGTH = 8192;
const JOURNAL_KEY = "miu-decision-journal-v1";
const EXAMPLES = {
  miu: { title: "MIU", initial: "MI", goal: "MU", limit: SERVER_MAX_LENGTH },
  algebra: { title: "Algebra", initial: "2 * (x + 3) = 14", goal: "Isolate x", limit: 512 },
};

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
  journal: $("decisionJournal"),
  exportLog: $("exportLog"),
  clearLog: $("clearLog"),
  journalNotice: $("journalNotice"),
  example: $("example"),
  exampleTitle: $("exampleTitle"),
  currentLabel: $("currentLabel"),
  metricLabel: $("invariantMetricLabel"),
  equationEditor: $("equationEditor"),
  equation: $("equation"),
  loadEquation: $("loadEquation"),
  exploreSetting: $("exploreSetting"),
  landing: $("landing"),
  chooseApp: $("chooseApp"),
  landingResume: $("landingResume"),
  resumeApp: $("resumeApp"),
  launchAlgebra: $("launchAlgebra"),
  launchMiu: $("launchMiu"),
  landingNotice: $("landingNotice"),
  appStage: $("appStage"),
  appWorkspace: $("appWorkspace"),
  appJournal: $("appJournal"),
  appSettings: $("appSettings"),
  rules: $("rules"),
};

const APP_VIEWS = [elements.appStage, elements.appWorkspace, elements.appJournal, elements.appSettings];

function goalValue() {
  return state.system === "algebra" ? EXAMPLES.algebra.goal : elements.goal.value.trim().toUpperCase();
}

function goalReached() {
  return state.system === "algebra" ? Boolean(state.analysis?.solved) : state.current === goalValue();
}

function progressDistance() {
  return state.system === "algebra" ? state.analysis.progress : targetDistance(state.current, goalValue());
}

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
  if (!response.ok) {
    const error = new Error(payload.error || `HTTP ${response.status}`);
    error.decision = payload.decision;
    throw error;
  }
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

function saveJournal() {
  if (!state.storageAvailable) return;
  try {
    localStorage.setItem(JOURNAL_KEY, JSON.stringify({ schema_version: 1, events: state.events }));
  } catch {
    state.storageAvailable = false;
    setError("The decision log could not be saved locally. Export JSON before closing this page.");
  }
}

function loadJournal() {
  try {
    const stored = localStorage.getItem(JOURNAL_KEY);
    if (!stored) return;
    const journal = JSON.parse(stored);
    if (
      journal.schema_version !== 1 || !Array.isArray(journal.events) ||
      !journal.events.every((event) => Number.isSafeInteger(event.id) && event.id > 0 &&
        typeof event.type === "string" && typeof event.timestamp === "string")
    ) throw new Error("Invalid journal");
    state.events = journal.events;
    state.nextEventId = state.events.reduce((largest, event) => Math.max(largest, event.id), 0) + 1;
    const unfinishedRuns = new Map();
    for (const event of state.events) {
      if (Number.isSafeInteger(event.run_id)) {
        state.autoRunId = Math.max(state.autoRunId, event.run_id);
      }
      if (event.type === "run_started") unfinishedRuns.set(event.run_id, event);
      if (event.type === "run_stopped") unfinishedRuns.delete(event.run_id);
      if (event.status === "pending") {
        event.status = "interrupted";
        event.reason = "Page closed before the decision completed; application was not recorded.";
      }
    }
    for (const run of unfinishedRuns.values()) {
      recordEvent("run_stopped", {
        system: run.system || "miu", run_id: run.run_id, reason: "page_interrupted",
      });
    }
  } catch {
    state.storageAvailable = false;
    setError("The saved decision log could not be loaded. It has not been overwritten.");
  }
}

function recordEvent(type, details = {}) {
  const event = {
    id: state.nextEventId++, timestamp: new Date().toISOString(), system: state.system, type,
    ...details,
  };
  state.events.push(event);
  saveJournal();
  renderJournal();
  return event;
}

function finishDecision(event, status, reason) {
  event.status = status;
  event.reason = reason;
  event.completed_at = new Date().toISOString();
  saveJournal();
  renderJournal();
}

function recordDetails(event) {
  const details = document.createElement("details");
  details.className = "decision-details";
  const summary = document.createElement("summary");
  const systemName = EXAMPLES[event.system || "miu"]?.title || event.system;
  summary.textContent = `${systemName} #${event.id} ${event.type.replaceAll("_", " ")} · ${event.status || event.reason || event.timestamp}`;
  details.append(summary);
  let loaded = false;
  details.addEventListener("toggle", () => {
    if (!details.open || loaded) return;
    loaded = true;
    const metadata = document.createElement("pre");
    const { evidence, candidates, ...description } = event;
    if (evidence) {
      description.decision_summary = {
        current: evidence.current, goal: evidence.goal,
        system: evidence.system || "miu",
        provider: evidence.provider, model: evidence.model, policy: evidence.policy,
        provider_calls: evidence.provider_calls, override_count: evidence.override_count,
        elapsed_ms: evidence.elapsed_ms,
      };
    }
    metadata.textContent = JSON.stringify(description, null, 2);
    details.append(metadata);
    const moves = evidence?.moves || candidates || [];
    for (const round of evidence?.rounds || []) {
      for (const group of round.groups) {
        const heading = document.createElement("p");
        heading.textContent = `Round ${round.round}, group ${group.group}: probability within this group only. ` +
          `Raw choice: ${group.raw_choice || "none (no completed provider choice)"}. ` +
          `Advanced: ${group.winner || "none"}. Guidance override: ${group.overridden ? "yes" : "no"}. ` +
          (group.selection?.reason || group.error || "");
        details.append(heading);
        const filters = document.createElement("pre");
        filters.textContent = JSON.stringify(group.selection || {}, null, 2);
        details.append(filters);
        const table = document.createElement("table");
        const header = document.createElement("tr");
        for (const label of ["Move", "Rule / position", "Result", "Group probability"]) {
          const cell = document.createElement("th");
          cell.textContent = label;
          header.append(cell);
        }
        table.append(header);
        for (const id of group.candidates) {
          const move = moves.find((candidate) => candidate.id === id);
          const row = document.createElement("tr");
          const probability = group.probabilities[id];
          for (const value of [
            id, move ? `${move.rule} / ${move.position ?? "n/a"}` : "n/a",
            move?.result || "not recorded",
            probability === undefined ? "not supplied" : `${(probability * 100).toFixed(2)}%`,
          ]) {
            const cell = document.createElement("td");
            cell.textContent = value;
            row.append(cell);
          }
          table.append(row);
        }
        details.append(table);
      }
    }
    if (!evidence?.rounds?.length && moves.length) {
      const menu = document.createElement("pre");
      menu.textContent = JSON.stringify(moves, null, 2);
      details.append(menu);
    }
  });
  return details;
}

function renderJournal() {
  elements.journalNotice.textContent = state.storageAvailable ? "" :
    "Local log persistence is unavailable. New records remain in this page only; export JSON before closing it.";
  elements.journal.replaceChildren();
  for (const event of state.events) elements.journal.append(recordDetails(event));
}

function exportJournal() {
  const payload = {
    schema_version: 1, exported_at: new Date().toISOString(),
    system: state.system, initial: state.initial,
    current: state.current, history: state.history, events: state.events,
  };
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "formal-decision-log.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function updateInvariantNotice() {
  if (state.system === "algebra") {
    const status = state.analysis?.solved
      ? state.analysis.solution_kind === "all"
        ? "Identity: every rational x is a solution."
        : state.analysis.solution_kind === "none"
          ? "Contradiction: this equation has no solution."
          : "Solved: x is isolated."
      : "Each offered transformation preserves exactly the solution set over the rationals.";
    const omitted = state.analysis?.omitted_for_limits || 0;
    elements.invariantNotice.textContent = `${status} This is a finite, bounded rewrite menu, not all of algebra.` +
      (omitted ? ` ${omitted} transformations exceed the representation limits and are not offered.` : "");
    return;
  }
  const goal = goalValue();
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
  elements.status.classList.toggle("online", Boolean(provider?.available));
  if (!provider) {
    elements.statusText.textContent = "Engine unavailable";
    return;
  }
  const providerName =
    elements.provider.value === "typesafe" ? "TypeSafe" : "Ollama";
  const model = elements.model.value.trim() || provider.default_model;
  const availability = provider.available
    ? ""
    : ` · unavailable: ${provider.error || "not configured"}`;
  elements.statusText.textContent = `${providerName} · ${model}${availability}`;
  setBusy(state.busy);
}

function setBusy(busy) {
  state.busy = busy;
  elements.thinking.classList.toggle("hidden", !busy);
  const unavailable = !state.providers[elements.provider.value]?.available;
  const solvedAlgebra = state.system === "algebra" && goalReached();
  elements.jevStep.disabled = busy || state.auto || unavailable || solvedAlgebra || state.moves.length === 0;
  elements.launchAlgebra.disabled = busy || state.auto;
  elements.launchMiu.disabled = busy || state.auto;
  elements.chooseApp.disabled = busy || state.auto;
  elements.autoRun.disabled = !state.auto && (busy || unavailable || solvedAlgebra || state.moves.length === 0);
  elements.undo.disabled = busy || state.auto || state.history.length <= 1;
  elements.reset.disabled = busy;
  elements.clearLog.disabled = busy || state.auto;
  elements.goal.disabled = busy || state.auto || state.system === "algebra";
  elements.example.disabled = busy || state.auto;
  elements.equation.disabled = busy || state.auto;
  elements.loadEquation.disabled = busy || state.auto;
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
  const algebraMode = state.system === "algebra";
  elements.landing.classList.toggle("hidden", !state.onLanding);
  for (const view of APP_VIEWS) view.classList.toggle("hidden", state.onLanding);
  elements.landingResume.classList.toggle("hidden", !(state.launched && state.onLanding));
  elements.example.value = state.system;
  elements.exampleTitle.textContent = state.onLanding ? "Formalism" : EXAMPLES[state.system].title;
  elements.currentLabel.textContent = algebraMode ? "CURRENT EQUATION" : "CURRENT STRING";
  elements.metricLabel.textContent = algebraMode ? "PROGRESS COST" : "#I MOD 3";
  elements.equationEditor.classList.toggle("hidden", !algebraMode);
  elements.exploreSetting.classList.toggle("hidden", algebraMode);
  elements.maxLength.max = EXAMPLES[state.system].limit;
  elements.rules.replaceChildren();
  const rules = algebraMode ? state.analysis?.rules || [] :
    ["1: xI → xIU", "2: Mx → Mxx", "3: xIIIy → xUy", "4: xUUy → xy"];
  for (const rule of rules) {
    const item = document.createElement("span");
    item.textContent = rule;
    elements.rules.append(item);
  }
  updateInvariantNotice();
  elements.current.textContent = state.current;
  elements.stepCount.textContent = state.history.length - 1;
  elements.lengthCount.textContent = state.current.length;
  elements.moveCount.textContent = state.moves.length;
  elements.iModulo.textContent = algebraMode ? state.analysis?.progress ?? "—" :
    [...state.current].filter((char) => char === "I").length % 3;
  elements.autoRun.textContent = state.auto ? "Stop auto-run" : "Auto-run";
  elements.autoRun.classList.toggle("primary", state.auto);

  elements.moves.replaceChildren();
  if (!state.moves.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "No legal rewrites from this state.";
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
          probability === undefined ? "" : `${Math.round(probability * 100)}% in group`
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
    const event = state.events.find((candidate) => candidate.id === entry.eventId);
    if (event) item.append(recordDetails(event));
    elements.history.append(item);
  }
  elements.history.scrollTop = elements.history.scrollHeight;
  renderJournal();
  setBusy(state.busy);
}

async function refreshMoves() {
  const revision = state.revision;
  const system = state.system;
  const request = ++state.movesRequest;
  state.moves = [];
  state.movesRevision = null;
  state.probabilities = {};
  state.selectedId = null;
  state.analysis = null;
  render();
  const payload = await api("/api/moves", { system, current: state.current });
  if (revision !== state.revision || request !== state.movesRequest || system !== state.system) return false;
  state.moves = payload.moves;
  state.analysis = system === "algebra" ? payload : null;
  state.movesRevision = revision;
  render();
  return true;
}

async function loadExample(system, equation = EXAMPLES[system]?.initial) {
  if (state.busy || state.auto) {
    elements.example.value = state.system;
    setError("Stop the run and wait for the current operation before changing examples.");
    return false;
  }
  if (!Object.hasOwn(EXAMPLES, system)) {
    setError("Unknown example.");
    return false;
  }
  setError();
  setBusy(true);
  try {
    const payload = await api("/api/moves", { system, current: equation });
    const initial = payload.current;
    stopAutoRun("example_changed");
    recordEvent("example_loaded", {
      system, previous_system: state.system, previous_current: state.current,
      input: equation, initial,
    });
    state.system = system;
    state.initial = initial;
    state.current = initial;
    state.history = [{ value: initial, label: system === "miu" ? "Axiom" : "Starting equation" }];
    state.revision += 1;
    state.movesRequest += 1;
    state.moves = payload.moves;
    state.movesRevision = state.revision;
    state.analysis = system === "algebra" ? payload : null;
    state.probabilities = {};
    state.selectedId = null;
    elements.goal.value = EXAMPLES[system].goal;
    elements.equation.value = system === "algebra" ? initial : EXAMPLES.algebra.initial;
    elements.maxLength.value = Math.max(8, Math.min(EXAMPLES[system].limit, Number(elements.maxLength.value) || 64));
    setRunNotice();
    return true;
  } catch (error) {
    setError(error.message);
    recordEvent("example_rejected", { requested_system: system, reason: error.message });
    return false;
  } finally {
    setBusy(false);
    render();
  }
}

function stopAutoRun(reason = "stopped") {
  if (state.auto) recordEvent("run_stopped", {
    run_id: state.autoRunId, current: state.current, reason,
  });
  state.auto = false;
  state.autoRunId += 1;
}

async function setHistory(history, appliedEvent = null, reason = "") {
  const wasBusy = state.busy;
  setBusy(true);
  state.history = history;
  state.current = history.at(-1).value;
  state.revision += 1;
  if (appliedEvent) finishDecision(appliedEvent, "applied", reason);
  try {
    return await refreshMoves();
  } catch (error) {
    setError(error.message);
    recordEvent("menu_error", { current: state.current, reason: error.message });
    stopAutoRun("menu_error");
    return false;
  } finally {
    setBusy(wasBusy);
    render();
  }
}

async function applyMove(move, source = "Manual choice", decision = null) {
  const event = decision || recordEvent("manual_move", {
    current: state.current, goal: goalValue(),
    candidates: state.moves, move,
  });
  if (state.movesRevision !== state.revision || !state.moves.includes(move)) {
    setError("Move discarded because its legal menu is no longer current.");
    finishDecision(event, "rejected", "stale_menu");
    return false;
  }
  if (move.result.length > EXAMPLES[state.system].limit) {
    setError(
      `That move would exceed the server limit of ${EXAMPLES[state.system].limit} characters.`,
    );
    finishDecision(event, "rejected", "server_length_limit");
    return false;
  }
  setError();
  event.applied_move = move;
  return setHistory([
    ...state.history,
    { value: move.result, label: `${move.label} · ${source}`, eventId: event.id },
  ], event, source);
}

async function jevStep(runId = null) {
  const autoMode = runId !== null;
  if (state.busy || !state.moves.length || (state.auto && !autoMode)) return false;
  if (state.system === "algebra" && goalReached()) return false;
  if (!state.providers[elements.provider.value]?.available) {
    updateEngineStatus();
    return false;
  }
  const requestedCurrent = state.current;
  const requestedRevision = state.revision;
  const requestedSystem = state.system;
  const goal = goalValue();
  if (state.system === "miu" && !validMiu(goal)) {
    setError("Target must contain only M, I, and U.");
    return false;
  }
  setError();
  setBusy(true);
  const request = {
    system: requestedSystem, current: requestedCurrent, goal, provider: elements.provider.value,
    model: elements.model.value.trim(), policy: elements.policy.value,
    history: state.history.map((entry) => entry.value),
    max_length: Math.max(8, Math.min(EXAMPLES[state.system].limit, Number(elements.maxLength.value) || 64)),
  };
  const decision = recordEvent("decision", {
    status: "pending", run_id: runId, request, candidates: state.moves,
  });
  try {
    const payload = await api("/api/choose", request);
    decision.evidence = payload;
    delete decision.candidates;
    saveJournal();
    if (autoMode && (!state.auto || state.autoRunId !== runId)) {
      finishDecision(decision, "rejected", "run_cancelled");
      return false;
    }
    if (state.system !== requestedSystem || state.revision !== requestedRevision || state.current !== requestedCurrent) {
      setRunNotice("Decision discarded because the current state changed.");
      finishDecision(decision, "rejected", "state_changed");
      stopAutoRun("state_changed");
      return false;
    }
    state.moves = payload.moves;
    if (state.system === "algebra") state.analysis = payload.analysis;
    state.movesRevision = requestedRevision;
    state.selectedId = payload.move.id;
    state.probabilities = payload.rounds.length === 1 && payload.rounds[0].groups.length === 1
      ? payload.rounds[0].groups[0].probabilities : {};
    render();
    await new Promise((resolve) => setTimeout(resolve, state.auto ? 100 : 450));
    if (autoMode && (!state.auto || state.autoRunId !== runId)) {
      finishDecision(decision, "rejected", "run_cancelled");
      return false;
    }
    if (state.system !== requestedSystem || state.revision !== requestedRevision || state.current !== requestedCurrent) {
      setRunNotice("Decision discarded because the current state changed.");
      finishDecision(decision, "rejected", "state_changed");
      stopAutoRun("state_changed");
      return false;
    }
    if (payload.move.result.length > Number(elements.maxLength.value)) {
      setRunNotice(
        `Model move not applied: the next state would have ${payload.move.result.length} characters.`,
      );
      finishDecision(decision, "rejected", "length_budget");
      stopAutoRun("length_budget");
      return false;
    }
    if (
      autoMode &&
      state.history.some((entry) => entry.value === payload.move.result)
    ) {
      setRunNotice("Auto-run stopped before revisiting an earlier state.");
      finishDecision(decision, "rejected", "cycle");
      stopAutoRun("cycle");
      return false;
    }
    const providerName =
      payload.provider === "typesafe" ? "TypeSafe Jev" : "Local Nimble";
    const source =
      payload.policy === "guided" ? `${providerName} · guided` : `${providerName} · model only`;
    const move = state.moves.find((candidate) => candidate.id === payload.move.id);
    if (!move) throw new Error("Decision returned a move outside the legal menu.");
    return await applyMove(move, source, decision);
  } catch (error) {
    if (error.decision) {
      decision.evidence = error.decision;
      delete decision.candidates;
    }
    finishDecision(decision, "error", error.message);
    setError(error.message);
    stopAutoRun("api_error");
    render();
    return false;
  } finally {
    setBusy(false);
    render();
  }
}

async function autoRun() {
  if (state.busy && !state.auto) return;
  if (state.auto) {
    stopAutoRun("user_stop");
    setRunNotice("Auto-run stopped.");
    render();
    return;
  }
  if (!state.providers[elements.provider.value]?.available || !state.moves.length) return;
  if (state.system === "algebra" && goalReached()) return;
  state.auto = true;
  const runId = ++state.autoRunId;
  setError();
  setRunNotice();
  const goal = goalValue();
  if (state.system === "miu" && !validMiu(goal)) {
    recordEvent("run_rejected", { goal, reason: "invalid_target" });
    stopAutoRun("invalid_target");
    setError("Target must contain only M, I, and U.");
    render();
    return;
  }
  const goalICount = [...goal].filter((character) => character === "I").length;
  const impossible = state.system === "miu" && goalICount % 3 === 0;
  if (impossible && !elements.exploreImpossible.checked) {
    recordEvent("run_rejected", { goal, reason: "invariant_impossible" });
    stopAutoRun("invariant_impossible");
    setRunNotice(
      `Auto-run skipped: the modulo-3 invariant proves ${goal} is unreachable from MI. Enable exploratory auto-run to override.`,
    );
    render();
    return;
  }
  if (impossible) {
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
    Math.min(EXAMPLES[state.system].limit, Number(elements.maxLength.value) || 64),
  );
  const stagnationLimit = Math.max(
    1,
    Math.min(100, Number(elements.stagnationLimit.value) || 10),
  );
  elements.maxSteps.value = maxSteps;
  elements.maxLength.value = maxLength;
  elements.stagnationLimit.value = stagnationLimit;
  let bestDistance = progressDistance();
  let stagnantSteps = 0;
  recordEvent("run_started", {
    run_id: runId, current: state.current, goal,
    provider: elements.provider.value, model: elements.model.value.trim(),
    policy: elements.policy.value,
    budgets: { max_steps: maxSteps, max_length: maxLength, stagnation_limit: stagnationLimit },
    exploratory: impossible,
  });
  let stopReason = "no_moves";
  render();
  while (state.auto && state.moves.length && !goalReached()) {
    if (state.history.length - 1 - startingStep >= maxSteps) {
      setRunNotice(`Auto-run stopped after its ${maxSteps}-step budget.`);
      stopReason = "step_budget";
      break;
    }
    const moved = await jevStep(runId);
    if (state.autoRunId !== runId) return;
    if (!moved) {
      stopReason = "decision_not_applied";
      break;
    }
    if (goalReached()) {
      stopReason = "target_reached";
      break;
    }
    const distance = progressDistance();
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
      stopReason = "stagnation";
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, Number(elements.delay.value)));
    if (state.autoRunId !== runId) return;
  }
  if (goalReached()) stopReason = "target_reached";
  stopAutoRun(stopReason);
  render();
}

function showLanding() {
  if (state.busy || state.auto || !state.launched) return;
  setError();
  setRunNotice();
  state.onLanding = true;
  render();
}

function resumeCurrentApp() {
  if (!state.launched) return;
  state.onLanding = false;
  render();
}

async function launchApp(system) {
  if (state.busy || state.auto || !Object.hasOwn(EXAMPLES, system)) return;
  setError();
  elements.landingNotice.textContent = "";
  elements.landingNotice.classList.add("hidden");
  const loaded = await loadExample(system);
  if (loaded) {
    state.launched = true;
    state.onLanding = false;
  } else {
    elements.landingNotice.textContent =
      elements.error.textContent || "The selected example could not be loaded.";
    elements.landingNotice.classList.remove("hidden");
  }
  render();
}

elements.launchAlgebra.addEventListener("click", () => launchApp("algebra"));
elements.launchMiu.addEventListener("click", () => launchApp("miu"));
elements.chooseApp.addEventListener("click", showLanding);
elements.resumeApp.addEventListener("click", resumeCurrentApp);
elements.jevStep.addEventListener("click", () => jevStep());
elements.autoRun.addEventListener("click", autoRun);
elements.undo.addEventListener("click", async () => {
  if (state.history.length <= 1 || state.busy || state.auto) return;
  stopAutoRun("undo");
  recordEvent("undo", { current: state.current, removed: state.history.at(-1) });
  setError();
  setRunNotice();
  await setHistory(state.history.slice(0, -1));
});
elements.reset.addEventListener("click", async () => {
  if (state.busy) return;
  stopAutoRun("reset");
  recordEvent("reset", { current: state.current, history: state.history });
  setError();
  setRunNotice();
  await setHistory([{
    value: state.initial, label: state.system === "miu" ? "Axiom" : "Starting equation",
  }]);
});
elements.goal.addEventListener("input", () => {
  if (state.system !== "miu") return;
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
elements.example.addEventListener("change", () => loadExample(elements.example.value));
elements.loadEquation.addEventListener("click", () => loadExample("algebra", elements.equation.value));
elements.exportLog.addEventListener("click", exportJournal);
elements.clearLog.addEventListener("click", () => {
  if (state.busy || state.auto) {
    setError("Stop the run and wait for the current operation before clearing the log.");
    return;
  }
  try {
    localStorage.removeItem(JOURNAL_KEY);
    state.events = [];
    state.storageAvailable = true;
    setError();
    render();
  } catch {
    setError("The saved decision log could not be cleared.");
  }
});

async function boot() {
  loadJournal();
  recordEvent("session_started", { current: state.current });
  setBusy(true);
  try {
    const health = await fetch("/api/health");
    if (!health.ok) throw new Error();
    const payload = await health.json();
    state.providers = payload.providers;
    for (const option of elements.provider.options) {
      const provider = state.providers[option.value];
      option.disabled = !provider?.available;
      if (!provider?.available) option.textContent += " · unavailable";
    }
    elements.provider.value = payload.default_provider;
    elements.model.value = state.providers[payload.default_provider].default_model;
    updateEngineStatus();
  } catch {
    elements.status.classList.remove("online");
    elements.statusText.textContent = "Engine unavailable";
    setError("Could not connect to the local MIU server.");
  }
  try {
    await refreshMoves();
  } catch (error) {
    setError(error.message);
  } finally {
    setBusy(false);
    render();
  }
}

boot();
