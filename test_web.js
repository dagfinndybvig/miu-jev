const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "web", "app.js"), "utf8");
const settle = () => new Promise(setImmediate);
const providers = {
  ollama: { available: true, default_model: "nimble:latest" },
  typesafe: { available: true, default_model: "jev-latest" },
};

function legalMenu(current) {
  const successors = {
    MI: [[1, "MIU"], [2, "MII"]],
    MIU: [[2, "MIUIU"]],
    MII: [[1, "MIIU"], [2, "MIIII"]],
    MIIII: [[1, "MIIIIU"], [2, "MIIIIIIII"], [3, "MUI"], [3, "MIU"]],
    MUI: [[1, "MUIU"], [2, "MUIUI"]],
    MUUII: [[1, "MUUIIU"], [2, "MUUIIUUII"], [4, "MII"]],
  };
  assert.ok(successors[current], `Missing fixture for ${current}`);
  return successors[current].map(([rule, result], index) => ({
    id: `move-${index}`, rule, result, label: `Rule ${rule}`, detail: "Legal move",
  }));
}

function element() {
  const classes = new Set();
  const listeners = new Map();
  return {
    value: "", textContent: "", children: [], options: [], disabled: false,
    checked: true, listeners,
    classList: {
      add(name) { classes.add(name); },
      remove(name) { classes.delete(name); },
      contains(name) { return classes.has(name); },
      toggle(name, enabled) {
        if (enabled) classes.add(name);
        else classes.delete(name);
      },
    },
    replaceChildren() { this.children = []; },
    append(child) { this.children.push(child); },
    querySelectorAll() {
      return this.children.filter((child) => child.className?.split(" ").includes("move"));
    },
    addEventListener(name, listener) { listeners.set(name, listener); },
    click() { if (!this.disabled) return listeners.get("click")?.(); },
  };
}

async function createApp(healthProviders = providers, storage = new Map()) {
  const nodes = new Map();
  const requests = [];
  const timers = [];
  const downloads = [];
  const context = vm.createContext({
    localStorage: {
      getItem(key) { return storage.get(key) ?? null; },
      setItem(key, value) { storage.set(key, value); },
      removeItem(key) { storage.delete(key); },
    },
    Blob,
    URL: {
      createObjectURL(blob) { downloads.push(blob); return "blob:test"; },
      revokeObjectURL() {},
    },
    document: {
      getElementById(id) {
        if (!nodes.has(id)) nodes.set(id, element());
        return nodes.get(id);
      },
      createElement: element,
    },
    fetch(url, options) {
      return new Promise((resolve, reject) => {
        requests.push({
          url, body: options ? JSON.parse(options.body) : null, reject,
          respond(payload, ok = true) { resolve({ ok, json: async () => payload }); },
        });
      });
    },
    setTimeout(callback, delay) { timers.push({ callback, delay }); },
  });
  const run = (code) => vm.runInContext(code, context);
  vm.runInContext(source, context);
  for (const [id, value] of Object.entries({
    goal: "MU", maxLength: "64", maxSteps: "2", stagnationLimit: "100",
    delay: "750", provider: "ollama", model: "nimble:latest", policy: "guided",
  })) nodes.get(id).value = value;
  nodes.get("provider").options = [
    { value: "ollama", textContent: "Ollama" },
    { value: "typesafe", textContent: "TypeSafe" },
  ];
  requests.shift().respond({ default_provider: "ollama", providers: healthProviders });
  await settle();
  requests.shift().respond({ moves: legalMenu("MI") });
  await settle();
  return {
    nodes, requests, timers, run, storage, downloads,
    get state() { return run("state"); },
    async movesResponse() {
      const request = requests.shift();
      assert.equal(request.url, "/api/moves");
      request.respond({ moves: legalMenu(request.body.current) });
      await settle();
    },
    async fireTimer(delay) {
      const index = timers.findIndex((timer) => timer.delay === delay);
      assert.notEqual(index, -1, `Missing ${delay}ms timer`);
      timers.splice(index, 1)[0].callback();
      await settle();
    },
    async decisionResponse(index) {
      const request = requests.shift();
      assert.equal(request.url, "/api/choose");
      const moves = legalMenu(request.body.current);
      request.respond({
        moves, move: moves[index], provider: request.body.provider,
        policy: request.body.policy, rounds: [{ round: 1, groups: [{
          group: 1, candidates: moves.map((move) => move.id),
          requested: true, raw_choice: moves[index].id, winner: moves[index].id,
          overridden: false, probabilities: { [moves[index].id]: 1 },
          selection: { reason: "Provider choice preserved.", filters: [], scores: {} },
        }] }],
      });
      await settle();
    },
    async completeDecision(index) {
      await this.decisionResponse(index);
      await this.fireTimer(100);
      await this.movesResponse();
    },
  };
}

test("manual moves lock transitions and reject obsolete menu entries", async () => {
  const app = await createApp();
  const [append, duplicate] = app.nodes.get("moves").children;
  const obsoleteMove = app.state.moves[1];
  append.click();
  assert.equal(app.state.current, "MIU");
  assert.equal(app.state.busy, true);
  assert.equal(duplicate.disabled, true);
  duplicate.listeners.get("click")();
  assert.equal(app.requests.length, 1);
  assert.equal(app.state.history.length, 2);
  assert.equal(app.state.moves.length, 0);
  await app.movesResponse();
  assert.equal(app.state.busy, false);
  assert.equal(app.state.moves[0].result, "MIUIU");
  app.run(`applyMove(${JSON.stringify(obsoleteMove)})`);
  assert.equal(app.state.current, "MIU");
  assert.match(app.nodes.get("errorBox").textContent, /no longer current/);
});

test("out-of-order refreshes cannot overwrite the current legal menu", async () => {
  const app = await createApp();
  app.run("refreshMoves(); refreshMoves();");
  const older = app.requests.splice(0);
  app.run("setHistory([{value:'MIU',label:'test'}])");
  await app.movesResponse();
  for (const request of older.reverse()) {
    request.respond({ moves: legalMenu("MI") });
    await settle();
  }
  assert.equal(app.state.current, "MIU");
  assert.equal(app.state.moves.length, 1);
  assert.equal(app.state.moves[0].result, "MIUIU");
});

test("latest refresh wins even when the source revision is unchanged", async () => {
  const app = await createApp();
  app.run("refreshMoves(); refreshMoves();");
  const [first, last] = app.requests.splice(0);
  last.respond({ moves: legalMenu("MI") });
  await settle();
  first.respond({ moves: [] });
  await settle();
  assert.equal(app.state.moves.length, 2);
});

test("failed refresh is surfaced and reset can recover without stale moves", async () => {
  const app = await createApp();
  app.nodes.get("moves").children[1].click();
  app.requests.shift().reject(new Error("Move service unavailable"));
  await settle();
  assert.equal(app.state.current, "MII");
  assert.equal(app.state.busy, false);
  assert.equal(app.state.moves.length, 0);
  assert.match(app.nodes.get("errorBox").textContent, /Move service unavailable/);
  app.nodes.get("reset").click();
  await app.movesResponse();
  assert.equal(app.state.current, "MI");
  assert.equal(app.state.history.length, 1);
  assert.equal(app.state.moves.length, 2);
});

test("undo locks manual moves and reset while its replacement menu loads", async () => {
  const app = await createApp();
  app.nodes.get("moves").children[1].click();
  await app.movesResponse();
  const oldButton = app.nodes.get("moves").children[1];
  app.nodes.get("undo").click();
  assert.equal(app.nodes.get("reset").disabled, true);
  oldButton.listeners.get("click")();
  assert.equal(app.requests.length, 1);
  await app.movesResponse();
  assert.equal(app.state.current, "MI");
  assert.equal(app.state.history.length, 1);
});

test("a stopped run's delay cannot cancel or advance a restarted run", async () => {
  const app = await createApp();
  const firstRun = app.run("autoRun()");
  await app.completeDecision(1);
  assert.equal(app.state.current, "MII");
  assert.equal(app.nodes.get("undo").disabled, true);
  await app.run("autoRun()");
  const secondRun = app.run("autoRun()");
  await app.completeDecision(1);
  assert.equal(app.state.current, "MIIII");
  await app.fireTimer(750);
  await firstRun;
  assert.equal(app.state.auto, true);
  assert.equal(app.requests.length, 0);
  await app.fireTimer(750);
  await app.completeDecision(2);
  await app.fireTimer(750);
  await secondRun;
  assert.equal(app.state.current, "MUI");
  assert.equal(app.state.history.length, 4);
  assert.equal(app.state.auto, false);
  assert.match(app.nodes.get("runNotice").textContent, /2-step budget/);
});

test("stopping during a provider request or animation never applies its move", async () => {
  for (const duringAnimation of [false, true]) {
    const app = await createApp();
    const run = app.run("autoRun()");
    if (duringAnimation) await app.decisionResponse(1);
    await app.run("autoRun()");
    if (duringAnimation) await app.fireTimer(100);
    else await app.decisionResponse(1);
    await run;
    assert.equal(app.state.current, "MI");
    assert.equal(app.state.auto, false);
    assert.equal(app.state.busy, false);
    assert.equal(app.requests.length, 0);
  }
});

test("reset invalidates a sleeping run", async () => {
  const app = await createApp();
  const run = app.run("autoRun()");
  await app.completeDecision(1);
  app.nodes.get("reset").click();
  await app.movesResponse();
  await app.fireTimer(750);
  await run;
  assert.equal(app.state.current, "MI");
  assert.equal(app.state.auto, false);
  assert.equal(app.requests.length, 0);
});

test("decisions are revision-bound before and after their animation", async () => {
  for (const duringAnimation of [false, true]) {
    const app = await createApp();
    const step = app.run("jevStep()");
    if (duringAnimation) await app.decisionResponse(1);
    app.run("state.revision += 2");
    if (duringAnimation) await app.fireTimer(450);
    else await app.decisionResponse(1);
    await step;
    assert.equal(app.state.current, "MI");
    assert.equal(app.state.history.length, 1);
    assert.match(app.nodes.get("runNotice").textContent, /current string changed/);
  }
});

test("one-step decisions retain probabilities, source labels, and legal successors", async () => {
  for (const [provider, label] of [["ollama", "Local Nimble"], ["typesafe", "TypeSafe Jev"]]) {
    const app = await createApp();
    app.nodes.get("provider").value = provider;
    app.nodes.get("provider").listeners.get("change")();
    app.nodes.get("policy").value = "model";
    const step = app.run("jevStep()");
    await app.decisionResponse(1);
    assert.equal(app.state.probabilities["move-1"], 1);
    await app.fireTimer(450);
    await app.movesResponse();
    assert.equal(await step, true);
    assert.equal(app.state.current, "MII");
    assert.ok(app.state.history[1].label.includes(`${label} · model only`));
    assert.equal(app.state.moves[1].result, "MIIII");
  }
});

test("auto-run preserves invariant preflight, target stopping, and stagnation limits", async () => {
  const preflight = await createApp();
  preflight.nodes.get("exploreImpossible").checked = false;
  await preflight.run("autoRun()");
  assert.equal(preflight.requests.length, 0);
  assert.equal(preflight.state.auto, false);
  assert.match(preflight.nodes.get("runNotice").textContent, /unreachable/);

  const goal = await createApp();
  goal.nodes.get("goal").value = "MII";
  const goalRun = goal.run("autoRun()");
  await goal.completeDecision(1);
  await goalRun;
  assert.equal(goal.state.current, "MII");
  assert.equal(goal.state.auto, false);
  assert.equal(goal.requests.length, 0);

  const stagnant = await createApp();
  stagnant.nodes.get("stagnationLimit").value = "1";
  const stagnantRun = stagnant.run("autoRun()");
  await stagnant.completeDecision(1);
  await stagnantRun;
  assert.equal(stagnant.state.auto, false);
  assert.match(stagnant.nodes.get("runNotice").textContent, /without getting closer/);
});

test("auto-run rejects over-budget and repeated successors before committing", async () => {
  for (const scenario of [
    { history: ["MI", "MII", "MIIII"], choice: 1, length: "8", notice: /grow the string/ },
    {
      history: ["MI", "MII", "MIIII", "MIIIIIIII", "MUIIIII", "MUUII"],
      choice: 2, length: "64", notice: /revisiting/,
    },
  ]) {
    const app = await createApp();
    const history = scenario.history.map((value) => ({ value, label: "test" }));
    const transition = app.run(`setHistory(${JSON.stringify(history)})`);
    await app.movesResponse();
    await transition;
    app.nodes.get("maxLength").value = scenario.length;
    const run = app.run("autoRun()");
    await app.decisionResponse(scenario.choice);
    await app.fireTimer(100);
    await run;
    assert.equal(app.state.history.length, history.length);
    assert.equal(app.state.current, history.at(-1).value);
    assert.equal(app.state.auto, false);
    assert.equal(app.requests.length, 0);
    assert.match(app.nodes.get("runNotice").textContent, scenario.notice);
  }
});

test("auto-run stops and surfaces API failures without changing the derivation", async () => {
  const app = await createApp();
  const run = app.run("autoRun()");
  app.requests.shift().reject(new Error("Provider unavailable"));
  await run;
  assert.equal(app.state.auto, false);
  assert.equal(app.state.busy, false);
  assert.equal(app.state.history.length, 1);
  assert.match(app.nodes.get("errorBox").textContent, /Provider unavailable/);
});

test("unavailable local provider stays selected until explicit hosted opt-in", async () => {
  const app = await createApp({
    ...providers,
    ollama: { ...providers.ollama, available: false, error: "Ollama 0.35.0 or later is required" },
  });
  assert.equal(app.nodes.get("provider").value, "ollama");
  assert.equal(app.nodes.get("engineStatus").classList.contains("online"), false);
  assert.match(app.nodes.get("engineStatusText").textContent, /0.35.0 or later/);
  assert.equal(app.nodes.get("jevStep").disabled, true);
  assert.equal(app.nodes.get("autoRun").disabled, true);
  assert.equal(app.nodes.get("moves").children[0].disabled, false);
  app.nodes.get("provider").value = "typesafe";
  app.nodes.get("provider").listeners.get("change")();
  assert.equal(app.nodes.get("model").value, "jev-latest");
  assert.equal(app.nodes.get("engineStatus").classList.contains("online"), true);
  assert.equal(app.nodes.get("jevStep").disabled, false);
  app.nodes.get("model").value = "custom-model";
  app.nodes.get("model").listeners.get("input")();
  assert.match(app.nodes.get("engineStatusText").textContent, /TypeSafe.*custom-model/);
});

test("both unavailable providers leave manual exploration enabled", async () => {
  const app = await createApp({
    ollama: { ...providers.ollama, available: false, error: "Could not reach Ollama" },
    typesafe: { ...providers.typesafe, available: false },
  });
  assert.equal(app.nodes.get("engineStatus").classList.contains("online"), false);
  assert.equal(app.nodes.get("provider").options[1].disabled, true);
  app.nodes.get("moves").children[1].click();
  await app.movesResponse();
  assert.equal(app.state.current, "MII");
});

test("decision evidence survives refresh, undo, reset, reload, and JSON export", async () => {
  const app = await createApp();
  const step = app.run("jevStep()");
  await app.decisionResponse(1);
  await app.fireTimer(450);
  await app.movesResponse();
  await step;
  const event = app.state.events.find((item) => item.type === "decision");
  assert.equal(event.status, "applied");
  assert.equal(event.request.current, "MI");
  assert.equal(event.evidence.moves.length, 2);
  assert.equal(event.evidence.rounds[0].groups[0].raw_choice, "move-1");
  assert.equal(event.applied_move.result, "MII");
  assert.equal(app.state.history[1].eventId, event.id);
  assert.equal(app.nodes.get("history").children[1].children[0].className, "decision-details");
  app.nodes.get("undo").click();
  await app.movesResponse();
  app.nodes.get("reset").click();
  await app.movesResponse();
  assert.equal(event.status, "applied");
  assert.ok(app.state.events.some((item) => item.type === "undo"));
  assert.ok(app.state.events.some((item) => item.type === "reset"));
  const restored = await createApp(providers, app.storage);
  const savedEvent = restored.state.events.find((item) => item.id === event.id);
  assert.equal(savedEvent.evidence.rounds[0].groups[0].winner, "move-1");
  assert.equal(restored.state.current, "MI");
  restored.nodes.get("exportLog").click();
  const exported = JSON.parse(await restored.downloads[0].text());
  assert.equal(exported.schema_version, 1);
  assert.equal(exported.events.length, restored.state.events.length);
  assert.equal(exported.events.find((item) => item.id === event.id).applied_move.result, "MII");
});

test("tournament probabilities remain group-local in display and export", async () => {
  const app = await createApp();
  const step = app.run("jevStep()");
  const moves = legalMenu("MI");
  const group = (number, probability, winner) => ({
    group: number, candidates: ["move-0", "move-1"], raw_choice: winner,
    winner, requested: true, overridden: false,
    probabilities: { "move-0": probability, "move-1": 1 - probability },
    selection: { reason: "Provider choice preserved.", filters: [], scores: {} },
  });
  app.requests.shift().respond({
    moves, move: moves[1], provider: "ollama", policy: "model",
    rounds: [
      { round: 1, groups: [group(1, 0.8, "move-0"), group(2, 0.3, "move-1")] },
      { round: 2, groups: [group(1, 0.1, "move-1")] },
    ],
  });
  await settle();
  assert.equal(Object.keys(app.state.probabilities).length, 0);
  const event = app.state.events.find((item) => item.type === "decision");
  const details = app.nodes.get("decisionJournal").children.at(-1);
  details.open = true;
  details.listeners.get("toggle")();
  const headings = details.children.filter((child) => child.textContent.startsWith("Round "));
  assert.equal(headings.length, 3);
  assert.ok(headings.every((heading) => heading.textContent.includes("within this group only")));
  await app.fireTimer(450);
  await app.movesResponse();
  await step;
  app.nodes.get("exportLog").click();
  const exported = JSON.parse(await app.downloads[0].text());
  const rounds = exported.events.find((item) => item.id === event.id).evidence.rounds;
  assert.equal(rounds[0].groups[0].probabilities["move-0"], 0.8);
  assert.equal(rounds[0].groups[1].probabilities["move-0"], 0.3);
  assert.equal(rounds[1].groups[0].probabilities["move-0"], 0.1);
});

test("cancelled decisions and stop reasons are retained without applied moves", async () => {
  const app = await createApp();
  const run = app.run("autoRun()");
  await app.run("autoRun()");
  await app.decisionResponse(1);
  await run;
  const decision = app.state.events.find((item) => item.type === "decision");
  assert.equal(decision.status, "rejected");
  assert.equal(decision.reason, "run_cancelled");
  assert.equal(decision.applied_move, undefined);
  assert.ok(app.state.events.some((item) => item.type === "run_stopped" && item.reason === "user_stop"));
});

test("failed provider decisions retain partial server evidence", async () => {
  const app = await createApp();
  const step = app.run("jevStep()");
  app.requests.shift().respond({
    error: "Provider request timed out",
    decision: { moves: legalMenu("MI"), rounds: [], provider_calls: 1 },
  }, false);
  await step;
  const event = app.state.events.find((item) => item.type === "decision");
  assert.equal(event.status, "error");
  assert.equal(event.evidence.provider_calls, 1);
  assert.match(event.reason, /timed out/);
});

test("reloading an unfinished decision records interruption, not success", async () => {
  const app = await createApp();
  app.run("jevStep()");
  const restored = await createApp(providers, app.storage);
  const event = restored.state.events.find((item) => item.type === "decision");
  assert.equal(event.status, "interrupted");
  assert.equal(event.applied_move, undefined);
  assert.equal(restored.state.current, "MI");
});

test("reload closes unfinished runs and does not reuse their run IDs", async () => {
  const app = await createApp();
  app.run("autoRun()");
  await app.completeDecision(1);
  const oldRunId = app.state.autoRunId;
  const restored = await createApp(providers, app.storage);
  assert.ok(restored.state.events.some((event) =>
    event.type === "run_stopped" && event.run_id === oldRunId && event.reason === "page_interrupted"));
  const run = restored.run("autoRun()");
  assert.ok(restored.state.autoRunId > oldRunId);
  await restored.run("autoRun()");
  await restored.decisionResponse(1);
  await run;
});

test("storage failures leave an explicit persistent warning and exportable in-memory log", async () => {
  const storage = new Map();
  storage.set = () => { throw new Error("Quota exceeded"); };
  const app = await createApp(providers, storage);
  app.nodes.get("moves").children[1].click();
  await app.movesResponse();
  assert.equal(app.state.storageAvailable, false);
  assert.match(app.nodes.get("journalNotice").textContent, /persistence is unavailable/);
  app.nodes.get("exportLog").click();
  const exported = JSON.parse(await app.downloads[0].text());
  assert.ok(exported.events.some((item) => item.type === "manual_move"));
});

test("corrupt saved logs are not silently overwritten; explicit clear leaves derivation intact", async () => {
  const storage = new Map([["miu-decision-journal-v1", "not JSON"]]);
  const app = await createApp(providers, storage);
  assert.equal(storage.get("miu-decision-journal-v1"), "not JSON");
  assert.equal(app.state.storageAvailable, false);
  app.nodes.get("moves").children[1].click();
  await app.movesResponse();
  app.nodes.get("clearLog").click();
  assert.equal(app.state.events.length, 0);
  assert.equal(app.state.current, "MII");
  assert.equal(app.state.history.length, 2);
  assert.equal(app.state.storageAvailable, true);
  assert.equal(storage.has("miu-decision-journal-v1"), false);
});
