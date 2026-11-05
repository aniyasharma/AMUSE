const state = {
  signedIn: false,
  authMode: "signin",
  useSpotify: false,
  hasTaste: false,
  genres: [],
  artists: [],
  songs: [],
  chosenGenres: new Set(),
  chosenArtists: new Set(),
  chosenSongs: new Set(),
  question: 0,
  answers: Array(10).fill(null),
  questions: [],
  choiceLabels: [],
  last: null,
  userId: "self-reported",
  preStress: "Moderate Stress",
  fromHome: false,
  checkin: null,
  displayName: "",
};

const screens = document.querySelectorAll(".screen");

function show(name) {
  state.screen = name;
  screens.forEach((screen) => {
    screen.classList.toggle("hidden", screen.dataset.screen !== name);
  });
  window.scrollTo(0, 0);
}

document.querySelectorAll("[data-next]").forEach((button) => {
  button.addEventListener("click", () => show(button.dataset.next));
});

function setAuthMode(mode) {
  state.authMode = mode;
  document.querySelector("#tab-signin").classList.toggle("on", mode === "signin");
  document.querySelector("#tab-signup").classList.toggle("on", mode === "signup");
  document.querySelector("#name-field").classList.toggle("hidden", mode === "signin");
  document.querySelector("#auth-submit").textContent =
    mode === "signin" ? "Sign In" : "Create Account";
  document.querySelector("#auth-password").autocomplete =
    mode === "signin" ? "current-password" : "new-password";
}

document.querySelector("#tab-signin").addEventListener("click", () => setAuthMode("signin"));
document.querySelector("#tab-signup").addEventListener("click", () => setAuthMode("signup"));

function showForgot(on) {
  document.querySelector("#auth-form").classList.toggle("hidden", on);
  document.querySelector("#forgot-form").classList.toggle("hidden", !on);
  document.querySelector("#tab-signin").closest(".segmented").classList.toggle("hidden", on);
  document.querySelector("#auth-error").textContent = "";
  document.querySelector("#forgot-error").textContent = "";
}

document.querySelector("#forgot-open").addEventListener("click", () => {
  document.querySelector("#forgot-email").value =
    document.querySelector("#auth-email").value;
  document.querySelector("#forgot-name").value =
    document.querySelector("#auth-name").value;
  showForgot(true);
});
document.querySelector("#forgot-back").addEventListener("click", () => showForgot(false));

document.querySelector("#auth-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const error = document.querySelector("#auth-error");
  const submit = document.querySelector("#auth-submit");
  error.textContent = "";
  const body = {
    email: document.querySelector("#auth-email").value.trim(),
    password: document.querySelector("#auth-password").value,
    name: document.querySelector("#auth-name").value.trim(),
  };
  if (!body.email || !body.password) {
    error.textContent = "Enter your email and password.";
    return;
  }
  if (state.authMode === "signup" && body.name.length < 2) {
    error.textContent = "Enter your name.";
    return;
  }
  const path = state.authMode === "signin" ? "/api/signin" : "/api/signup";
  const label = submit.textContent;
  submit.disabled = true;
  submit.textContent = state.authMode === "signin" ? "Signing in…" : "Creating…";
  try {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      error.textContent = data.error || "Could not sign in.";
      return;
    }
    await enterApp(data.name);
  } catch (err) {
    error.textContent = "Could not reach the server. Is AMUSE running?";
  } finally {
    submit.disabled = false;
    submit.textContent = label;
  }
});

document.querySelector("#forgot-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const error = document.querySelector("#forgot-error");
  const submit = document.querySelector("#forgot-submit");
  error.textContent = "";
  const body = {
    name: document.querySelector("#forgot-name").value.trim(),
    email: document.querySelector("#forgot-email").value.trim(),
    password: document.querySelector("#forgot-password").value,
    confirm: document.querySelector("#forgot-confirm").value,
  };
  submit.disabled = true;
  submit.textContent = "Resetting…";
  try {
    const response = await fetch("/api/forgot-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      error.textContent = data.error || "Could not reset password.";
      return;
    }
    showForgot(false);
    await enterApp(data.name);
  } catch (err) {
    error.textContent = "Could not reach the server. Is AMUSE running?";
  } finally {
    submit.disabled = false;
    submit.textContent = "Reset password";
  }
});

async function signOut() {
  await fetch("/api/signout", { method: "POST" });
  sessionStorage.removeItem("amuse_open");
  state.signedIn = false;
  state.hasTaste = false;
  state.checkin = null;
  showForgot(false);
  setAuthMode("signin");
  show("auth");
}

document.querySelector("#signout").addEventListener("click", signOut);
document.querySelector("#signout-home").addEventListener("click", signOut);
document.querySelector("#signout-checkin").addEventListener("click", signOut);

async function beginAppOpen() {
  // New browser/app open → require HRV again. Refresh in the same tab keeps it.
  // Skip clearing when returning from the Watch Shortcut with health params.
  const params = new URLSearchParams(window.location.search);
  const fromWatch = params.has("hk_hrv") || params.has("hk_sleep") || params.has("hk_hr");
  if (!sessionStorage.getItem("amuse_open")) {
    sessionStorage.setItem("amuse_open", "1");
    if (!fromWatch) {
      try {
        await fetch("/api/session-hrv-clear", { method: "POST" });
      } catch (err) {
        // Ignore if signed out.
      }
    }
  }
}

async function loadWatchSetup() {
  try {
    const data = await fetch("/api/device").then((response) => response.json());
    const template = `${data.base_url}/?hk_hrv=HRV&hk_sleep=SLEEP&hk_hr=HR`;
    const box = document.querySelector("#watch-url-template");
    if (box) box.textContent = template;
    const install = document.querySelector("#watch-install");
    if (install && data.watch_install_url) {
      install.href = data.watch_install_url;
    }
    const run = document.querySelector("#watch-run");
    if (run && data.watch_run_url) run.href = data.watch_run_url;
    return data;
  } catch (err) {
    return null;
  }
}

document.querySelector("#copy-watch-template")?.addEventListener("click", async () => {
  const text = document.querySelector("#watch-url-template")?.textContent || "";
  const note = document.querySelector("#watch-copy-note");
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    if (note) note.textContent = "Copied. In Shortcuts, replace HRV / SLEEP / HR with Magic Variables.";
  } catch (err) {
    if (note) note.textContent = "Select the template and copy it manually.";
  }
});

async function importWatchFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const hrv = params.get("hk_hrv");
  const sleep = params.get("hk_sleep");
  const hr = params.get("hk_hr");
  if (hrv == null && sleep == null && hr == null) return false;

  if (hrv != null && hrv !== "") document.querySelector("#checkin-hrv").value = hrv;
  if (sleep != null && sleep !== "") document.querySelector("#checkin-sleep").value = sleep;
  if (hr != null && hr !== "") document.querySelector("#checkin-hr").value = hr;
  if (hrv != null && hrv !== "") document.querySelector("#hrv-input").value = hrv;
  if (sleep != null && sleep !== "") document.querySelector("#sleep-hours").value = sleep;
  if (hr != null && hr !== "") document.querySelector("#heart-rate").value = hr;

  const status = document.querySelector("#watch-status");
  if (status) status.textContent = "Apple Watch numbers received. Saving…";

  const body = {
    mark_hrv: hrv != null && hrv !== "",
    mark_sleep: sleep != null && sleep !== "",
    hrv: hrv || undefined,
    sleep_hours: sleep || undefined,
    heart_rate: hr || undefined,
  };

  // If only some values arrived, still save what we got; check-in screen asks for the rest.
  if (body.mark_hrv || body.mark_sleep || hr) {
    const response = await fetch("/api/checkin", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (response.ok) {
      applyCheckin(data.checkin);
      if (status) {
        status.textContent = "Loaded from Apple Watch / Health Shortcut.";
      }
    } else if (status) {
      status.textContent = data.error || "Could not save Watch data — check the fields below.";
    }
  }

  const clean = window.location.pathname;
  window.history.replaceState({}, "", clean);
  return true;
}

function applyPreferences(prefs) {
  if (!prefs) return;
  state.chosenGenres = new Set(prefs.genres || []);
  state.chosenArtists = new Set(prefs.artists || []);
  state.chosenSongs = new Set(prefs.songs || []);
  state.useSpotify = !!prefs.use_spotify;
  if (prefs.last_pss && prefs.last_pss.length === 10) {
    state.answers = prefs.last_pss.map((value) => Number(value));
  }
  setTasteMode(state.useSpotify);
  refreshTasteUI();
  updateTasteSummary(prefs);
}

function updateTasteSummary(prefs) {
  const summary = document.querySelector("#taste-summary");
  if (!summary) return;
  if (!prefs) {
    summary.textContent = "Save your taste once, then reuse it every time you come back.";
    return;
  }
  if (prefs.use_spotify) {
    summary.textContent = "Using your Spotify listening history.";
    return;
  }
  const bits = [];
  if (prefs.genres?.length) bits.push(prefs.genres.slice(0, 3).join(", "));
  if (prefs.artists?.length) bits.push(prefs.artists.slice(0, 3).join(", "));
  if (prefs.songs?.length) bits.push(prefs.songs.length + " songs");
  summary.textContent = bits.length
    ? "Saved taste: " + bits.join(" · ")
    : "No taste saved yet. Update music taste to get started.";
}

function applyCheckin(checkin) {
  state.checkin = checkin || null;
  const health = checkin?.health || {};
  if (health.sleep_hours != null) {
    document.querySelector("#sleep-hours").value = health.sleep_hours;
    document.querySelector("#checkin-sleep").value = health.sleep_hours;
  }
  if (health.hrv != null) {
    document.querySelector("#hrv-input").value = health.hrv;
    document.querySelector("#checkin-hrv").value = health.hrv;
  }
  if (health.heart_rate != null) {
    document.querySelector("#heart-rate").value = health.heart_rate;
    document.querySelector("#checkin-hr").value = health.heart_rate;
  }
  const summary = document.querySelector("#checkin-summary");
  if (summary && checkin) {
    const bits = [];
    bits.push(checkin.sleep_ok ? "Sleep logged today" : "Sleep due today");
    bits.push(checkin.hrv_ok ? "HRV logged this open" : "HRV due this open");
    bits.push(checkin.pss_ok ? "PSS current this week" : "PSS due this week");
    summary.textContent = bits.join(" · ");
  }
  const stressTitle = document.querySelector("#home-stress-title");
  const stressHint = document.querySelector("#home-stress-hint");
  if (stressTitle && checkin) {
    if (checkin.needs_pss) {
      stressTitle.textContent = "Weekly PSS due";
      stressHint.textContent = "Required once every 7 days before recommendations.";
    } else {
      stressTitle.textContent = "Update PSS (optional)";
      stressHint.textContent = "Already done this week. Retake anytime if you want.";
    }
  }
}

function showHome(name) {
  document.querySelector("#home-hello").textContent = "Hi, " + (name || "there");
  document.querySelector("#home-title").textContent =
    "What do you need right now?";
  applyCheckin(state.checkin);
  show("home");
}

function showCheckin(name) {
  document.querySelector("#checkin-hello").textContent = "Hi, " + (name || "there");
  const needsHrv = !state.checkin || state.checkin.needs_hrv;
  const needsSleep = !state.checkin || state.checkin.needs_sleep;
  document.querySelector("#checkin-hrv-block").classList.toggle("hidden", !needsHrv);
  document.querySelector("#checkin-sleep-block").classList.toggle("hidden", !needsSleep);
  document.querySelector("#checkin-hint").textContent = [
    needsHrv ? "HRV is required each time you open AMUSE." : null,
    needsSleep ? "Sleep is required once per day." : null,
    "Use Get from Apple Watch, or type the numbers.",
  ].filter(Boolean).join(" ");
  document.querySelector("#checkin-error").textContent = "";
  loadWatchSetup();
  show("checkin");
}

function routeAfterAuth(name) {
  const params = new URLSearchParams(window.location.search);
  if (params.get("spotify") === "connected") {
    setTasteMode(true);
    show("taste");
    return;
  }
  if (state.checkin && (state.checkin.needs_hrv || state.checkin.needs_sleep)) {
    showCheckin(name);
    return;
  }
  if (!state.hasTaste) {
    show("welcome");
    return;
  }
  if (state.checkin && state.checkin.needs_pss) {
    state.fromHome = true;
    state.question = 0;
    renderQuestion();
    show("stress");
    return;
  }
  showHome(name);
}

async function enterApp(name) {
  state.signedIn = true;
  state.displayName = name || "there";
  document.querySelector("#hello").textContent = "Hi, " + state.displayName;
  await beginAppOpen();
  await loadWatchSetup();

  let me = { has_taste: false, preferences: null, checkin: null };
  try {
    me = await fetch("/api/me").then((response) => response.json());
  } catch (err) {
    // Continue with defaults if /api/me fails after a fresh session.
  }
  state.hasTaste = !!me.has_taste;
  if (me.preferences) applyPreferences(me.preferences);
  applyCheckin(me.checkin);

  // Apple Watch Shortcut returns here with ?hk_hrv=&hk_sleep=&hk_hr=
  await importWatchFromUrl();
  try {
    me = await fetch("/api/me").then((response) => response.json());
    if (me.checkin) applyCheckin(me.checkin);
    state.hasTaste = !!me.has_taste;
  } catch (err) {
    // Keep prior check-in state.
  }

  routeAfterAuth(state.displayName);

  try {
    await loadOptions();
    await loadSpotify();
    if (me.preferences) applyPreferences(me.preferences);
  } catch (err) {
    console.error(err);
  }
}

document.querySelector("#checkin-save").addEventListener("click", async () => {
  const error = document.querySelector("#checkin-error");
  error.textContent = "";
  const needsHrv = !state.checkin || state.checkin.needs_hrv;
  const needsSleep = !state.checkin || state.checkin.needs_sleep;
  const body = {
    mark_hrv: needsHrv,
    mark_sleep: needsSleep,
    hrv: document.querySelector("#checkin-hrv").value,
    sleep_hours: document.querySelector("#checkin-sleep").value,
    heart_rate: document.querySelector("#checkin-hr").value,
  };
  const response = await fetch("/api/checkin", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    error.textContent = data.error || "Could not save check-in.";
    return;
  }
  applyCheckin(data.checkin);
  document.querySelector("#hrv-input").value = body.hrv || document.querySelector("#hrv-input").value;
  document.querySelector("#sleep-hours").value =
    body.sleep_hours || document.querySelector("#sleep-hours").value;
  document.querySelector("#heart-rate").value =
    body.heart_rate || document.querySelector("#heart-rate").value;
  routeAfterAuth(state.displayName);
});

function chosenHas(chosen, item) {
  return chosen.has(item) || chosen.has(item.toLowerCase());
}

function addChoice(chosen, item) {
  if (chosenHas(chosen, item)) return;
  chosen.add(item);
}

function removeChoice(chosen, item) {
  chosen.delete(item);
  chosen.delete(item.toLowerCase());
  for (const value of [...chosen]) {
    if (String(value).toLowerCase() === String(item).toLowerCase()) {
      chosen.delete(value);
    }
  }
}

function renderChips(container, chosen, onChange) {
  container.innerHTML = "";
  [...chosen].forEach((item) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip";
    chip.textContent = item;
    chip.addEventListener("click", () => {
      removeChoice(chosen, item);
      onChange();
    });
    container.appendChild(chip);
  });
}

function renderSuggestions(box, items, chosen, query, onPick) {
  const needle = query.trim().toLowerCase();
  box.innerHTML = "";
  if (!needle) {
    box.classList.add("hidden");
    return;
  }
  const visible = items
    .filter((item) => item.toLowerCase().includes(needle) && !chosenHas(chosen, item))
    .slice(0, 12);
  if (!visible.length) {
    box.classList.add("hidden");
    return;
  }
  visible.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.setAttribute("role", "option");
    button.textContent = item;
    button.addEventListener("mousedown", (event) => {
      event.preventDefault();
      onPick(item);
    });
    box.appendChild(button);
  });
  box.classList.remove("hidden");
}

function refreshTasteUI() {
  renderChips(document.querySelector("#genre-chips"), state.chosenGenres, refreshTasteUI);
  renderChips(document.querySelector("#artist-chips"), state.chosenArtists, refreshTasteUI);
  renderChips(document.querySelector("#song-chips"), state.chosenSongs, refreshTasteUI);
  renderSuggestions(
    document.querySelector("#genre-suggest"),
    state.genres,
    state.chosenGenres,
    document.querySelector("#genre-search").value,
    (item) => {
      addChoice(state.chosenGenres, item);
      document.querySelector("#genre-search").value = "";
      refreshTasteUI();
      document.querySelector("#genre-suggest").classList.add("hidden");
    }
  );
  renderSuggestions(
    document.querySelector("#artist-suggest"),
    state.artists,
    state.chosenArtists,
    document.querySelector("#artist-search").value,
    (item) => {
      addChoice(state.chosenArtists, item);
      document.querySelector("#artist-search").value = "";
      refreshTasteUI();
      document.querySelector("#artist-suggest").classList.add("hidden");
    }
  );
  renderSuggestions(
    document.querySelector("#song-suggest"),
    state.songs,
    state.chosenSongs,
    document.querySelector("#song-search").value,
    (item) => {
      addChoice(state.chosenSongs, item);
      document.querySelector("#song-search").value = "";
      refreshTasteUI();
      document.querySelector("#song-suggest").classList.add("hidden");
    }
  );
}

function renderAllPicks() {
  refreshTasteUI();
}

async function loadOptions() {
  const response = await fetch("/api/options");
  if (response.status === 401) {
    state.signedIn = false;
    show("auth");
    const error = document.querySelector("#auth-error");
    if (error) error.textContent = "Session expired. Sign in again.";
    return;
  }
  if (!response.ok) {
    throw new Error("Could not load music options.");
  }
  const data = await response.json();
  state.genres = data.genres || [];
  state.artists = data.artists || [];
  state.songs = data.songs || [];
  state.questions = data.questions || [];
  state.choiceLabels = data.choices || [];
  refreshTasteUI();
  renderQuestion();
}

document.querySelector("#genre-search").addEventListener("input", () => refreshTasteUI());
document.querySelector("#artist-search").addEventListener("input", () => refreshTasteUI());
document.querySelector("#song-search").addEventListener("input", () => refreshTasteUI());

["#genre-search", "#artist-search", "#song-search"].forEach((selector) => {
  const input = document.querySelector(selector);
  input.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    const box = input.parentElement.querySelector(".suggest");
    const first = box && box.querySelector("button");
    if (first) first.dispatchEvent(new Event("mousedown"));
  });
  input.addEventListener("blur", () => {
    setTimeout(() => {
      const box = input.parentElement.querySelector(".suggest");
      if (box) box.classList.add("hidden");
    }, 150);
  });
});

function setTasteMode(spotify) {
  state.useSpotify = spotify;
  document.querySelector("#mode-manual").classList.toggle("on", !spotify);
  document.querySelector("#mode-spotify").classList.toggle("on", spotify);
  document.querySelector("#manual-taste").classList.toggle("hidden", spotify);
  document.querySelector("#spotify-taste").classList.toggle("hidden", !spotify);
}

document.querySelector("#mode-manual").addEventListener("click", () => setTasteMode(false));
document.querySelector("#mode-spotify").addEventListener("click", () => setTasteMode(true));

function setSpotifyConnected(connected, name, canConnectHere) {
  const status = document.querySelector("#spotify-status");
  const note = document.querySelector("#spotify-computer-note");
  const login = document.querySelector("#spotify-login");
  const logout = document.querySelector("#spotify-logout");
  const error = document.querySelector("#spotify-error");
  if (error) error.textContent = "";
  if (connected) {
    status.textContent = "Connected as " + (name || "Spotify") + ".";
    login.classList.add("hidden");
    logout.classList.remove("hidden");
    if (note) note.classList.add("hidden");
  } else {
    status.textContent = "Connect Spotify to personalize with your listening history.";
    logout.classList.add("hidden");
    if (canConnectHere) {
      login.classList.remove("hidden");
      login.textContent = "Log in with Spotify";
      login.setAttribute("href", "/spotify/login");
      if (note) {
        note.classList.remove("hidden");
        note.textContent =
          "Dashboard redirect must be exactly http://127.0.0.1:8501/ — delete any iPhone/Wi‑Fi IP. Then click Log in here.";
      }
    } else {
      login.classList.add("hidden");
      if (note) {
        note.classList.remove("hidden");
        note.textContent =
          "Phone IPs cannot be used with Spotify. On your Mac: delete the iPhone URL from the Spotify Dashboard, keep only http://127.0.0.1:8501/, open that URL, sign into the same AMUSE account, connect Spotify once, then return here.";
      }
    }
  }
}

function showSpotifyQueryMessage() {
  const params = new URLSearchParams(window.location.search);
  const error = document.querySelector("#spotify-error");
  if (!error) return;
  if (params.get("spotify") === "use-computer") {
    error.textContent =
      "Spotify login only works at http://127.0.0.1:8501 on this computer.";
    setTasteMode(true);
  } else if (params.get("spotify") === "denied") {
    error.textContent = "Spotify login was cancelled.";
  } else if (params.get("spotify") === "signin-first") {
    error.textContent = "Sign in to AMUSE first, then connect Spotify.";
  }
}

async function loadSpotify() {
  const response = await fetch("/api/spotify");
  if (!response.ok) return;
  const data = await response.json();
  setSpotifyConnected(data.connected, data.name, data.can_connect_here);
  if (data.connected) setTasteMode(true);
  showSpotifyQueryMessage();
}

document.querySelector("#spotify-logout").addEventListener("click", async () => {
  await fetch("/spotify/logout", { method: "POST" });
  const status = await fetch("/api/spotify").then((response) => response.json()).catch(() => ({}));
  setSpotifyConnected(false, "", status.can_connect_here);
});

async function saveCurrentTaste(lastPss) {
  await fetch("/api/preferences", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      genres: [...state.chosenGenres],
      artists: [...state.chosenArtists],
      songs: [...state.chosenSongs],
      use_spotify: state.useSpotify,
      last_pss: lastPss || undefined,
    }),
  });
  state.hasTaste = true;
  updateTasteSummary({
    genres: [...state.chosenGenres],
    artists: [...state.chosenArtists],
    songs: [...state.chosenSongs],
    use_spotify: state.useSpotify,
  });
}

document.querySelector('#app [data-screen="taste"] [data-next="stress"]').addEventListener(
  "click",
  async (event) => {
    event.preventDefault();
    await saveCurrentTaste();
    if (state.fromHome) {
      state.fromHome = false;
      showHome(document.querySelector("#home-hello").textContent.replace(/^Hi, /, ""));
      return;
    }
    state.question = 0;
    renderQuestion();
    show("stress");
  }
);

document.querySelector("#home-taste").addEventListener("click", () => {
  state.fromHome = true;
  show("taste");
});

document.querySelector("#home-stress").addEventListener("click", () => {
  state.fromHome = true;
  state.question = 0;
  renderQuestion();
  show("stress");
});

document.querySelector("#home-recommend").addEventListener("click", async () => {
  const error = document.querySelector("#home-error");
  error.textContent = "";
  if (!state.hasTaste && !state.useSpotify) {
    error.textContent = "Update your music taste first.";
    return;
  }
  if (state.checkin?.needs_hrv || state.checkin?.needs_sleep) {
    showCheckin(state.displayName);
    return;
  }
  if (state.checkin?.needs_pss || state.answers.some((answer) => answer === null)) {
    error.textContent = "Complete this week's stress questionnaire first.";
    state.fromHome = true;
    state.question = 0;
    renderQuestion();
    show("stress");
    return;
  }
  await recommend(0);
});

function renderQuestion() {
  const text = document.querySelector("#question-text");
  const box = document.querySelector("#answers");
  if (!state.questions.length) return;
  text.textContent = state.questions[state.question];
  document.querySelector("#question-count").textContent =
    "Question " + (state.question + 1) + " of 10";
  box.innerHTML = "";
  state.choiceLabels.forEach((label, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "answer" + (state.answers[state.question] === index ? " on" : "");
    button.textContent = index + "  " + label;
    button.addEventListener("click", () => {
      state.answers[state.question] = index;
      renderQuestion();
    });
    box.appendChild(button);
  });
  document.querySelector("#question-next").textContent =
    state.question === 9 ? "Continue" : "Next";
  document.querySelector("#question-prev").classList.toggle(
    "hidden",
    state.question === 0
  );
}

document.querySelector("#question-next").addEventListener("click", async () => {
  if (state.answers[state.question] === null) return;
  if (state.question < 9) {
    state.question += 1;
    renderQuestion();
    return;
  }
  await saveCurrentTaste(state.answers);
  const me = await fetch("/api/me").then((response) => response.json()).catch(() => ({}));
  if (me.checkin) applyCheckin(me.checkin);
  if (state.fromHome && state.hasTaste && state.checkin && !state.checkin.needs_hrv && !state.checkin.needs_sleep) {
    state.fromHome = false;
    showHome(state.displayName);
    return;
  }
  // Prefill health confirm from check-in, then recommend.
  if (state.checkin?.health?.sleep_hours != null) {
    document.querySelector("#sleep-hours").value = state.checkin.health.sleep_hours;
  }
  if (state.checkin?.health?.hrv != null) {
    document.querySelector("#hrv-input").value = state.checkin.health.hrv;
  }
  show("health");
});

document.querySelector("#question-prev").addEventListener("click", () => {
  if (state.question === 0) return;
  state.question -= 1;
  renderQuestion();
});

document.querySelector('#app [data-screen="stress"] .top .text').addEventListener(
  "click",
  (event) => {
    if (state.question > 0) {
      event.preventDefault();
      event.stopImmediatePropagation();
      state.question -= 1;
      renderQuestion();
      return;
    }
    if (state.fromHome || state.hasTaste) {
      event.preventDefault();
      event.stopImmediatePropagation();
      showHome(document.querySelector("#hello").textContent.replace(/^Hi, /, ""));
    }
  },
  true
);

document.querySelector("#health-back").addEventListener("click", () => {
  state.question = 9;
  renderQuestion();
  show("stress");
});

async function syncHealthBeforeRecommend() {
  const sleep = document.querySelector("#sleep-hours").value;
  const hrv = document.querySelector("#hrv-input").value;
  const heart = document.querySelector("#heart-rate").value;
  const needsSleep = !state.checkin || state.checkin.needs_sleep;
  const needsHrv = !state.checkin || state.checkin.needs_hrv;
  if (!needsSleep && !needsHrv && !sleep && !hrv) return true;
  const response = await fetch("/api/checkin", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      mark_sleep: true,
      mark_hrv: true,
      sleep_hours: sleep,
      hrv: hrv,
      heart_rate: heart,
    }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = document.querySelector("#form-error");
    if (error) error.textContent = data.error || "Enter sleep and HRV.";
    return false;
  }
  applyCheckin(data.checkin);
  return true;
}

function payload(startAt) {
  return {
    pss: state.answers,
    heart_rate: document.querySelector("#heart-rate").value,
    sleep_hours: document.querySelector("#sleep-hours").value,
    hrv: document.querySelector("#hrv-input").value,
    genres: [...state.chosenGenres],
    artists: [...state.chosenArtists],
    songs: [...state.chosenSongs],
    use_spotify: state.useSpotify,
    start_at: startAt,
  };
}

function renderResults(data) {
  state.last = data;
  state.userId = data.user_id;
  state.preStress = data.stress_level;
  document.querySelector("#stress-label").textContent = data.stress_level;
  document.querySelector("#playlist-note").textContent = "";
  const note = document.querySelector("#result-note");
  if (data.target_arousal <= 0.35) {
    note.textContent = "High stress, so these stay low-energy and skip rock and hype.";
  } else if (data.genres.length) {
    note.textContent = "Drawn toward " + data.genres.slice(0, 6).join(", ") + ".";
  } else {
    note.textContent = "PSS " + data.pss_total + "/40, " + data.pss_band + ".";
  }
  const list = document.querySelector("#song-list");
  list.innerHTML = "";
  const select = document.querySelector("#feedback-song");
  select.innerHTML = "";
  data.songs.forEach((song, index) => {
    const card = document.createElement("article");
    card.className = "song";
    const width = Math.round(song.energy * 100);
    card.innerHTML =
      "<strong>" + (data.start_at + index + 1) + ". " + song.track_name + "</strong>" +
      "<span>" + song.artists + (song.genre ? " · " + song.genre : "") + "</span>" +
      "<div class='meter'><i style='width:" + width + "%'></i></div>";
    list.appendChild(card);
    const option = document.createElement("option");
    option.value = index;
    option.textContent = song.track_name + " — " + song.artists;
    select.appendChild(option);
  });
  show("results");
}

async function recommend(startAt) {
  const error =
    document.querySelector("#form-error") || document.querySelector("#home-error");
  if (error) error.textContent = "";
  if (state.answers.some((answer) => answer === null)) {
    if (error) error.textContent = "Finish the stress questions first.";
    show("stress");
    return;
  }
  if (state.screen === "health") {
    const ok = await syncHealthBeforeRecommend();
    if (!ok) return;
  }
  const button = document.querySelector("#recommend");
  if (button) button.textContent = "Finding songs…";
  const homeButton = document.querySelector("#home-recommend");
  if (homeButton) homeButton.textContent = "Finding songs…";
  const response = await fetch("/api/recommend", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload(startAt)),
  });
  const data = await response.json();
  if (button) button.textContent = "Recommend music";
  if (homeButton) homeButton.textContent = "Recommend music";
  if (!response.ok) {
    if (data.needs_hrv || data.needs_sleep) {
      showCheckin(state.displayName);
      return;
    }
    if (data.needs_pss) {
      state.fromHome = true;
      state.question = 0;
      renderQuestion();
      show("stress");
      return;
    }
    if (error) error.textContent = data.error || "Something went wrong.";
    return;
  }
  renderResults(data);
}

document.querySelector("#recommend").addEventListener("click", () => recommend(0));
document.querySelector("#again").addEventListener("click", () => {
  if (!state.last) return;
  recommend(state.last.start_at + 10);
});

document.querySelector("#save-playlist").addEventListener("click", async () => {
  const note = document.querySelector("#playlist-note");
  note.textContent = "Saving to Spotify…";
  if (!state.last) return;
  const response = await fetch("/api/playlist", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      songs: state.last.songs,
      stress_level: state.last.stress_level,
      name: "AMUSE · " + state.last.stress_level,
    }),
  });
  const data = await response.json();
  if (!response.ok) {
    note.textContent = data.error || "Could not save the playlist.";
    return;
  }
  note.innerHTML =
    'Saved as <a href="' + data.url + '" target="_blank" rel="noreferrer">' +
    data.name + "</a>.";
});

document.querySelector("#feedback").addEventListener("submit", async (event) => {
  event.preventDefault();
  const song = state.last.songs[document.querySelector("#feedback-song").value];
  await fetch("/api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: state.userId,
      track_name: song.track_name,
      artists: song.artists,
      pre_stress: state.preStress,
      post_stress: document.querySelector("#post-stress").value,
      helpfulness: document.querySelector("#helpfulness").value,
    }),
  });
  document.querySelector("#feedback-note").textContent = "Saved. The next list can use this.";
});

document.querySelector('[data-screen="results"] .top .text').addEventListener("click", (event) => {
  if (state.hasTaste) {
    event.preventDefault();
    showHome(document.querySelector("#hello").textContent.replace(/^Hi, /, ""));
  }
});

async function boot() {
  const response = await fetch("/api/me");
  const data = await response.json();
  if (data.signed_in) {
    await enterApp(data.name);
    return;
  }
  show("auth");
}

boot();
