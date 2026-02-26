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
        readingOverrides: {},  // {slot: {label, citation, intro, text_html}}
        coverImage: "",
        outputDir: "",
        liturgicalTexts: null,  // raw texts from API
        textChoices: {},        // {key: {source, isCustom, value}}
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

/** Shows login overlay when session expires. Returns true if auth error was handled. */
function handleAuthError(result) {
    if (!result || !result.auth_error) return false;
    show($("#login-overlay"));
    var form = $("#login-form");
    show(form);
    hide($("#login-spinner"));
    hideError($("#login-error"));
    showError($("#login-error"), "Session expired. Please sign in again.");
    $("#login-btn").disabled = false;
    return true;
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

/** Maps a reading label to an override slot key. */
function readingSlotKey(label) {
    var l = label.toLowerCase();
    if (l.indexOf("first") !== -1) return "first";
    if (l.indexOf("second") !== -1) return "second";
    if (l.indexOf("psalm") !== -1) return "psalm";
    if (l.indexOf("gospel") !== -1) return "gospel";
    return l;
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

// ── Update Check ─────────────────────────────────────────────────────

async function checkForUpdate() {
    try {
        var result = await window.pywebview.api.check_for_update();
        if (result.success && result.update_available) {
            var banner = $("#update-banner");
            $("#update-message").textContent =
                "Version " + result.latest + " is available (you have " + result.current + ").";
            var link = $("#update-link");
            link.href = result.download_url || "#";
            if (!result.download_url) hide(link);
            show(banner);
        }
    } catch (e) {
        // Silently ignore — update check is non-critical
    }
}

function setupUpdateBanner() {
    $("#update-dismiss").addEventListener("click", function() {
        hide($("#update-banner"));
    });
}

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
            checkForUpdate();
        } else {
            hide(spinner);
            show(form);
            btn.disabled = false;
            showError(errorEl, result.error || "Login failed");
        }
    });
}

function setupNewBulletin() {
    $("#new-bulletin-link").addEventListener("click", function(e) {
        e.preventDefault();
        resetAll();
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

    ["section-hymns", "section-liturgy", "section-details", "section-texts", "section-generate"].forEach(function(id) {
        document.getElementById(id).classList.add("disabled-section");
    });

    // Reset liturgical texts
    $("#texts-panels").innerHTML = "";
    hide($("#custom-edit-warning"));
    hideError($("#texts-error"));

    // Reset hymn slots
    $$(".hymn-number").forEach(function(el) { el.value = ""; });
    $$(".hymn-info").forEach(function(el) { hide(el); el.textContent = ""; });
    $$(".hymn-error").forEach(function(el) { hide(el); });
    $$(".hymn-clear-btn").forEach(function(el) { hide(el); });

    // Reset details
    $("#prelude-title").value = "";
    $("#prelude-performer").value = "";
    $("#postlude-title").value = "";
    $("#postlude-performer").value = "";
    $("#choral-title").value = "";
    $("#cover-image-path").textContent = "None selected";
    hide($("#cover-image-clear"));
    $("#output-dir-path").textContent = "./output";

    // Reset generate section
    $$('input[name="doc_select"]').forEach(function(el) { el.checked = true; });
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
            if (handleAuthError(result)) return;
            showError($("#date-error"), result.error || "Failed to fetch content.");
            return;
        }

        state.season = result.season;
        state.defaults = result.defaults;

        // Reset hymns and service details for the new date
        state.hymns = { gathering: null, sermon: null, communion: null, sending: null };
        state.coverImage = "";
        $$(".hymn-number").forEach(function(el) { el.value = ""; });
        $$(".hymn-info").forEach(function(el) { hide(el); el.textContent = ""; });
        $$(".hymn-error").forEach(function(el) { hide(el); });
        $$(".hymn-clear-btn").forEach(function(el) { hide(el); });
        $("#prelude-title").value = "";
        $("#prelude-performer").value = "";
        $("#postlude-title").value = "";
        $("#postlude-performer").value = "";
        $("#choral-title").value = "";
        $("#cover-image-path").textContent = "None selected";
        hide($("#cover-image-clear"));

        // Display day info
        $("#day-name").textContent = result.day_name;
        $("#day-season").textContent = seasonLabel(result.season);

        const readingsEl = $("#readings-list");
        readingsEl.innerHTML = "";
        state.readingOverrides = {};
        (result.readings || []).forEach(function(r) {
            var slot = readingSlotKey(r.label);
            var div = document.createElement("div");
            div.className = "reading-item";
            div.dataset.slot = slot;

            var labelSpan = document.createElement("span");
            labelSpan.className = "reading-label";
            labelSpan.textContent = r.label + ":";
            div.appendChild(labelSpan);

            var citationSpan = document.createElement("span");
            citationSpan.className = "reading-citation-text";
            citationSpan.textContent = " " + r.citation;
            div.appendChild(citationSpan);

            var editBtn = document.createElement("button");
            editBtn.type = "button";
            editBtn.className = "btn-link reading-edit-btn";
            editBtn.textContent = "Edit";
            editBtn.addEventListener("click", function() {
                var editArea = div.querySelector(".reading-edit-area");
                if (editArea) {
                    editArea.hidden = !editArea.hidden;
                    return;
                }
                var area = document.createElement("div");
                area.className = "reading-edit-area";
                var input = document.createElement("input");
                input.type = "text";
                input.className = "reading-citation-input";
                input.value = r.citation;
                input.placeholder = "Enter citation (e.g. Genesis 2:15-25)";
                area.appendChild(input);

                var fetchBtn = document.createElement("button");
                fetchBtn.type = "button";
                fetchBtn.className = "btn secondary reading-fetch-btn";
                fetchBtn.textContent = "Fetch";
                fetchBtn.addEventListener("click", async function() {
                    var citation = input.value.trim();
                    if (!citation) return;
                    fetchBtn.disabled = true;
                    fetchBtn.textContent = "...";
                    var result = await window.pywebview.api.fetch_custom_reading(citation);
                    fetchBtn.disabled = false;
                    fetchBtn.textContent = "Fetch";
                    var preview = area.querySelector(".reading-preview");
                    if (!preview) {
                        preview = document.createElement("div");
                        preview.className = "reading-preview";
                        area.appendChild(preview);
                    }
                    if (result.success) {
                        preview.innerHTML = '<p class="reading-preview-ok">Passage fetched. Will use custom citation.</p>';
                        state.readingOverrides[slot] = {
                            label: r.label,
                            citation: citation,
                            intro: "",
                            text_html: result.text_html,
                        };
                        citationSpan.textContent = " " + citation + " (custom)";
                    } else {
                        preview.innerHTML = '<p class="error-msg">' + escapeHtml(result.error || "Failed to fetch") + '</p>';
                    }
                });
                area.appendChild(fetchBtn);

                var resetBtn = document.createElement("button");
                resetBtn.type = "button";
                resetBtn.className = "btn-link reading-reset-btn";
                resetBtn.textContent = "Reset";
                resetBtn.addEventListener("click", function() {
                    delete state.readingOverrides[slot];
                    input.value = r.citation;
                    citationSpan.textContent = " " + r.citation;
                    var preview = area.querySelector(".reading-preview");
                    if (preview) preview.innerHTML = "";
                });
                area.appendChild(resetBtn);

                div.appendChild(area);
            });
            div.appendChild(editBtn);

            readingsEl.appendChild(div);
        });

        show($("#day-info"));

        // Enable all sections
        enableSection("section-hymns");
        enableSection("section-liturgy");
        enableSection("section-details");
        enableSection("section-texts");
        enableSection("section-generate");

        // Fetch liturgical texts for the review step
        loadLiturgicalTexts();

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

    // Confession
    var showConf = defaults.show_confession !== undefined ? defaults.show_confession : true;
    $("#show-confession").checked = showConf;
    $("#hint-confession").textContent = "Default: " + (showConf ? "Yes" : "No");

    // Nunc Dimittis
    var showNunc = defaults.show_nunc_dimittis !== undefined ? defaults.show_nunc_dimittis : true;
    $("#show-nunc-dimittis").checked = showNunc;
    $("#hint-nunc-dimittis").textContent = "Default: Yes";

    // Baptism (always unchecked by default)
    $("#include-baptism").checked = false;
    hide($("#baptism-names-group"));
    $("#baptism-names").value = "";
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

function clearHymnSlot(slot) {
    var slotName = slot.dataset.slot;
    state.hymns[slotName] = null;
    slot.querySelector(".hymn-number").value = "";
    var infoEl = slot.querySelector(".hymn-info");
    infoEl.textContent = "";
    hide(infoEl);
    hideError(slot.querySelector(".hymn-error"));
    var clearBtn = slot.querySelector(".hymn-clear-btn");
    if (clearBtn) hide(clearBtn);
}

function setupHymnFetch() {
    // Clear buttons
    $$(".hymn-clear-btn").forEach(function(btn) {
        btn.addEventListener("click", function() {
            clearHymnSlot(this.closest(".hymn-slot"));
        });
    });

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
            var clearBtn = slot.querySelector(".hymn-clear-btn");
            if (clearBtn) hide(clearBtn);
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
                    if (clearBtn) show(clearBtn);
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
                    if (clearBtn) show(clearBtn);
                    state.hymns[slotName] = {
                        number: number,
                        collection: collection,
                        title: searchResult.title,
                    };
                } else {
                    // Lyrics failed but search succeeded — still usable (title only)
                    infoEl.textContent = searchResult.title + " (title only \u2014 lyrics unavailable)";
                    show(infoEl);
                    if (clearBtn) show(clearBtn);
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
                show($("#cover-image-clear"));
            }
        } finally {
            this.disabled = false;
        }
    });

    $("#cover-image-clear").addEventListener("click", function() {
        state.coverImage = "";
        $("#cover-image-path").textContent = "None selected";
        hide(this);
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

// ── Liturgical Texts Review ──────────────────────────────────────────

/** Role options for structured (call-and-response) text entries. */
var ROLE_OPTIONS = [
    { value: "P", label: "P (Pastor)" },
    { value: "C", label: "C (Congregation)" },
    { value: "", label: "(none)" },
    { value: "instruction", label: "Instruction" },
];

/** Builds a single structured-entry row element. */
function buildEntryRow(entry) {
    var row = document.createElement("div");
    row.className = "entry-row";

    var roleSelect = document.createElement("select");
    roleSelect.className = "entry-role";
    ROLE_OPTIONS.forEach(function(opt) {
        var option = document.createElement("option");
        option.value = opt.value;
        option.textContent = opt.label;
        if (opt.value === (entry.role || "")) option.selected = true;
        roleSelect.appendChild(option);
    });
    row.appendChild(roleSelect);

    var textInput = document.createElement("input");
    textInput.type = "text";
    textInput.className = "entry-text";
    textInput.value = entry.text || "";
    row.appendChild(textInput);

    var removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "btn entry-remove-btn";
    removeBtn.textContent = "\u00d7";
    removeBtn.title = "Remove entry";
    removeBtn.addEventListener("click", function() {
        row.remove();
    });
    row.appendChild(removeBtn);

    return row;
}

/** Builds a structured editor with entry rows and an Add button. */
function buildStructuredEditor(key, entries) {
    var wrapper = document.createElement("div");
    wrapper.className = "structured-editor";
    wrapper.dataset.key = key;

    var rowsContainer = document.createElement("div");
    rowsContainer.className = "entry-rows";
    (entries || []).forEach(function(entry) {
        rowsContainer.appendChild(buildEntryRow(entry));
    });
    wrapper.appendChild(rowsContainer);

    var addBtn = document.createElement("button");
    addBtn.type = "button";
    addBtn.className = "btn secondary entry-add-btn";
    addBtn.textContent = "+ Add entry";
    addBtn.addEventListener("click", function() {
        rowsContainer.appendChild(buildEntryRow({ role: "", text: "" }));
    });
    wrapper.appendChild(addBtn);

    return wrapper;
}

/** Reads structured entries from a structured editor element. */
function collectStructuredEntries(editorEl) {
    var rows = editorEl.querySelectorAll(".entry-row");
    var entries = [];
    rows.forEach(function(row) {
        var role = row.querySelector(".entry-role").value;
        var text = row.querySelector(".entry-text").value.trim();
        if (text) {
            entries.push({ role: role, text: text });
        }
    });
    return entries;
}

/** Loads liturgical texts from the API and builds the review panels. */
async function loadLiturgicalTexts() {
    var spinner = $("#texts-spinner");
    var errorEl = $("#texts-error");
    var panelsEl = $("#texts-panels");
    hideError(errorEl);
    panelsEl.innerHTML = "";
    show(spinner);

    try {
        var result = await window.pywebview.api.get_liturgical_texts();
        hide(spinner);

        if (!result.success) {
            showError(errorEl, result.error || "Failed to load liturgical texts.");
            return;
        }

        state.liturgicalTexts = result.texts;
        state.textChoices = {};

        var textOrder = ["confession", "offering_prayer", "prayer_after_communion", "blessing", "dismissal"];
        textOrder.forEach(function(key) {
            var info = result.texts[key];
            if (!info) return;

            var isStructured = info.type === "structured";
            var defaultSource = info.has_sns ? "sns" : "standard";
            var initialData = defaultSource === "sns" ? info.sns : info.standard;

            state.textChoices[key] = {
                source: defaultSource,
                isCustom: false,
                value: isStructured ? null : (initialData || ""),
                snsData: info.sns,
                stdData: info.standard,
                type: info.type,
            };

            // Build panel
            var panel = document.createElement("div");
            panel.className = "text-panel";
            panel.dataset.key = key;

            var header = document.createElement("div");
            header.className = "text-panel-header";
            header.innerHTML = '<span class="text-panel-title">' + escapeHtml(info.label) + '</span>' +
                '<span class="text-panel-toggle">&#9660;</span>';
            header.addEventListener("click", function() {
                panel.classList.toggle("open");
            });
            panel.appendChild(header);

            var body = document.createElement("div");
            body.className = "text-panel-body";

            // No S&S notice
            if (!info.has_sns) {
                var notice = document.createElement("p");
                notice.className = "text-no-sns";
                notice.textContent = "No S&S text available for this week. Using standard text.";
                body.appendChild(notice);
            }

            // Radio toggle
            var radios = document.createElement("div");
            radios.className = "text-source-radios";

            var snsLabel = document.createElement("label");
            var snsRadio = document.createElement("input");
            snsRadio.type = "radio";
            snsRadio.name = "text_source_" + key;
            snsRadio.value = "sns";
            if (defaultSource === "sns") snsRadio.checked = true;
            if (!info.has_sns) snsRadio.disabled = true;
            snsLabel.appendChild(snsRadio);
            snsLabel.appendChild(document.createTextNode(" This Week's (S&S)"));
            radios.appendChild(snsLabel);

            var stdLabel = document.createElement("label");
            var stdRadio = document.createElement("input");
            stdRadio.type = "radio";
            stdRadio.name = "text_source_" + key;
            stdRadio.value = "standard";
            if (defaultSource === "standard") stdRadio.checked = true;
            stdLabel.appendChild(stdRadio);
            stdLabel.appendChild(document.createTextNode(" Standard"));
            radios.appendChild(stdLabel);

            body.appendChild(radios);

            if (isStructured) {
                // Structured editor for call-and-response texts
                var editor = buildStructuredEditor(key, initialData);
                body.appendChild(editor);

                // Wire radio changes — rebuild editor with new data
                [snsRadio, stdRadio].forEach(function(radio) {
                    radio.addEventListener("change", function() {
                        var choice = state.textChoices[key];
                        choice.source = this.value;
                        choice.isCustom = false;
                        var newData = this.value === "sns" ? choice.snsData : choice.stdData;
                        // Replace editor rows
                        var rowsContainer = editor.querySelector(".entry-rows");
                        rowsContainer.innerHTML = "";
                        (newData || []).forEach(function(entry) {
                            rowsContainer.appendChild(buildEntryRow(entry));
                        });
                        hide($("#custom-edit-warning"));
                    });
                });
            } else {
                // Plain textarea for simple texts
                var textarea = document.createElement("textarea");
                textarea.className = "text-textarea";
                textarea.value = initialData || "";
                textarea.dataset.key = key;
                body.appendChild(textarea);

                // Wire radio changes
                [snsRadio, stdRadio].forEach(function(radio) {
                    radio.addEventListener("change", function() {
                        var choice = state.textChoices[key];
                        choice.source = this.value;
                        choice.isCustom = false;
                        var newText = this.value === "sns" ? (choice.snsData || "") : (choice.stdData || "");
                        choice.value = newText;
                        textarea.value = newText;
                        hide($("#custom-edit-warning"));
                    });
                });

                // Wire textarea edits
                textarea.addEventListener("input", function() {
                    var choice = state.textChoices[key];
                    choice.value = this.value;
                    var matchesSns = this.value === (choice.snsData || "");
                    var matchesStd = this.value === (choice.stdData || "");
                    choice.isCustom = !matchesSns && !matchesStd;
                    if (choice.isCustom) {
                        show($("#custom-edit-warning"));
                    }
                });
            }

            panel.appendChild(body);
            panelsEl.appendChild(panel);
        });
    } catch (err) {
        hide(spinner);
        showError(errorEl, "Failed to load texts: " + (err.message || "unknown error"));
    }
}

function escapeHtml(str) {
    var div = document.createElement("div");
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
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
        show_confession: $("#show-confession").checked,
        show_nunc_dimittis: $("#show-nunc-dimittis").checked,
        include_baptism: $("#include-baptism").checked,
        baptism_candidate_names: $("#baptism-names").value.trim(),
        prelude_title: $("#prelude-title").value.trim(),
        prelude_performer: $("#prelude-performer").value.trim(),
        postlude_title: $("#postlude-title").value.trim(),
        postlude_performer: $("#postlude-performer").value.trim(),
        choral_title: $("#choral-title").value.trim(),
        cover_image: state.coverImage,
        output_dir: state.outputDir || "output",
        selected_docs: Array.from($$('input[name="doc_select"]:checked')).map(function(el) { return el.value; }),
    };

    // Reading overrides
    if (state.readingOverrides && Object.keys(state.readingOverrides).length > 0) {
        formData.reading_overrides = state.readingOverrides;
    }

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

    // Liturgical texts
    var tc = state.textChoices;

    // Structured texts: collect entries from the editor rows
    ["confession", "dismissal"].forEach(function(key) {
        if (!tc[key]) return;
        var editorEl = document.querySelector('.structured-editor[data-key="' + key + '"]');
        if (editorEl) {
            formData[key + "_entries"] = collectStructuredEntries(editorEl);
        }
    });

    // Plain texts: collect from textarea value
    ["offering_prayer", "prayer_after_communion", "blessing"].forEach(function(key) {
        if (tc[key]) {
            formData[key + "_text"] = tc[key].value || "";
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

        var selectedDocs = $$('input[name="doc_select"]:checked');
        if (selectedDocs.length === 0) {
            showError(errorEl, "Select at least one document to generate.");
            return;
        }

        const formData = collectFormData();

        // Check for existing files before generating
        var checkResult = await window.pywebview.api.check_existing_files(
            formData.output_dir, formData.selected_docs
        );
        if (checkResult.existing && checkResult.existing.length > 0) {
            var ok = confirm(
                "The following files will be overwritten:\n\n" +
                checkResult.existing.join("\n") +
                "\n\nContinue?"
            );
            if (!ok) return;
        }

        this.disabled = true;
        show($("#progress-area"));
        $("#progress-fill").style.width = "0%";
        $("#progress-status").textContent = "Starting generation...";
        const bar = document.querySelector(".progress-bar");
        if (bar) bar.setAttribute("aria-valuenow", 0);

        const result = await window.pywebview.api.generate_all(formData);

        this.disabled = false;

        if (result.error && !result.results) {
            hide($("#progress-area"));
            if (handleAuthError(result)) return;
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

        hide($("#progress-area"));

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

function setupBaptismToggle() {
    $("#include-baptism").addEventListener("change", function() {
        if (this.checked) {
            show($("#baptism-names-group"));
        } else {
            hide($("#baptism-names-group"));
            $("#baptism-names").value = "";
        }
    });
}

document.addEventListener("DOMContentLoaded", function() {
    setupLogin();
    setupLogout();
    setupNewBulletin();
    setupUpdateBanner();
    setupDateFetch();
    setupResetDefaults();
    setupHymnFetch();
    setupFilePickers();
    setupGenerate();
    setupBaptismToggle();
    initLogin();
});
