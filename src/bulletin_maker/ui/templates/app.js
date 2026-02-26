/* Bulletin Maker — Wizard UI Logic */

"use strict";

// ── Constants ────────────────────────────────────────────────────────

/** Season key to display label. */
const SEASON_LABELS = {
    advent: "Advent",
    christmas: "Christmas",
    epiphany: "Epiphany",
    lent: "Lent",
    easter: "Easter",
    pentecost: "Ordinary Time",
    christmas_eve: "Christmas Eve",
};

/** Canticle key to display label. */
const CANTICLE_LABELS = {
    glory_to_god: "Glory to God",
    this_is_the_feast: "This Is the Feast",
    none: "None",
};

/** Document key to display label. */
const DOC_LABELS = {
    bulletin: "Bulletin for Congregation",
    prayers: "Pulpit Prayers",
    scripture: "Pulpit Scripture",
    large_print: "Full with Hymns LARGE PRINT",
    leader_guide: "Leader Guide",
};

// ── State ────────────────────────────────────────────────────────────

/** Returns a fresh initial state object. */
function initialState() {
    return {
        dateStr: "",          // "2026-02-22" (HTML input value)
        dateDisplay: "",      // "February 22, 2026"
        apiDate: "",          // "2026-2-22" (for S&S API)
        season: "",
        defaults: null,       // seasonal liturgical defaults
        hymns: {              // {slot: {number, collection, title}}
            gathering: null,
            sermon: null,
            communion: null,
            sending: null,
        },
        coverImage: "",
        outputDir: "",
    };
}

const state = initialState();

// ── Helpers ──────────────────────────────────────────────────────────

function $(sel) { return document.querySelector(sel); }
function $$(sel) { return document.querySelectorAll(sel); }

function show(el) { el.hidden = false; }
function hide(el) { el.hidden = true; }

function showError(el, msg) {
    el.textContent = msg;
    show(el);
}

function hideError(el) {
    el.textContent = "";
    hide(el);
}

function showWarning(el, msg) {
    el.textContent = msg;
    show(el);
}

function hideWarning(el) {
    el.textContent = "";
    hide(el);
}

function enableSection(id) {
    document.getElementById(id).classList.remove("disabled-section");
}

/** Formats "2026-02-22" as "February 22, 2026". */
function formatDate(dateStr) {
    const d = new Date(dateStr + "T12:00:00");
    return d.toLocaleDateString("en-US", {
        year: "numeric", month: "long", day: "numeric",
    });
}

/** Returns the display label for a liturgical season key. */
function seasonLabel(season) {
    return SEASON_LABELS[season] || season;
}

/** Waits for pywebview JS bridge to be ready. */
function waitForApi() {
    return new Promise(function(resolve) {
        if (window.pywebview && window.pywebview.api) {
            resolve();
            return;
        }
        window.addEventListener("pywebviewready", resolve);
    });
}

// ── Progress callback (called from Python via evaluate_js) ──────────

window.updateProgress = function(data) {
    const fill = document.getElementById("progress-fill");
    const status = document.getElementById("progress-status");
    const bar = document.querySelector(".progress-bar");
    if (fill) fill.style.width = data.pct + "%";
    if (status) status.textContent = data.detail;
    if (bar) bar.setAttribute("aria-valuenow", data.pct);
};

// ── Login ────────────────────────────────────────────────────────────

async function initLogin() {
    await waitForApi();
}

function setupLogin() {
    const form = $("#login-form");
    const btn = $("#login-btn");
    const errorEl = $("#login-error");
    const spinner = $("#login-spinner");

    form.addEventListener("submit", async function() {
        const username = $("#login-username").value.trim();
        const password = $("#login-password").value;
        if (!username || !password) return;

        hideError(errorEl);
        btn.disabled = true;
        hide(form);
        show(spinner);

        const result = await window.pywebview.api.login(username, password);

        if (result.success) {
            hide($("#login-overlay"));
            show($("#app"));
            $("#user-display").textContent = result.username;
        } else {
            hide(spinner);
            show(form);
            btn.disabled = false;
            showError(errorEl, result.error || "Login failed");
        }
    });
}

function setupLogout() {
    $("#logout-link").addEventListener("click", async function(e) {
        e.preventDefault();
        await window.pywebview.api.logout();
        // Show login overlay again
        show($("#login-overlay"));
        hide($("#app"));
        const form = $("#login-form");
        show(form);
        hide($("#login-spinner"));
        $("#login-username").value = "";
        $("#login-password").value = "";
        hideError($("#login-error"));
        $("#login-btn").disabled = false;

        // Reset state
        resetAll();
    });
}

/** Resets all wizard state and UI to initial values. */
function resetAll() {
    Object.assign(state, initialState());

    // Reset UI
    hide($("#day-info"));
    hideError($("#date-error"));
    hideWarning($("#date-warning"));
    $("#date-input").value = "";
    $("#preface-select").innerHTML = "";

    ["section-hymns", "section-liturgy", "section-details", "section-generate"].forEach(function(id) {
        document.getElementById(id).classList.add("disabled-section");
    });

    // Reset hymn slots
    $$(".hymn-number").forEach(function(el) { el.value = ""; });
    $$(".hymn-info").forEach(function(el) { hide(el); el.textContent = ""; });
    $$(".hymn-error").forEach(function(el) { hide(el); });

    // Reset details
    $("#prelude-title").value = "";
    $("#prelude-performer").value = "";
    $("#postlude-title").value = "";
    $("#postlude-performer").value = "";
    $("#choral-title").value = "";
    $("#cover-image-path").textContent = "None selected";
    $("#output-dir-path").textContent = "./output";

    // Reset generate section
    hide($("#progress-area"));
    hide($("#results-area"));
    hideError($("#generate-error"));
}

// ── Date & Season Fetch ──────────────────────────────────────────────

function setupDateFetch() {
    $("#fetch-btn").addEventListener("click", async function() {
        const dateInput = $("#date-input");
        const dateStr = dateInput.value;
        if (!dateStr) {
            showError($("#date-error"), "Please select a date.");
            return;
        }

        // Validate date is parseable
        const dateVal = new Date(dateStr + "T12:00:00");
        if (isNaN(dateVal.getTime())) {
            showError($("#date-error"), "Invalid date format.");
            return;
        }

        hideError($("#date-error"));
        hideWarning($("#date-warning"));
        hide($("#day-info"));

        // M14: Warn if date is not a Sunday (non-blocking)
        if (dateVal.getDay() !== 0) {
            showWarning($("#date-warning"), "Note: this date is not a Sunday.");
        }

        const spinner = $("#date-spinner");
        show(spinner);
        this.disabled = true;

        const dateDisplay = formatDate(dateStr);
        state.dateStr = dateStr;
        state.dateDisplay = dateDisplay;

        const result = await window.pywebview.api.fetch_day_content(dateStr, dateDisplay);

        hide(spinner);
        this.disabled = false;

        if (!result.success) {
            showError($("#date-error"), result.error || "Failed to fetch content.");
            return;
        }

        state.season = result.season;
        state.defaults = result.defaults;

        // Display day info
        $("#day-name").textContent = result.day_name;
        $("#day-season").textContent = seasonLabel(result.season);

        const readingsEl = $("#readings-list");
        readingsEl.innerHTML = "";
        (result.readings || []).forEach(function(r) {
            const div = document.createElement("div");
            div.className = "reading-item";
            const span = document.createElement("span");
            span.className = "reading-label";
            span.textContent = r.label + ":";
            div.appendChild(span);
            div.appendChild(document.createTextNode(" " + r.citation));
            readingsEl.appendChild(div);
        });

        show($("#day-info"));

        // Enable all sections
        enableSection("section-hymns");
        enableSection("section-liturgy");
        enableSection("section-details");
        enableSection("section-generate");

        // Pre-fill liturgical settings
        applyDefaults(result.defaults);

        // Reset generate area
        hide($("#progress-area"));
        hide($("#results-area"));
        hideError($("#generate-error"));
    });
}

/** Pre-fills liturgical setting controls from seasonal defaults. */
function applyDefaults(defaults) {
    if (!defaults) return;

    // Creed
    const creedRadio = document.querySelector('input[name="creed_type"][value="' + defaults.creed_type + '"]');
    if (creedRadio) creedRadio.checked = true;
    $("#hint-creed").textContent = "Default: " + (defaults.creed_type === "nicene" ? "Nicene" : "Apostles'");

    // Kyrie
    $("#include-kyrie").checked = defaults.include_kyrie;
    $("#hint-kyrie").textContent = "Default: " + (defaults.include_kyrie ? "Yes" : "No");

    // Canticle
    const canticleRadio = document.querySelector('input[name="canticle"][value="' + defaults.canticle + '"]');
    if (canticleRadio) canticleRadio.checked = true;
    $("#hint-canticle").textContent = "Default: " + (CANTICLE_LABELS[defaults.canticle] || defaults.canticle);

    // Eucharistic form
    const epRadio = document.querySelector('input[name="eucharistic_form"][value="' + defaults.eucharistic_form + '"]');
    if (epRadio) epRadio.checked = true;
    $("#hint-eucharistic").textContent = "Default: " + defaults.eucharistic_form.charAt(0).toUpperCase() + defaults.eucharistic_form.slice(1);

    // Memorial acclamation
    $("#include-memorial").checked = defaults.include_memorial_acclamation;
    $("#hint-memorial").textContent = "Default: " + (defaults.include_memorial_acclamation ? "Yes" : "No");

    // Preface
    if (defaults.preface) {
        populatePrefaceDropdown(defaults.preface);
    }
}

/** Populate preface dropdown from API, pre-selecting the seasonal default. */
async function populatePrefaceDropdown(defaultKey) {
    var select = $("#preface-select");
    select.innerHTML = "";

    try {
        var result = await window.pywebview.api.get_preface_options();
        if (!result.success) return;

        var prefaces = result.prefaces;

        // Seasonal group
        var seasonalGroup = document.createElement("optgroup");
        seasonalGroup.label = "Seasonal";
        (prefaces.seasonal || []).forEach(function(p) {
            var opt = document.createElement("option");
            opt.value = p.key;
            opt.textContent = p.label;
            if (p.key === defaultKey) opt.selected = true;
            seasonalGroup.appendChild(opt);
        });
        select.appendChild(seasonalGroup);

        // Occasional group
        var occasionalGroup = document.createElement("optgroup");
        occasionalGroup.label = "Occasional";
        (prefaces.occasional || []).forEach(function(p) {
            var opt = document.createElement("option");
            opt.value = p.key;
            opt.textContent = p.label;
            if (p.key === defaultKey) opt.selected = true;
            occasionalGroup.appendChild(opt);
        });
        select.appendChild(occasionalGroup);

        $("#hint-preface").textContent = "Default: " + (select.options[select.selectedIndex] ? select.options[select.selectedIndex].textContent : defaultKey);
    } catch (err) {
        // Fallback: just set the key directly
        var opt = document.createElement("option");
        opt.value = defaultKey;
        opt.textContent = defaultKey;
        opt.selected = true;
        select.appendChild(opt);
    }
}

function setupResetDefaults() {
    $("#reset-defaults-btn").addEventListener("click", function() {
        if (state.defaults) {
            applyDefaults(state.defaults);
        }
    });
}

// ── Hymn Fetching ────────────────────────────────────────────────────

function setupHymnFetch() {
    $$(".hymn-fetch-btn").forEach(function(btn) {
        btn.addEventListener("click", async function() {
            const slot = this.closest(".hymn-slot");
            const slotName = slot.dataset.slot;
            const numberInput = slot.querySelector(".hymn-number");
            const collection = slot.querySelector(".hymn-collection").value;
            const errorEl = slot.querySelector(".hymn-error");
            const infoEl = slot.querySelector(".hymn-info");
            const number = numberInput.value.trim();

            if (!number) {
                showError(errorEl, "Enter a hymn number.");
                hide(infoEl);
                return;
            }

            // Clear previous results
            hideError(errorEl);
            infoEl.textContent = "";
            hide(infoEl);
            state.hymns[slotName] = null;
            this.disabled = true;
            this.textContent = "...";

            try {
                // Search first
                const searchResult = await window.pywebview.api.search_hymn(number, collection);

                if (!searchResult.success) {
                    this.disabled = false;
                    this.textContent = "Fetch";
                    showError(errorEl, searchResult.error || "Hymn not found.");
                    return;
                }

                // Skip lyrics fetch if hymn has no words download
                if (!searchResult.has_words) {
                    this.disabled = false;
                    this.textContent = "Fetch";
                    infoEl.textContent = searchResult.title + " (title only \u2014 no lyrics available)";
                    show(infoEl);
                    state.hymns[slotName] = {
                        number: number,
                        collection: collection,
                        title: searchResult.title,
                    };
                    return;
                }

                // Then fetch lyrics
                const lyricsResult = await window.pywebview.api.fetch_hymn_lyrics(
                    number, state.dateStr, collection
                );

                this.disabled = false;
                this.textContent = "Fetch";

                if (lyricsResult.success) {
                    infoEl.textContent = searchResult.title +
                        " \u2014 " + lyricsResult.verse_count + " verse(s)" +
                        (lyricsResult.has_refrain ? " + refrain" : "");
                    show(infoEl);
                    state.hymns[slotName] = {
                        number: number,
                        collection: collection,
                        title: searchResult.title,
                    };
                } else {
                    // Lyrics failed but search succeeded — still usable (title only)
                    infoEl.textContent = searchResult.title + " (title only \u2014 lyrics unavailable)";
                    show(infoEl);
                    state.hymns[slotName] = {
                        number: number,
                        collection: collection,
                        title: searchResult.title,
                    };
                    showError(errorEl, "Lyrics: " + (lyricsResult.error || "unavailable"));
                }
            } catch (err) {
                this.disabled = false;
                this.textContent = "Fetch";
                showError(errorEl, "Failed to fetch hymn: " + (err.message || "unknown error"));
            }
        });
    });
}

// ── File Pickers ─────────────────────────────────────────────────────

function setupFilePickers() {
    $("#cover-image-btn").addEventListener("click", async function() {
        this.disabled = true;
        try {
            const result = await window.pywebview.api.choose_cover_image();
            if (result.success) {
                state.coverImage = result.path;
                const name = result.path.split("/").pop().split("\\").pop();
                $("#cover-image-path").textContent = name;
            }
        } finally {
            this.disabled = false;
        }
    });

    $("#output-dir-btn").addEventListener("click", async function() {
        this.disabled = true;
        try {
            const result = await window.pywebview.api.choose_output_directory();
            if (result.success) {
                state.outputDir = result.path;
                $("#output-dir-path").textContent = result.path;
            }
        } finally {
            this.disabled = false;
        }
    });
}

// ── Generation ───────────────────────────────────────────────────────

/** Collects all form data into a dict for the Python API. */
function collectFormData() {
    // Liturgical settings
    const creedEl = document.querySelector('input[name="creed_type"]:checked');
    const canticleEl = document.querySelector('input[name="canticle"]:checked');
    const epEl = document.querySelector('input[name="eucharistic_form"]:checked');

    const formData = {
        date: state.dateStr,
        date_display: state.dateDisplay,
        creed_type: creedEl ? creedEl.value : null,
        include_kyrie: $("#include-kyrie").checked,
        canticle: canticleEl ? canticleEl.value : null,
        eucharistic_form: epEl ? epEl.value : null,
        include_memorial_acclamation: $("#include-memorial").checked,
        preface: $("#preface-select").value || null,
        prelude_title: $("#prelude-title").value.trim(),
        prelude_performer: $("#prelude-performer").value.trim(),
        postlude_title: $("#postlude-title").value.trim(),
        postlude_performer: $("#postlude-performer").value.trim(),
        choral_title: $("#choral-title").value.trim(),
        cover_image: state.coverImage,
        output_dir: state.outputDir || "output",
    };

    // Hymns
    ["gathering", "sermon", "communion", "sending"].forEach(function(slot) {
        const data = state.hymns[slot];
        if (data && data.number) {
            formData[slot + "_hymn"] = {
                number: data.number,
                collection: data.collection,
                title: data.title,
            };
        } else {
            formData[slot + "_hymn"] = null;
        }
    });

    return formData;
}

function setupGenerate() {
    $("#generate-btn").addEventListener("click", async function() {
        const errorEl = $("#generate-error");
        hideError(errorEl);
        hide($("#results-area"));

        // Validate required state
        if (!state.dateStr || !state.dateDisplay) {
            showError(errorEl, "Please fetch content for a date first.");
            return;
        }

        this.disabled = true;
        show($("#progress-area"));
        $("#progress-fill").style.width = "0%";
        $("#progress-status").textContent = "Starting generation...";
        const bar = document.querySelector(".progress-bar");
        if (bar) bar.setAttribute("aria-valuenow", 0);

        const formData = collectFormData();
        const result = await window.pywebview.api.generate_all(formData);

        this.disabled = false;

        if (result.error && !result.results) {
            hide($("#progress-area"));
            showError(errorEl, result.error);
            return;
        }

        // Show results
        const resultsList = $("#results-list");
        resultsList.innerHTML = "";

        if (result.results) {
            Object.keys(result.results).forEach(function(key) {
                const li = document.createElement("li");
                const path = result.results[key];
                const name = path.split("/").pop().split("\\").pop();
                li.textContent = (DOC_LABELS[key] || key) + " \u2014 " + name;
                resultsList.appendChild(li);
            });
        }

        // Show errors if any
        const errorsArea = $("#results-errors");
        const errorsList = $("#errors-list");
        errorsList.innerHTML = "";

        if (result.errors && Object.keys(result.errors).length > 0) {
            Object.keys(result.errors).forEach(function(key) {
                const li = document.createElement("li");
                li.textContent = (DOC_LABELS[key] || key) + ": " + result.errors[key];
                errorsList.appendChild(li);
            });
            show(errorsArea);
        } else {
            hide(errorsArea);
        }

        // Store output dir for open folder button
        if (result.output_dir) {
            $("#open-folder-btn").dataset.path = result.output_dir;
        }

        show($("#results-area"));
    });

    // Open folder button
    $("#open-folder-btn").addEventListener("click", async function() {
        const path = this.dataset.path;
        if (path) {
            await window.pywebview.api.open_output_folder(path);
        }
    });
}

// ── Init ─────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", function() {
    setupLogin();
    setupLogout();
    setupDateFetch();
    setupResetDefaults();
    setupHymnFetch();
    setupFilePickers();
    setupGenerate();
    initLogin();
});
