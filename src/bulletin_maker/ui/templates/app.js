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

/** Liturgical season colors for the season bar. */
const SEASON_COLORS = {
    advent:       "#2B5EA0",
    christmas:    "#8A6414",
    epiphany:     "#2E7D32",
    lent:         "#5B2882",
    easter:       "#8A6414",
    pentecost:    "#2E7D32",
    christmas_eve:"#8A6414",
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

/** Wizard panel IDs in step order. */
const STEP_IDS = ["step-date-music", "step-liturgy-texts", "step-review-generate"];

// ── State ────────────────────────────────────────────────────────────

/** Returns a fresh initial state object. */
function initialState() {
    return {
        currentStep: 1,
        dateStr: "",          // "2026-02-22" (HTML input value)
        dateDisplay: "",      // "February 22, 2026"
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
    showAuthForm("#login-form");
    showError($("#login-error"), "Session expired. Please sign in again.");
    $("#login-btn").disabled = false;
    return true;
}

/** Replace button text with an inline spinner ring. */
function showBtnSpinner(btn) {
    btn._savedText = btn.textContent;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-ring" style="width:14px;height:14px;border-width:2px;display:inline-block;vertical-align:middle;"></span>';
}

/** Restore button text after spinner. */
function hideBtnSpinner(btn, text) {
    btn.disabled = false;
    btn.textContent = text || btn._savedText || "Fetch";
}

function showWarning(el, msg) {
    el.textContent = msg;
    show(el);
}

function hideWarning(el) {
    el.textContent = "";
    hide(el);
}

function getMemorialAcclamationMode() {
    var selected = document.querySelector('input[name="memorial_acclamation_mode"]:checked');
    return selected ? selected.value : null;
}

function setMemorialAcclamationMode(mode) {
    $$('input[name="memorial_acclamation_mode"]').forEach(function(el) {
        el.checked = !!mode && el.value === mode;
    });
}

function getOffertoryType() {
    var selected = document.querySelector('input[name="offertory_type"]:checked');
    return selected ? selected.value : "offertory";
}

function setOffertoryType(type) {
    var value = type === "choral_anthem" ? "choral_anthem" : "offertory";
    $$('input[name="offertory_type"]').forEach(function(el) {
        el.checked = el.value === value;
    });
}

function offertoryTypeLabel(type) {
    return type === "choral_anthem" ? "Choral Anthem" : "Offertory";
}

function updateMemorialAcclamationModeControls() {
    var include = $("#include-memorial").checked;
    $$('input[name="memorial_acclamation_mode"]').forEach(function(el) {
        el.disabled = !include;
    });
    var group = $("#memorial-format-group");
    if (group) group.classList.toggle("disabled", !include);
    if (!include) {
        var settingsError = $("#settings-error");
        if (settingsError) hideError(settingsError);
    }
}

function validateMemorialAcclamationMode(errorEl) {
    if ($("#include-memorial").checked && !getMemorialAcclamationMode()) {
        showError(errorEl, "Choose whether Memorial Acclamation is sung music or spoken text.");
        return false;
    }
    hideError(errorEl);
    return true;
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

/** Apply liturgical season color to the season bar. */
function applySeasonTheme(season) {
    var color = SEASON_COLORS[season];
    if (color) {
        document.documentElement.style.setProperty("--season-accent", color);
    }
    var bar = $("#season-bar");
    if (bar) {
        $("#season-bar-label").textContent = seasonLabel(season);
        show(bar);
    }
}

/** Clear season bar and reset accent color. */
function clearSeasonTheme() {
    document.documentElement.style.removeProperty("--season-accent");
    var bar = $("#season-bar");
    if (bar) hide(bar);
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

// ── Server API adapter ───────────────────────────────────────────────
// Talks to the FastAPI backend. Method names mirror the old pywebview
// bridge so call sites read the same; failures resolve to
// {success:false, error, error_type, auth_error?} rather than throwing.
var api = (function() {
    var lastDayResponse = null;
    var hymnCache = {};       // "COLL_NUM" -> merged hymn response
    var lastJobId = null;

    async function req(method, url, body) {
        var opts = { method: method, headers: {} };
        if (body !== undefined) {
            opts.headers["Content-Type"] = "application/json";
            opts.body = JSON.stringify(body);
        }
        var resp;
        try {
            resp = await fetch(url, opts);
        } catch (e) {
            return { success: false, error_type: "network",
                     error: "Cannot reach the Bulletin Maker server. Is it still running?" };
        }
        var data = null;
        try { data = await resp.json(); } catch (e) {}
        if (!resp.ok) {
            var detail = (data && data.detail) || {};
            var failure = {
                success: false,
                error: detail.error || ("Server error (HTTP " + resp.status + ")"),
                error_type: detail.error_type || "internal",
                auth_error: !!detail.auth_error,
            };
            // Expired sessions re-open the sign-in overlay from ANY call
            if (failure.auth_error) handleAuthError(failure);
            return failure;
        }
        if (data === null) {
            return { success: false, error_type: "internal",
                     error: "The server sent an unexpected response — please try again." };
        }
        return data;
    }

    var methods = {
        login: function(email, password) {
            return req("POST", "/api/session", { email: email, password: password });
        },
        register: function(payload) { return req("POST", "/api/register", payload); },
        join: function(payload) { return req("POST", "/api/join", payload); },
        whoami: function() { return req("GET", "/api/session"); },
        instance_info: function() { return req("GET", "/api/instance"); },
        logout: function() { return req("DELETE", "/api/session"); },
        get_church: function() { return req("GET", "/api/church"); },
        update_church_profile: function(payload) {
            return req("PUT", "/api/church/profile", payload);
        },
        link_sns: function(username, password) {
            return req("PUT", "/api/church/sns-link",
                       { username: username, password: password });
        },
        get_preface_options: function() { return req("GET", "/api/prefaces"); },

        fetch_day_content: async function(dateStr, dateDisplay) {
            var result = await req("GET", "/api/day?date=" + encodeURIComponent(dateStr) +
                                   "&display=" + encodeURIComponent(dateDisplay));
            if (result.success) lastDayResponse = result;
            return result;
        },
        get_file_prefix: function() {
            if (lastDayResponse && lastDayResponse.prefix) {
                return Promise.resolve({ success: true, prefix: lastDayResponse.prefix });
            }
            return Promise.resolve({ success: false, error: "No content fetched yet.",
                                     error_type: "validation" });
        },
        get_liturgical_texts: function() { return req("GET", "/api/day/texts"); },
        get_reading_preview: function(slot) {
            return req("GET", "/api/day/readings/" + encodeURIComponent(slot) + "/preview");
        },
        fetch_custom_reading: function(citation) {
            return req("POST", "/api/passage", { citation: citation });
        },

        // The server merges search + lyrics into one endpoint; both old
        // bridge methods resolve from it (cached per hymn).
        search_hymn: async function(number, collection) {
            var result = await req("GET", "/api/hymns/" + encodeURIComponent(collection) +
                                   "/" + encodeURIComponent(number) +
                                   "?date=" + encodeURIComponent(state.dateStr || ""));
            if (result.success) {
                hymnCache[collection + "_" + number] = result;
            }
            return result;
        },

        save_past_run: function(formData, metadata) {
            return req("POST", "/api/runs", { form_data: formData, metadata: metadata });
        },
        get_past_runs: function() { return req("GET", "/api/runs"); },
        get_past_run: function(runId) { return req("GET", "/api/runs/" + encodeURIComponent(runId)); },
        delete_past_run: function(runId) { return req("DELETE", "/api/runs/" + encodeURIComponent(runId)); },

        upload_cover: async function(file) {
            var fd = new FormData();
            fd.append("file", file, file.name);
            var resp;
            try {
                resp = await fetch("/api/cover", { method: "POST", body: fd });
            } catch (e) {
                return { success: false, error: "Upload failed.", error_type: "network" };
            }
            var data = null;
            try { data = await resp.json(); } catch (e) {}
            if (!resp.ok) {
                var detail = (data && data.detail) || {};
                return { success: false, error: detail.error || "Upload failed.",
                         error_type: detail.error_type || "internal" };
            }
            return data;
        },

        generate_all: async function(formData) {
            var start = await req("POST", "/api/generate", formData);
            if (!start.success) return start;
            lastJobId = start.job_id;
            var seen = 0;
            for (;;) {
                // Poll every 700ms; when a backgrounded tab returns to
                // focus, check immediately instead of waiting out the
                // browser's throttled timer.
                await new Promise(function(r) {
                    var timer = setTimeout(done, 700);
                    function done() {
                        clearTimeout(timer);
                        document.removeEventListener("visibilitychange", onVisible);
                        r();
                    }
                    function onVisible() {
                        if (!document.hidden) done();
                    }
                    document.addEventListener("visibilitychange", onVisible);
                });
                var status = await req("GET", "/api/jobs/" + lastJobId);
                if (!status.success) return status;
                (status.progress || []).slice(seen).forEach(function(entry) {
                    updateProgress(entry);
                });
                seen = (status.progress || []).length;
                if (status.status !== "running") {
                    return { success: status.status === "done",
                             results: status.results, errors: status.errors };
                }
            }
        },
        file_url: function(docKey) {
            return "/api/jobs/" + lastJobId + "/files/" + encodeURIComponent(docKey);
        },
        zip_url: function() { return "/api/jobs/" + lastJobId + "/zip"; },
    };
    return methods;
})();

// Allowlist sanitizer for S&S-derived HTML (previews). Keeps textual
// structure, drops every attribute except class and any non-listed tag.
var SANITIZE_ALLOWED_TAGS = {
    P: 1, BR: 1, DIV: 1, SPAN: 1, SUP: 1, SUB: 1, EM: 1, STRONG: 1,
    B: 1, I: 1, H3: 1, H4: 1, UL: 1, OL: 1, LI: 1,
};

function sanitizeHtml(html) {
    var template = document.createElement("template");
    template.innerHTML = html || "";
    (function walk(node) {
        var children = Array.from(node.children || []);
        children.forEach(function(el) {
            if (!SANITIZE_ALLOWED_TAGS[el.tagName]) {
                el.replaceWith(document.createTextNode(el.textContent || ""));
                return;
            }
            Array.from(el.attributes).forEach(function(attr) {
                if (attr.name !== "class") el.removeAttribute(attr.name);
            });
            walk(el);
        });
    })(template.content);
    return template.innerHTML;
}

function escapeHtml(str) {
    var div = document.createElement("div");
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}

/** Returns the next Sunday's date as "YYYY-MM-DD". */
function getNextSunday() {
    var d = new Date();
    d.setDate(d.getDate() + ((7 - d.getDay()) % 7 || 7));
    var y = d.getFullYear();
    var m = String(d.getMonth() + 1).padStart(2, "0");
    var day = String(d.getDate()).padStart(2, "0");
    return y + "-" + m + "-" + day;
}

// ── Wizard Navigation ────────────────────────────────────────────────

/** Shows the given step (1-based) and updates step indicator. */
function showStep(n) {
    state.currentStep = n;
    STEP_IDS.forEach(function(id, i) {
        var panel = document.getElementById(id);
        if (i === n - 1) {
            panel.classList.add("active");
        } else {
            panel.classList.remove("active");
        }
    });
    $$(".wizard-step").forEach(function(stepEl) {
        var stepNum = parseInt(stepEl.dataset.step);
        stepEl.classList.remove("active", "completed");
        if (stepNum === n) {
            stepEl.classList.add("active");
        } else if (stepNum < n) {
            stepEl.classList.add("completed");
        }
    });
    if (n === STEP_IDS.length) {
        buildReadinessSummary();
        buildReviewOutline();
    }
    window.scrollTo(0, 0);
    var heading = document.querySelector(".wizard-panel.active h2");
    if (heading) {
        heading.setAttribute("tabindex", "-1");
        heading.focus({ preventScroll: true });
    }
}

/** Validates whether the user can leave the given step. */
function validateStep(n) {
    if (n === 1) {
        return !!state.dateStr && !!state.season;
    }
    if (n === 2) {
        return validateMemorialAcclamationMode($("#settings-error"));
    }
    return true;
}

/** Wires up Next/Back buttons and step indicator clicks. */
function setupWizardStepKeys() {
    $$(".wizard-step").forEach(function(stepEl) {
        stepEl.setAttribute("role", "button");
        stepEl.setAttribute("tabindex", "0");
        stepEl.addEventListener("keydown", function(e) {
            if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                stepEl.click();
            }
        });
    });
}

function setupWizardNav() {
    $$(".wizard-next-btn").forEach(function(btn) {
        btn.addEventListener("click", function() {
            var panel = this.closest(".wizard-panel");
            var currentIdx = STEP_IDS.indexOf(panel.id);
            var stepNum = currentIdx + 1;
            if (!validateStep(stepNum)) {
                if (stepNum === 1) {
                    showError($("#date-error"), "Please fetch content for a date before continuing.");
                }
                return;
            }
            if (currentIdx < STEP_IDS.length - 1) {
                showStep(currentIdx + 2);
            }
        });
    });

    $$(".wizard-back-btn").forEach(function(btn) {
        btn.addEventListener("click", function() {
            var panel = this.closest(".wizard-panel");
            var currentIdx = STEP_IDS.indexOf(panel.id);
            if (currentIdx > 0) {
                showStep(currentIdx);
            }
        });
    });

    $$(".wizard-step").forEach(function(stepEl) {
        stepEl.addEventListener("click", function() {
            var targetStep = parseInt(this.dataset.step);
            if (targetStep < state.currentStep) {
                showStep(targetStep);
            } else if (targetStep === state.currentStep + 1 && validateStep(state.currentStep)) {
                showStep(targetStep);
            }
        });
    });
}

// ── Readiness Summary ────────────────────────────────────────────────

/** Builds a readiness checklist at the top of Step 4 review. */
function buildReadinessSummary() {
    var el = $("#readiness-summary");
    el.innerHTML = "";

    var hymnCount = ["gathering", "sermon", "communion", "sending"].filter(function(s) {
        return state.hymns[s] && state.hymns[s].number;
    }).length;

    var docCount = $$('input[name="doc_select"]:checked').length;
    var memorialIncluded = $("#include-memorial").checked;
    var memorialMode = getMemorialAcclamationMode();

    var items = [
        { label: "Date", ok: !!state.dateStr, detail: state.dateStr ? state.dateDisplay : "Not set" },
        { label: "Hymns", ok: hymnCount > 0, detail: hymnCount + " of 4 set" },
        { label: "Output", ok: true, detail: "Downloads in your browser" },
        { label: "Prints", ok: true,
          detail: (state.paperLabel || "Legal booklet") + " \u00b7 " + (state.settingLabel || "Setting Two") },
        { label: "Docs", ok: docCount > 0, detail: docCount + " selected" },
        {
            label: "Memorial Acc.",
            ok: !memorialIncluded || !!memorialMode,
            detail: memorialIncluded
                ? (memorialMode === "sung" ? "Sung music" : memorialMode === "spoken" ? "Spoken text" : "Choose sung or spoken")
                : "Omitted",
        },
    ];

    items.forEach(function(item) {
        var row = document.createElement("div");
        row.className = "readiness-item " + (item.ok ? "ok" : "missing");
        var icon = document.createElement("span");
        icon.className = "readiness-icon";
        icon.textContent = item.ok ? "\u2713" : "!";
        row.appendChild(icon);
        var label = document.createElement("span");
        label.className = "readiness-label";
        label.textContent = item.label;
        row.appendChild(label);
        var detail = document.createElement("span");
        detail.className = "readiness-detail";
        detail.textContent = item.detail;
        row.appendChild(detail);
        el.appendChild(row);
    });
}

// ── Review Outline Builder ───────────────────────────────────────────

/** Returns an outline item object for a hymn slot. */
function hymnOutlineItem(label, slotName) {
    var hymn = state.hymns[slotName];
    if (hymn && hymn.number) {
        return { label: label, value: hymn.collection + " " + hymn.number + " \u2014 " + hymn.title };
    }
    return { label: label, value: "(not set)", empty: true };
}

/** Returns the source label for a liturgical text choice. */
function getTextSourceLabel(key) {
    var tc = state.textChoices[key];
    if (!tc) return "This Week\u2019s (S&S)";
    if (tc.isCustom) return "Custom edit";
    var opt = (tc.options || []).find(function(o) { return o.key === tc.source; });
    return opt ? opt.label : tc.source;
}

/** Returns a preview string for a liturgical text choice. */
function getTextPreview(key) {
    var tc = state.textChoices[key];
    if (!tc) return "";

    if (tc.type === "structured") {
        // Read current entries from the DOM editor if available
        var editor = document.querySelector('.structured-editor[data-key="' + key + '"]');
        if (editor) {
            var rows = editor.querySelectorAll(".entry-row");
            var lines = [];
            rows.forEach(function(row) {
                var role = row.querySelector(".entry-role");
                var text = row.querySelector(".entry-text");
                if (role && text) {
                    var r = role.value;
                    var t = (text.value || text.textContent || "").trim();
                    if (t) lines.push((r ? r + ": " : "") + t);
                }
            });
            return lines.join("\n");
        }
        // Fallback: use the selected option's data
        var data = findOptionData(tc.options, tc.source);
        if (Array.isArray(data)) {
            return data.map(function(e) {
                return (e[0] ? e[0] + ": " : "") + e[1];
            }).join("\n");
        }
        return "";
    }

    // Plain text
    if (tc.value) return tc.value;
    var opt = findOptionData(tc.options, tc.source);
    return typeof opt === "string" ? opt : "";
}

/** Returns the gospel acclamation label for the current season. */
function getGospelAccLabel() {
    var season = state.season;
    if (season === "advent") return "\u201CWait for the Lord\u201D";
    if (season === "lent") return "Lenten verse";
    return "Alleluia";
}

/** Builds the visual liturgy outline in Step 4. */
function buildReviewOutline() {
    var outline = $("#review-outline");
    outline.innerHTML = "";

    var dayName = $("#day-name") ? ($("#day-name").textContent || "Sunday Service") : "Sunday Service";

    var title = document.createElement("div");
    title.className = "outline-title";
    title.textContent = "SERVICE ORDER \u2014 " + dayName;
    outline.appendChild(title);

    var divider = document.createElement("div");
    divider.className = "outline-divider";
    outline.appendChild(divider);

    var list = document.createElement("div");
    list.className = "outline-list";

    var items = [];

    // Prelude
    var pt = $("#prelude-title").value.trim();
    var pc = $("#prelude-composer").value.trim();
    var preludeVal = "";
    if (pt || pc) {
        preludeVal = (pt ? "\u201C" + pt + "\u201D" : "") + (pc ? " \u2014 " + pc : "");
    }
    items.push({ label: "Prelude", value: preludeVal || "(not set)", empty: !preludeVal });

    var baptismOn = $("#include-baptism").checked;
    var baptismNames = $("#baptism-names").value.trim();

    // Confession
    var showConf = $("#show-confession").checked;
    items.push({ label: "Confession", value: showConf ? getTextSourceLabel("confession") : "(omitted)", empty: !showConf, textKey: showConf ? "confession" : null });

    // Gathering Hymn
    items.push(hymnOutlineItem("Gathering Hymn", "gathering"));

    // Kyrie
    var hasKyrie = $("#include-kyrie").checked;
    items.push({ label: "Kyrie", value: hasKyrie ? (state.settingLabel || "Sung setting") : "(omitted)", empty: !hasKyrie });

    // Canticle
    var canticleEl = document.querySelector('input[name="canticle"]:checked');
    var canticleVal = canticleEl ? canticleEl.value : "none";
    items.push({ label: "Canticle", value: canticleVal === "none" ? "(omitted)" : (CANTICLE_LABELS[canticleVal] || canticleVal), empty: canticleVal === "none" });

    // Prayer of Day
    items.push({ label: "Prayer of Day", value: "This Week\u2019s (S&S)", textKey: "prayer_of_day" });

    // Readings
    var readings = $$("#readings-list .reading-item");
    readings.forEach(function(r) {
        var label = r.querySelector(".reading-label").textContent.replace(":", "").trim();
        var citation = r.querySelector(".reading-citation-text").textContent.trim();
        items.push({ label: label, value: citation || "(not set)", empty: !citation });
    });
    if (readings.length === 0) {
        items.push({ label: "Readings", value: "(not fetched)", empty: true });
    }

    // Gospel Acclamation
    items.push({ label: "Gospel Acc.", value: getGospelAccLabel() });

    // Sermon
    items.push({ label: "Sermon", value: "" });

    // Sermon Hymn
    items.push(hymnOutlineItem("Sermon Hymn", "sermon"));

    // Creed (or Baptism replacing creed)
    var creedEl = document.querySelector('input[name="creed_type"]:checked');
    var creedType = creedEl ? creedEl.value : "apostles";
    if (baptismOn) {
        items.push({ label: "BAPTISM", value: (baptismNames || "(names not set)") + " (replaces Creed)", extra: true });
    } else {
        items.push({ label: "Creed", value: creedType === "nicene" ? "Nicene Creed" : "Apostles\u2019 Creed" });
    }

    // Prayers
    items.push({ label: "Prayers", value: "This Week\u2019s (S&S)" });

    // Offering Prayer
    items.push({ label: "Offering Prayer", value: getTextSourceLabel("offering_prayer"), textKey: "offering_prayer" });

    // Offertory
    var offertoryType = getOffertoryType();
    var ot = $("#offertory-title").value.trim();
    var oc = $("#offertory-composer").value.trim();
    var op = $("#offertory-performer").value.trim();
    var offVal = "";
    if (ot || oc || op) {
        offVal = (ot ? "\u201C" + ot + "\u201D" : "") + (oc ? " \u2014 " + oc : "") + (op ? " / " + op : "");
    }
    items.push({ label: offertoryTypeLabel(offertoryType), value: offVal || "(not set)", empty: !offVal });

    // Choral
    var choralTitle = $("#choral-title").value.trim();
    var choralComposer = $("#choral-composer").value.trim();
    if (choralTitle) {
        items.push({
            label: "Choral Call",
            value: "\u201C" + choralTitle + "\u201D" + (choralComposer ? " \u2014 " + choralComposer : ""),
        });
    }

    // Memorial Acclamation
    var memorialIncluded = $("#include-memorial").checked;
    var memorialMode = getMemorialAcclamationMode();
    items.push({
        label: "Memorial Acc.",
        value: memorialIncluded
            ? (memorialMode === "sung" ? "Sung music" : memorialMode === "spoken" ? "Spoken text" : "(choose sung or spoken)")
            : "(omitted)",
        empty: memorialIncluded && !memorialMode,
    });

    // Communion Hymn
    items.push(hymnOutlineItem("Communion Hymn", "communion"));

    // Prayer After Communion
    items.push({ label: "Prayer After Comm.", value: getTextSourceLabel("prayer_after_communion"), textKey: "prayer_after_communion" });

    // Blessing
    items.push({ label: "Blessing", value: getTextSourceLabel("blessing"), textKey: "blessing" });

    // Sending Hymn
    items.push(hymnOutlineItem("Sending Hymn", "sending"));

    // Dismissal
    items.push({ label: "Dismissal", value: getTextSourceLabel("dismissal"), textKey: "dismissal" });

    // Postlude
    var pot = $("#postlude-title").value.trim();
    var poc = $("#postlude-composer").value.trim();
    var postVal = "";
    if (pot || poc) {
        postVal = (pot ? "\u201C" + pot + "\u201D" : "") + (poc ? " \u2014 " + poc : "");
    }
    items.push({ label: "Postlude", value: postVal || "(not set)", empty: !postVal });

    // Render items
    items.forEach(function(item) {
        var wrapper = document.createElement("div");
        wrapper.className = "outline-item-wrapper";

        var row = document.createElement("div");
        row.className = "outline-item";
        if (item.extra) row.classList.add("outline-extra");
        if (item.empty) row.classList.add("outline-empty");

        var labelSpan = document.createElement("span");
        labelSpan.className = "outline-label";
        labelSpan.textContent = (item.extra ? "* " : "") + item.label;
        row.appendChild(labelSpan);

        if (item.value) {
            var valueSpan = document.createElement("span");
            valueSpan.className = "outline-value";
            valueSpan.textContent = item.value;
            row.appendChild(valueSpan);
        }

        // Preview toggle for liturgical texts
        if (item.textKey) {
            var peekBtn = document.createElement("button");
            peekBtn.type = "button";
            peekBtn.className = "outline-peek-btn";
            peekBtn.textContent = "\u25B6";
            peekBtn.title = "Preview text";
            (function(key) {
                peekBtn.addEventListener("click", function(e) {
                    e.stopPropagation();
                    var existing = wrapper.querySelector(".outline-peek");
                    if (existing) {
                        existing.hidden = !existing.hidden;
                        peekBtn.textContent = existing.hidden ? "\u25B6" : "\u25BC";
                        return;
                    }
                    var peek = document.createElement("div");
                    peek.className = "outline-peek";
                    var text = getTextPreview(key);
                    if (text) {
                        peek.textContent = text;
                    } else {
                        peek.textContent = "(no text available)";
                        peek.classList.add("outline-empty");
                    }
                    wrapper.appendChild(peek);
                    peekBtn.textContent = "\u25BC";
                });
            })(item.textKey);
            row.appendChild(peekBtn);
        }

        wrapper.appendChild(row);
        list.appendChild(wrapper);
    });

    outline.appendChild(list);
}

// ── Progress callback (called from Python via evaluate_js) ──────────

window.updateProgress = function(data) {
    // Route update-step progress to the banner progress bar
    const fill = document.getElementById("progress-fill");
    const status = document.getElementById("progress-status");
    const bar = document.querySelector(".progress-bar");
    if (fill) fill.style.width = data.pct + "%";
    if (status) status.textContent = data.detail;
    if (bar) bar.setAttribute("aria-valuenow", data.pct);
};

// ── Update Check ─────────────────────────────────────────────────────


// ── Login ────────────────────────────────────────────────────────────

function _authForms() {
    return [$("#login-form"), $("#register-form"), $("#join-form")];
}

function showAuthForm(id) {
    _authForms().forEach(function(f) { hide(f); });
    ["#login-error", "#register-error", "#join-error"].forEach(function(sel) {
        hideError($(sel));
    });
    hide($("#login-spinner"));
    show($(id));
}

/** Post-auth entry: reveal the app and personalize the header. */
function enterApp(auth) {
    hide($("#login-overlay"));
    show($("#app"));
    var user = auth.user || {};
    $("#user-display").textContent = user.display_name || user.email || "";
    $("#church-display").textContent = (auth.church && auth.church.name) || "";
    document.title = "Bulletin Maker — " + ((auth.church && auth.church.name) || "");
    state.isAdmin = user.role === "admin";
    state.snsLinked = !!auth.sns_linked;
    loadChurchLabels();
    if (!state.snsLinked) {
        showWarning($("#date-warning"),
            state.isAdmin
                ? "No Sundays & Seasons account is linked yet — open Settings to link one before fetching content."
                : "No Sundays & Seasons account is linked yet — ask your church admin to link one under Settings.");
    }
    loadPastRuns();
}

/** Cache the church's setting/paper labels for the review outline. */
async function loadChurchLabels() {
    var result = await api.get_church();
    if (!result.success) return;
    var profile = result.profile || {};
    function labelFor(options, key) {
        var found = (options || []).filter(function(o) { return o.key === key; })[0];
        return found ? found.label : key;
    }
    state.settingLabel = labelFor(result.options.liturgical_setting,
                                  profile.liturgical_setting);
    state.paperLabel = labelFor(result.options.paper_size, profile.paper_size);
}

async function initAuth() {
    var who = await api.whoami();
    if (who.success && who.authenticated) {
        enterApp(who);
        return;
    }
    // Show the registration-code field only when this server requires it
    var info = await api.instance_info();
    if (info.success && info.has_churches) {
        show($("#register-code-field"));
    }
}

async function _submitAuth(action, errorEl, form) {
    hideError(errorEl);
    hide(form);
    show($("#login-spinner"));
    var result = await action();
    hide($("#login-spinner"));
    if (result && result.success) {
        enterApp(result);
    } else {
        show(form);
        showError(errorEl, (result && result.error) || "Something went wrong.");
    }
}

function setupAuth() {
    $("#show-register-link").addEventListener("click", function(e) {
        e.preventDefault();
        showAuthForm("#register-form");
    });
    $("#show-join-link").addEventListener("click", function(e) {
        e.preventDefault();
        showAuthForm("#join-form");
    });
    $$(".show-login-link").forEach(function(link) {
        link.addEventListener("click", function(e) {
            e.preventDefault();
            showAuthForm("#login-form");
        });
    });

    $("#login-form").addEventListener("submit", function(e) {
        e.preventDefault();
        var email = $("#login-email").value.trim();
        var password = $("#login-password").value;
        if (!email || !password) return;
        _submitAuth(function() { return api.login(email, password); },
                    $("#login-error"), $("#login-form"));
    });

    $("#register-form").addEventListener("submit", function(e) {
        e.preventDefault();
        _submitAuth(function() {
            return api.register({
                church_name: $("#register-church").value.trim(),
                display_name: $("#register-name").value.trim(),
                email: $("#register-email").value.trim(),
                password: $("#register-password").value,
                registration_code: $("#register-code").value.trim(),
            });
        }, $("#register-error"), $("#register-form"));
    });

    $("#join-form").addEventListener("submit", function(e) {
        e.preventDefault();
        _submitAuth(function() {
            return api.join({
                invite_code: $("#join-code").value.trim(),
                display_name: $("#join-name").value.trim(),
                email: $("#join-email").value.trim(),
                password: $("#join-password").value,
            });
        }, $("#join-error"), $("#join-form"));
    });
}

// ── Church settings panel ────────────────────────────────────────────

function showSettingsPanel(visible) {
    // Hide the wizard via inline display so its own active-class state
    // is untouched and restores exactly when settings closes.
    document.querySelector(".wizard-nav").hidden = visible;
    $$(".wizard-panel").forEach(function(panel) {
        panel.style.display = visible ? "none" : "";
    });
    $("#settings-panel").hidden = !visible;
    if (visible) window.scrollTo(0, 0);
}

function _fillSelect(select, options, selectedKey) {
    select.innerHTML = "";
    options.forEach(function(opt) {
        var el = document.createElement("option");
        el.value = opt.key;
        el.textContent = opt.label;
        if (opt.key === selectedKey) el.selected = true;
        select.appendChild(el);
    });
}

async function openSettings() {
    var result = await api.get_church();
    if (!result.success) {
        showError($("#generate-error"), result.error || "Could not load settings.");
        return;
    }
    var profile = result.profile || {};
    $("#set-church-name").value = profile.church_name || "";
    $("#set-address").value = (profile.address_lines || []).join("\n");
    $("#set-service-time").value = profile.service_time || "";
    $("#set-welcome").value = profile.welcome_message || "";
    $("#set-standing").value = profile.standing_instructions || "";
    $("#set-copyright").value = (profile.copyright_paragraphs || []).join("\n");
    _fillSelect($("#set-setting"), result.options.liturgical_setting,
                profile.liturgical_setting);
    _fillSelect($("#set-paper"), result.options.paper_size, profile.paper_size);

    var editable = !!result.is_admin;
    $$("#settings-panel input, #settings-panel textarea, #settings-panel select")
        .forEach(function(el) { el.disabled = !editable; });
    $("#settings-save-btn").hidden = !editable;
    $("#settings-admin-hint").textContent = editable
        ? "These details print on every bulletin."
        : "These details print on every bulletin. Only a church admin can change them.";

    $("#sns-card").hidden = !editable;
    $("#invite-card").hidden = !editable;
    if (editable) {
        var status = $("#sns-status");
        if (result.sns_linked) {
            status.textContent = "Linked (" + (result.sns_username || "") + ")";
            status.className = "sns-status-linked";
        } else {
            status.textContent = "Not linked";
            status.className = "sns-status-unlinked";
        }
        $("#sns-username").value = result.sns_username || "";
        $("#sns-password").value = "";
        $("#invite-code").textContent = result.invite_code || "";
    }

    hide($("#settings-saved"));
    hideError($("#settings-error"));
    hide($("#sns-saved"));
    hideError($("#sns-error"));
    showSettingsPanel(true);
}

function _linesToList(value) {
    return value.split("\n")
        .map(function(line) { return line.trim(); })
        .filter(Boolean);
}

function setupSettings() {
    $("#settings-link").addEventListener("click", function(e) {
        e.preventDefault();
        openSettings();
    });
    $("#settings-back-btn").addEventListener("click", function() {
        showSettingsPanel(false);
    });

    $("#settings-save-btn").addEventListener("click", async function() {
        hide($("#settings-saved"));
        hideError($("#settings-error"));
        showBtnSpinner(this);
        var result = await api.update_church_profile({
            church_name: $("#set-church-name").value.trim(),
            address_lines: _linesToList($("#set-address").value),
            service_time: $("#set-service-time").value.trim(),
            welcome_message: $("#set-welcome").value.trim(),
            standing_instructions: $("#set-standing").value,
            copyright_paragraphs: _linesToList($("#set-copyright").value),
            liturgical_setting: $("#set-setting").value,
            paper_size: $("#set-paper").value,
        });
        hideBtnSpinner(this, "Save Settings");
        if (!result.success) {
            showError($("#settings-error"), result.error || "Could not save.");
            return;
        }
        show($("#settings-saved"));
        $("#church-display").textContent = result.profile.church_name;
        loadChurchLabels();
    });

    $("#sns-link-btn").addEventListener("click", async function() {
        hide($("#sns-saved"));
        hideError($("#sns-error"));
        var username = $("#sns-username").value.trim();
        var password = $("#sns-password").value;
        if (!username || !password) {
            showError($("#sns-error"), "Enter the S&S email and password.");
            return;
        }
        showBtnSpinner(this);
        var result = await api.link_sns(username, password);
        hideBtnSpinner(this, "Link Account");
        if (!result.success) {
            showError($("#sns-error"), result.error || "Could not link the account.");
            return;
        }
        show($("#sns-saved"));
        state.snsLinked = true;
        hideWarning($("#date-warning"));
        var status = $("#sns-status");
        status.textContent = "Linked (" + result.sns_username + ")";
        status.className = "sns-status-linked";
        $("#sns-password").value = "";
    });
}

function setupNewBulletin() {
    $("#new-bulletin-link").addEventListener("click", function(e) {
        e.preventDefault();
        if (state.dateStr || Object.values(state.hymns).some(function(h) { return h; })) {
            if (!confirm("Start over? All current entries will be cleared.")) return;
        }
        resetAll();
    });
}

function setupHelp() {
    function openHelp(e) {
        e.preventDefault();
        window.open("/help.html", "_blank");
    }
    const helpLink = $("#help-link");
    if (helpLink) helpLink.addEventListener("click", openHelp);
    const loginHelpLink = $("#login-help-link");
    if (loginHelpLink) loginHelpLink.addEventListener("click", openHelp);
}

function setupLogout() {
    $("#logout-link").addEventListener("click", async function(e) {
        e.preventDefault();
        if (!confirm("Log out? Any unsaved work will be lost.")) return;
        await api.logout();
        // Show the auth overlay again
        show($("#login-overlay"));
        hide($("#app"));
        showSettingsPanel(false);
        showAuthForm("#login-form");
        $("#login-email").value = "";
        $("#login-password").value = "";
        $("#login-btn").disabled = false;

        // Reset state
        resetAll();
    });
}

/** Resets hymn slot UI and service detail fields (shared by resetAll and date re-fetch). */
function resetFormUI() {
    $$(".hymn-number").forEach(function(el) { el.value = ""; });
    $$(".hymn-info").forEach(function(el) { hide(el); el.textContent = ""; });
    $$(".hymn-error").forEach(function(el) { hide(el); });
    $$(".hymn-clear-btn").forEach(function(el) { hide(el); });
    $$(".verse-select").forEach(function(el) { el.innerHTML = ""; hide(el); });
    $("#prelude-title").value = "";
    $("#prelude-composer").value = "";
    setOffertoryType("offertory");
    $("#offertory-title").value = "";
    $("#offertory-composer").value = "";
    $("#offertory-performer").value = "";
    $("#postlude-title").value = "";
    $("#postlude-composer").value = "";
    $("#choral-title").value = "";
    $("#choral-composer").value = "";
    $("#cover-image-path").textContent = "None selected";
    hide($("#cover-image-clear"));
    hide($("#cover-image-preview"));
}

/** Resets all wizard state and UI to initial values. */
function resetAll() {
    state.unsavedWork = false;
    Object.assign(state, initialState());

    // Reset UI
    hide($("#day-info"));
    hide($("#filename-preview"));
    hideError($("#date-error"));
    hideWarning($("#date-warning"));
    hideWarning($("#content-warning"));
    $("#date-input").value = "";
    $("#preface-select").innerHTML = "";

    // Reset liturgical texts
    $("#texts-panels").innerHTML = "";
    hide($("#custom-edit-warning"));
    hideError($("#texts-error"));

    resetFormUI();

    // Reset generate section
    $$('input[name="doc_select"]').forEach(function(el) { el.checked = true; });
    hide($("#progress-area"));
    hide($("#results-area"));
    hideError($("#generate-error"));

    // Reset baptism
    $("#include-baptism").checked = false;
    hide($("#baptism-details"));
    $("#baptism-names").value = "";

    // Reset review outline + season theme
    $("#review-outline").innerHTML = "";
    clearSeasonTheme();

    // Go back to step 1
    showStep(1);
}

// ── Date & Season Fetch ──────────────────────────────────────────────

async function handleDateFetchResult(result) {
    state.season = result.season;
    state.defaults = result.defaults;
    state.unsavedWork = true;

    // Surface S&S content sanity-check warnings (empty sections)
    var contentWarning = $("#content-warning");
    if (contentWarning) {
        if (result.warnings && result.warnings.length) {
            showWarning(contentWarning,
                "Content check: " + result.warnings.join(" "));
        } else {
            hideWarning(contentWarning);
        }
    }

    // Reset hymns and service details for the new date
    state.hymns = { gathering: null, sermon: null, communion: null, sending: null };
    state.coverImage = "";
    resetFormUI();

    // Display day info + apply season theme
    $("#day-name").textContent = result.day_name;
    applySeasonTheme(result.season);
    var seasonBar = $("#season-bar");
    if (seasonBar) $("#season-bar-day").textContent = "\u2014 " + result.day_name;

    const readingsEl = $("#readings-list");
    readingsEl.innerHTML = "";
    state.readingOverrides = {};
    (result.readings || []).forEach(function(r) {
        var slot = readingSlotKey(r.label);
        var div = document.createElement("div");
        div.className = "reading-item";
        div.dataset.slot = slot;

        // Header row: label + citation + action links
        var header = document.createElement("div");
        header.className = "reading-header";

        var labelSpan = document.createElement("span");
        labelSpan.className = "reading-label";
        labelSpan.textContent = r.label + ":";
        header.appendChild(labelSpan);

        var citationSpan = document.createElement("span");
        citationSpan.className = "reading-citation-text";
        citationSpan.textContent = " " + r.citation;
        header.appendChild(citationSpan);

        var editBtn = document.createElement("button");
        editBtn.type = "button";
        editBtn.className = "btn-link reading-edit-btn";
        editBtn.textContent = "Edit";
        editBtn.addEventListener("click", function() {
            var editArea = div.querySelector(".reading-edit-area");
            if (editArea) {
                editArea.hidden = !editArea.hidden;
                editBtn.textContent = editArea.hidden ? "Edit" : "Cancel";
                return;
            }
            editBtn.textContent = "Cancel";
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
                showBtnSpinner(fetchBtn);
                var result = await api.fetch_custom_reading(citation);
                hideBtnSpinner(fetchBtn, "Fetch");
                var msg = area.querySelector(".reading-edit-msg");
                if (!msg) {
                    msg = document.createElement("div");
                    msg.className = "reading-edit-msg";
                    area.appendChild(msg);
                }
                if (result.success) {
                    msg.innerHTML = '<span class="reading-edit-ok">Fetched. Will use custom citation.</span>';
                    state.readingOverrides[slot] = {
                        label: r.label,
                        citation: citation,
                        intro: "",
                        text_html: result.text_html,
                    };
                    citationSpan.textContent = " " + citation + " (custom)";
                    // Invalidate any cached preview
                    var oldPreview = div.querySelector(".reading-content-preview");
                    if (oldPreview) oldPreview.remove();
                    previewBtn.textContent = "Preview";
                } else {
                    msg.innerHTML = '<span class="error-msg">' + escapeHtml(result.error || "Failed to fetch") + '</span>';
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
                var msg = area.querySelector(".reading-edit-msg");
                if (msg) msg.innerHTML = "";
                // Invalidate any cached preview
                var oldPreview = div.querySelector(".reading-content-preview");
                if (oldPreview) oldPreview.remove();
                previewBtn.textContent = "Preview";
            });
            area.appendChild(resetBtn);

            div.appendChild(area);
        });
        header.appendChild(editBtn);

        // Preview button
        var previewBtn = document.createElement("button");
        previewBtn.type = "button";
        previewBtn.className = "btn-link reading-preview-btn";
        previewBtn.textContent = "Preview";
        previewBtn.addEventListener("click", async function() {
            var existing = div.querySelector(".reading-content-preview");
            if (existing) {
                existing.hidden = !existing.hidden;
                previewBtn.textContent = existing.hidden ? "Preview" : "Hide";
                return;
            }
            showBtnSpinner(previewBtn);
            var res = await api.get_reading_preview(slot);
            hideBtnSpinner(previewBtn, "Preview");
            if (!res.success) {
                showError($("#date-error"),
                    "Could not load the preview: " + (res.error || "unknown error"));
                return;
            }
            hideError($("#date-error"));
            var preview = document.createElement("div");
            preview.className = "reading-content-preview";
            if (res.intro) {
                var intro = document.createElement("p");
                intro.className = "reading-intro";
                intro.textContent = res.intro;
                preview.appendChild(intro);
            }
            var content = document.createElement("div");
            content.className = "reading-content";
            content.innerHTML = sanitizeHtml(res.preview_html);
            preview.appendChild(content);
            div.appendChild(preview);
            previewBtn.textContent = "Hide";
        });
        header.appendChild(previewBtn);

        div.appendChild(header);

        readingsEl.appendChild(div);
    });

    show($("#day-info"));

    // Show filename preview
    try {
        var prefixResult = await api.get_file_prefix();
        if (prefixResult.success) {
            $("#filename-prefix").textContent = "[Document] - " + prefixResult.prefix + ".pdf";
            show($("#filename-preview"));
        } else {
            hide($("#filename-preview"));
        }
    } catch (_) {
        hide($("#filename-preview"));
    }

    // Fetch liturgical texts for the review step
    await loadLiturgicalTexts();

    // Pre-fill liturgical settings
    applyDefaults(result.defaults);

    // Reset generate area
    hide($("#progress-area"));
    hide($("#results-area"));
    hideError($("#generate-error"));
}

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

        // Warn if changing date will lose existing work
        var hasWork = Object.values(state.hymns).some(function(h) { return h; }) ||
            Object.keys(state.textChoices).some(function(k) { return state.textChoices[k] && state.textChoices[k].isCustom; });
        if (hasWork && !confirm("Changing the date will clear all hymns and text edits. Continue?")) {
            return;
        }

        hideError($("#date-error"));
        hideWarning($("#date-warning"));
        hideWarning($("#content-warning"));
        hide($("#day-info"));

        // Warn if date is not a Sunday (non-blocking)
        if (dateVal.getDay() !== 0) {
            showWarning($("#date-warning"), "Note: this date is not a Sunday.");
        }

        const spinner = $("#date-spinner");
        show(spinner);
        this.disabled = true;

        const dateDisplay = formatDate(dateStr);

        const result = await api.fetch_day_content(dateStr, dateDisplay);

        hide(spinner);
        this.disabled = false;

        if (!result.success) {
            if (result.auth_error) return;
            showError($("#date-error"), result.error || "Failed to fetch content.");
            return;
        }

        state.dateStr = dateStr;
        state.dateDisplay = dateDisplay;
        await handleDateFetchResult(result);
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
    setMemorialAcclamationMode(defaults.memorial_acclamation_mode || null);
    updateMemorialAcclamationModeControls();
    $("#hint-memorial").textContent = defaults.include_memorial_acclamation
        ? "Default: Yes; choose sung or spoken"
        : "Default: No";
    var settingsError = $("#settings-error");
    if (settingsError) hideError(settingsError);

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
    hide($("#baptism-details"));
    $("#baptism-names").value = "";
}

/** Populate preface dropdown from API, pre-selecting the seasonal default. */
async function populatePrefaceDropdown(defaultKey) {
    var select = $("#preface-select");
    select.innerHTML = "";

    try {
        var result = await api.get_preface_options();
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

/** Build verse checkbox HTML for a hymn with the given verse count. */
function buildVerseCheckboxes(slotName, verseCount) {
    var html = '<span class="verse-label">Verses:</span>';
    for (var i = 1; i <= verseCount; i++) {
        var id = "verse-" + slotName + "-" + i;
        html += '<label class="verse-cb-label" for="' + id + '">' +
            '<input type="checkbox" id="' + id + '" value="' + i + '" checked> ' + i +
            '</label>';
    }
    return html;
}

/** Read which verse checkboxes are checked in a slot's .verse-select container. */
function getSelectedVerses(slot) {
    var checks = slot.querySelectorAll(".verse-select input[type=checkbox]:checked");
    var selected = [];
    checks.forEach(function(cb) { selected.push(parseInt(cb.value, 10)); });
    return selected;
}

/** Show verse checkboxes for a hymn slot after successful lyrics fetch. */
function showVerseSelect(slot, slotName, verseCount) {
    var container = slot.querySelector(".verse-select");
    container.innerHTML = buildVerseCheckboxes(slotName, verseCount);
    show(container);
    // Wire checkbox changes to update state
    container.querySelectorAll("input[type=checkbox]").forEach(function(cb) {
        cb.addEventListener("change", function() {
            var hymn = state.hymns[slotName];
            if (hymn) {
                hymn.selectedVerses = getSelectedVerses(slot);
            }
        });
    });
}

function clearHymnSlot(slot) {
    var slotName = slot.dataset.slot;
    state.hymns[slotName] = null;
    slot.querySelector(".hymn-number").value = "";
    var infoEl = slot.querySelector(".hymn-info");
    infoEl.textContent = "";
    hide(infoEl);
    hideError(slot.querySelector(".hymn-error"));
    var verseEl = slot.querySelector(".verse-select");
    verseEl.innerHTML = "";
    hide(verseEl);
    var clearBtn = slot.querySelector(".hymn-clear-btn");
    if (clearBtn) hide(clearBtn);
}

function setupFetchAllHymns() {
    $("#fetch-all-hymns-btn").addEventListener("click", async function() {
        var slots = $$(".hymn-slot");
        var toFetch = [];
        slots.forEach(function(slot) {
            var number = slot.querySelector(".hymn-number").value.trim();
            if (number) toFetch.push(slot);
        });
        if (toFetch.length === 0) return;

        showBtnSpinner(this);
        for (var i = 0; i < toFetch.length; i++) {
            await fetchHymnSlot(toFetch[i]);
        }
        hideBtnSpinner(this, "Fetch All Hymns");
    });
}

/** Fetch one hymn slot's title + lyrics. Callable directly (Fetch All,
    past-run restore) or from the per-slot button — no click simulation. */
async function fetchHymnSlot(slot) {
    const slotName = slot.dataset.slot;
    const numberInput = slot.querySelector(".hymn-number");
    const collection = slot.querySelector(".hymn-collection").value;
    const errorEl = slot.querySelector(".hymn-error");
    const infoEl = slot.querySelector(".hymn-info");
    const fetchBtn = slot.querySelector(".hymn-fetch-btn");
    const clearBtn = slot.querySelector(".hymn-clear-btn");
    const number = numberInput.value.trim();

    if (!number) {
        showError(errorEl, "Enter a hymn number from the hymnal's index.");
        hide(infoEl);
        return;
    }

    hideError(errorEl);
    infoEl.textContent = "";
    hide(infoEl);
    if (clearBtn) hide(clearBtn);
    state.hymns[slotName] = null;
    showBtnSpinner(fetchBtn);

    try {
        // One call: the server merges search + lyrics fetch
        const result = await api.search_hymn(number, collection);
        hideBtnSpinner(fetchBtn, "Fetch");

        if (!result.success) {
            showError(errorEl, result.error ||
                "Hymn not found. Check the number and make sure the right hymnal is selected.");
            return;
        }

        if (result.lyrics_unavailable) {
            infoEl.textContent = result.title + " (title only \u2014 no lyrics available)";
            show(infoEl);
            if (clearBtn) show(clearBtn);
            state.hymns[slotName] = {
                number: number,
                collection: collection,
                title: result.title,
                hasLyrics: false,
            };
            return;
        }

        infoEl.textContent = result.title +
            " \u2014 " + result.verse_count + " verse(s)" +
            (result.has_refrain ? " + refrain" : "");
        show(infoEl);
        if (clearBtn) show(clearBtn);
        var allVerses = [];
        for (var vi = 1; vi <= result.verse_count; vi++) allVerses.push(vi);
        state.hymns[slotName] = {
            number: number,
            collection: collection,
            title: result.title,
            hasLyrics: result.verse_count > 0,
            verseCount: result.verse_count,
            selectedVerses: allVerses,
        };
        if (result.verse_count > 1) {
            showVerseSelect(slot, slotName, result.verse_count);
        }
    } catch (err) {
        hideBtnSpinner(fetchBtn, "Fetch");
        showError(errorEl, "Failed to fetch hymn: " + (err.message || "unknown error"));
    }
}

function setupHymnFetch() {
    // Clear buttons
    $$(".hymn-clear-btn").forEach(function(btn) {
        btn.addEventListener("click", function() {
            clearHymnSlot(this.closest(".hymn-slot"));
        });
    });

    $$(".hymn-fetch-btn").forEach(function(btn) {
        btn.addEventListener("click", function() {
            fetchHymnSlot(this.closest(".hymn-slot"));
        });
    });
}

// ── Past Runs ────────────────────────────────────────────────────────

async function loadPastRuns() {
    var container = $("#past-runs-list");
    if (!container) return;
    container.innerHTML = "";

    try {
        var result = await api.get_past_runs();
        if (!result.success || !result.runs.length) {
            hide($("#past-runs-section"));
            return;
        }

        show($("#past-runs-section"));

        result.runs.forEach(function(run) {
            var item = document.createElement("div");
            item.className = "past-run-item";

            var info = document.createElement("button");
            info.type = "button";
            info.className = "past-run-load-btn";
            var meta = run.metadata || {};
            var label = meta.date_display || run.date || "Unknown";
            if (meta.day_name) label += " \u2014 " + meta.day_name;
            info.textContent = label;
            info.addEventListener("click", function() {
                restorePastRun(run.id);
            });
            item.appendChild(info);

            if (meta.hymn_summary) {
                var hymns = document.createElement("span");
                hymns.className = "past-run-hymns";
                hymns.textContent = meta.hymn_summary;
                item.appendChild(hymns);
            }

            var deleteBtn = document.createElement("button");
            deleteBtn.type = "button";
            deleteBtn.className = "btn-link past-run-delete";
            deleteBtn.textContent = "Delete";
            deleteBtn.addEventListener("click", function(e) {
                e.stopPropagation();
                deletePastRun(run.id, label);
            });
            item.appendChild(deleteBtn);

            container.appendChild(item);
        });
    } catch (_) {
        hide($("#past-runs-section"));
    }
}

async function deletePastRun(runId, label) {
    if (!confirm('Delete the saved run "' + (label || runId) + '"? This cannot be undone.')) {
        return;
    }
    var result = await api.delete_past_run(runId);
    if (!result.success) {
        showError($("#date-error"),
            "Could not delete that run: " + (result.error || "unknown error"));
        return;
    }
    loadPastRuns();
}

async function savePastRun(formData) {
    var saveData = Object.assign({}, formData);
    delete saveData.selected_docs;
    delete saveData.cover_image;

    var hymnSummary = ["gathering", "sermon", "communion", "sending"]
        .map(function(slot) {
            var h = state.hymns[slot];
            return h && h.number ? h.collection + " " + h.number : "";
        })
        .filter(Boolean)
        .join(", ");

    var metadata = {
        date_display: state.dateDisplay,
        season: state.season,
        day_name: $("#day-name") ? $("#day-name").textContent : "",
        hymn_summary: hymnSummary,
    };

    var result = await api.save_past_run(saveData, metadata);
    if (!result.success) {
        showWarning($("#date-warning"),
            "The documents generated, but this run could not be saved to Past Runs.");
        return;
    }
    loadPastRuns();
}

async function restorePastRun(runId) {
    var result = await api.get_past_run(runId);
    if (!result.success) {
        showError($("#date-error"),
            "Could not load that past run: " + (result.error || "unknown error"));
        return;
    }

    var fd = result.form_data;

    // Set the date and trigger content fetch
    $("#date-input").value = fd.date;

    hideError($("#date-error"));
    hideWarning($("#date-warning"));
    hideWarning($("#content-warning"));
    hide($("#day-info"));
    var spinner = $("#date-spinner");
    show(spinner);
    $("#fetch-btn").disabled = true;

    var fetchResult = await api.fetch_day_content(fd.date, state.dateDisplay);

    hide(spinner);
    $("#fetch-btn").disabled = false;

    if (!fetchResult.success) {
        showError($("#date-error"), fetchResult.error || "Failed to fetch content for this date.");
        return;
    }

    state.dateStr = fd.date;
    state.dateDisplay = formatDate(fd.date);
    await handleDateFetchResult(fetchResult);

    // Overlay saved settings
    applyRestoredSettings(fd);

    // Restore hymns
    await restoreHymns(fd);

    // Restore liturgical text choices after texts have loaded
    restoreLiturgicalTextChoices(fd);

    showStep(1);
}

function applyRestoredSettings(fd) {
    // Liturgical settings
    var creedRadio = document.querySelector('input[name="creed_type"][value="' + fd.creed_type + '"]');
    if (creedRadio) creedRadio.checked = true;

    $("#include-kyrie").checked = !!fd.include_kyrie;

    var canticleRadio = document.querySelector('input[name="canticle"][value="' + fd.canticle + '"]');
    if (canticleRadio) canticleRadio.checked = true;

    var epRadio = document.querySelector('input[name="eucharistic_form"][value="' + fd.eucharistic_form + '"]');
    if (epRadio) epRadio.checked = true;

    $("#include-memorial").checked = !!fd.include_memorial_acclamation;
    setMemorialAcclamationMode(fd.memorial_acclamation_mode || null);
    updateMemorialAcclamationModeControls();

    if (fd.preface) {
        var prefSelect = $("#preface-select");
        if (prefSelect) prefSelect.value = fd.preface;
    }

    if (fd.show_confession !== undefined) $("#show-confession").checked = fd.show_confession;
    if (fd.show_nunc_dimittis !== undefined) $("#show-nunc-dimittis").checked = fd.show_nunc_dimittis;

    // Baptism
    $("#include-baptism").checked = !!fd.include_baptism;
    var baptismDetails = $("#baptism-details");
    if (fd.include_baptism) {
        show(baptismDetails);
        $("#baptism-names").value = fd.baptism_candidate_names || "";
    } else {
        hide(baptismDetails);
    }

    // Service music
    $("#prelude-title").value = fd.prelude_title || "";
    $("#prelude-composer").value = fd.prelude_composer || "";
    setOffertoryType(fd.offertory_type || "offertory");
    $("#offertory-title").value = fd.offertory_title || "";
    $("#offertory-composer").value = fd.offertory_composer || "";
    $("#offertory-performer").value = fd.offertory_performer || "";
    $("#postlude-title").value = fd.postlude_title || "";
    $("#postlude-composer").value = fd.postlude_composer || "";
    $("#choral-title").value = fd.choral_title || "";
    $("#choral-composer").value = fd.choral_composer || "";
}

async function restoreHymns(fd) {
    var slots = ["gathering", "sermon", "communion", "sending"];
    for (var i = 0; i < slots.length; i++) {
        var slot = slots[i];
        var hymnData = fd[slot + "_hymn"];
        if (!hymnData || !hymnData.number) continue;

        var slotEl = document.querySelector('.hymn-slot[data-slot="' + slot + '"]');
        if (!slotEl) continue;

        slotEl.querySelector(".hymn-number").value = hymnData.number;
        var collectionSelect = slotEl.querySelector(".hymn-collection");
        if (collectionSelect && hymnData.collection) {
            collectionSelect.value = hymnData.collection;
        }

        await fetchHymnSlot(slotEl);

        // Restore verse selection if applicable
        if (hymnData.selected_verses && state.hymns[slot] && state.hymns[slot].verseCount) {
            var verseChecks = slotEl.querySelectorAll(".verse-select input[type=checkbox]");
            verseChecks.forEach(function(cb) {
                var v = parseInt(cb.value, 10);
                cb.checked = hymnData.selected_verses.indexOf(v) !== -1;
            });
            state.hymns[slot].selectedVerses = hymnData.selected_verses.slice();
        }
    }
}

function restoreLiturgicalTextChoices(fd) {
    // Structured texts: confession, dismissal
    ["confession", "dismissal"].forEach(function(key) {
        var entries = fd[key + "_entries"];
        if (!entries || !entries.length) return;
        var editorEl = document.querySelector('.structured-editor[data-key="' + key + '"]');
        if (!editorEl) return;
        var rowsContainer = editorEl.querySelector(".entry-rows");
        if (!rowsContainer) return;
        rowsContainer.innerHTML = "";
        entries.forEach(function(entry) {
            rowsContainer.appendChild(buildEntryRow(entry));
        });
    });

    // Plain texts: offering_prayer, prayer_after_communion, blessing
    ["offering_prayer", "prayer_after_communion", "blessing"].forEach(function(key) {
        var savedText = fd[key + "_text"];
        if (savedText === undefined) return;
        var textarea = document.querySelector('.text-textarea[data-key="' + key + '"]');
        if (textarea) {
            textarea.value = savedText;
            if (state.textChoices && state.textChoices[key]) {
                state.textChoices[key].value = savedText;
            }
        }
    });
}

function setupPastRuns() {
    var toggle = $("#past-runs-toggle");
    if (!toggle) return;
    toggle.addEventListener("click", function() {
        var list = $("#past-runs-list");
        var isOpen = !list.hidden;
        if (isOpen) {
            hide(list);
            toggle.innerHTML = "Past Runs &#9654;";
        } else {
            show(list);
            toggle.innerHTML = "Past Runs &#9660;";
        }
    });
}

// ── File Pickers ─────────────────────────────────────────────────────

function setupFilePickers() {
    var fileInput = $("#cover-file-input");

    $("#cover-image-btn").addEventListener("click", function() {
        fileInput.click();
    });

    fileInput.addEventListener("change", async function() {
        var file = this.files && this.files[0];
        this.value = "";
        if (!file) return;
        var btn = $("#cover-image-btn");
        btn.disabled = true;
        try {
            var result = await api.upload_cover(file);
            if (!result.success) {
                showError($("#cover-error"),
                    result.error || "Could not upload the cover image.");
                return;
            }
            hideError($("#cover-error"));
            state.coverImage = result.cover_token;
            $("#cover-image-path").textContent = file.name;
            show($("#cover-image-clear"));
            var img = $("#cover-image-preview");
            img.src = URL.createObjectURL(file);
            show(img);
        } finally {
            btn.disabled = false;
        }
    });

    $("#cover-image-clear").addEventListener("click", function() {
        state.coverImage = "";
        $("#cover-image-path").textContent = "None selected";
        hide(this);
        var img = $("#cover-image-preview");
        hide(img);
        img.removeAttribute("src");
    });
}

// ── Liturgical Texts Review ──────────────────────────────────────────

/** Role options for structured (call-and-response) text entries. */
var ROLE_OPTIONS = [
    { value: "P", label: "P (Pastor)" },
    { value: "C", label: "C (Congregation)" },
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

    var textInput = document.createElement("textarea");
    textInput.className = "entry-text";
    textInput.textContent = entry.text || "";
    textInput.rows = 2;
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

/** Find the data for a given option key within an options list. */
function findOptionData(options, key) {
    for (var i = 0; i < options.length; i++) {
        if (options[i].key === key) return options[i].data;
    }
    return null;
}

function confirmSourceChange(key, radioEls) {
    var choice = state.textChoices[key];
    if (choice.isCustom && !confirm("This will replace your custom edits. Continue?")) {
        var prev = radioEls.find(function(r) { return r.value === choice.source; });
        if (prev) prev.checked = true;
        return false;
    }
    return true;
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
        var result = await api.get_liturgical_texts();
        hide(spinner);

        if (!result.success) {
            showError(errorEl, result.error || "Failed to load liturgical texts.");
            return;
        }

        state.liturgicalTexts = result.texts;
        state.textChoices = {};

        // Initialize read-only text choices (no editable panel, preview only)
        ["prayer_of_day"].forEach(function(key) {
            var info = result.texts[key];
            if (!info) return;
            var options = info.options || [];
            var opt = options.find(function(o) { return !o.disabled; }) || options[0];
            state.textChoices[key] = {
                source: opt ? opt.key : "",
                isCustom: false,
                value: opt ? (opt.data || "") : "",
                options: options,
                type: info.type,
            };
        });

        var textOrder = ["confession", "offering_prayer", "prayer_after_communion", "blessing", "dismissal"];
        textOrder.forEach(function(key) {
            var info = result.texts[key];
            if (!info) return;

            var isStructured = info.type === "structured";
            var options = info.options || [];

            // Resolve the default — fall back to first enabled option
            var defaultKey = info.default || (options[0] && options[0].key) || "";
            var defaultOpt = options.find(function(o) { return o.key === defaultKey && !o.disabled; });
            if (!defaultOpt) {
                defaultOpt = options.find(function(o) { return !o.disabled; }) || options[0];
            }
            var activeKey = defaultOpt ? defaultOpt.key : "";
            var initialData = defaultOpt ? defaultOpt.data : (isStructured ? [] : "");

            state.textChoices[key] = {
                source: activeKey,
                isCustom: false,
                value: isStructured ? null : (initialData || ""),
                options: options,
                type: info.type,
            };

            // Build panel
            var panel = document.createElement("div");
            panel.className = "text-panel";
            panel.dataset.key = key;

            var header = document.createElement("button");
            header.className = "text-panel-header";
            header.setAttribute("type", "button");
            header.setAttribute("aria-expanded", "false");
            header.innerHTML = '<span class="text-panel-title">' + escapeHtml(info.label) + '</span>' +
                '<span class="text-panel-toggle">&#9660;</span>';
            header.addEventListener("click", function() {
                var open = panel.classList.toggle("open");
                header.setAttribute("aria-expanded", open ? "true" : "false");
            });
            panel.appendChild(header);

            var body = document.createElement("div");
            body.className = "text-panel-body";

            // Build radio buttons from options (only if >1 option)
            var radioEls = [];
            if (options.length > 1) {
                var radios = document.createElement("div");
                radios.className = "text-source-radios";

                options.forEach(function(opt) {
                    var label = document.createElement("label");
                    var radio = document.createElement("input");
                    radio.type = "radio";
                    radio.name = "text_source_" + key;
                    radio.value = opt.key;
                    if (opt.key === activeKey) radio.checked = true;
                    if (opt.disabled) radio.disabled = true;
                    label.appendChild(radio);
                    label.appendChild(document.createTextNode(" " + opt.label));
                    radios.appendChild(label);
                    radioEls.push(radio);
                });

                body.appendChild(radios);
            }

            if (isStructured) {
                // Structured editor for call-and-response texts
                var editor = buildStructuredEditor(key, initialData);
                body.appendChild(editor);

                // Wire radio changes — rebuild editor with selected option's data
                radioEls.forEach(function(radio) {
                    radio.addEventListener("change", function() {
                        if (!confirmSourceChange(key, radioEls)) return;
                        var choice = state.textChoices[key];
                        choice.source = this.value;
                        choice.isCustom = false;
                        var newData = findOptionData(choice.options, this.value) || [];
                        var rowsContainer = editor.querySelector(".entry-rows");
                        rowsContainer.innerHTML = "";
                        newData.forEach(function(entry) {
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
                radioEls.forEach(function(radio) {
                    radio.addEventListener("change", function() {
                        if (!confirmSourceChange(key, radioEls)) return;
                        var choice = state.textChoices[key];
                        choice.source = this.value;
                        choice.isCustom = false;
                        var newText = findOptionData(choice.options, this.value) || "";
                        choice.value = newText;
                        textarea.value = newText;
                        hide($("#custom-edit-warning"));
                    });
                });

                // Wire textarea edits — detect custom modifications
                textarea.addEventListener("input", function() {
                    var choice = state.textChoices[key];
                    choice.value = this.value;
                    var matchesAny = choice.options.some(function(opt) {
                        return (opt.data || "") === choice.value;
                    });
                    choice.isCustom = !matchesAny;
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

// ── Generation ───────────────────────────────────────────────────────

/** Collects all form data into a dict for the Python API. */
function collectFormData() {
    // Liturgical settings
    const creedEl = document.querySelector('input[name="creed_type"]:checked');
    const canticleEl = document.querySelector('input[name="canticle"]:checked');
    const epEl = document.querySelector('input[name="eucharistic_form"]:checked');
    const includeMemorial = $("#include-memorial").checked;

    const formData = {
        date: state.dateStr,
        date_display: state.dateDisplay,
        creed_type: creedEl ? creedEl.value : null,
        include_kyrie: $("#include-kyrie").checked,
        canticle: canticleEl ? canticleEl.value : null,
        eucharistic_form: epEl ? epEl.value : null,
        include_memorial_acclamation: includeMemorial,
        memorial_acclamation_mode: includeMemorial ? getMemorialAcclamationMode() : null,
        preface: $("#preface-select").value || null,
        show_confession: $("#show-confession").checked,
        show_nunc_dimittis: $("#show-nunc-dimittis").checked,
        include_baptism: $("#include-baptism").checked,
        baptism_candidate_names: $("#baptism-names").value.trim(),
        prelude_title: $("#prelude-title").value.trim(),
        prelude_composer: $("#prelude-composer").value.trim(),
        offertory_type: getOffertoryType(),
        offertory_title: $("#offertory-title").value.trim(),
        offertory_composer: $("#offertory-composer").value.trim(),
        offertory_performer: $("#offertory-performer").value.trim(),
        postlude_title: $("#postlude-title").value.trim(),
        postlude_composer: $("#postlude-composer").value.trim(),
        choral_title: $("#choral-title").value.trim(),
        choral_composer: $("#choral-composer").value.trim(),
        cover_image: state.coverImage,
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
            var hymnEntry = {
                number: data.number,
                collection: data.collection,
                title: data.title,
            };
            // Include selected_verses only when a subset is chosen
            if (data.selectedVerses && data.verseCount &&
                data.selectedVerses.length < data.verseCount) {
                hymnEntry.selected_verses = data.selectedVerses;
            }
            formData[slot + "_hymn"] = hymnEntry;
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

/** Runs the document generation flow. Extracted for reuse by single-doc regen. */
var generationInProgress = false;

async function runGeneration(docOverride) {
    const generateBtn = $("#generate-btn");
    const errorEl = $("#generate-error");
    if (generationInProgress) return;
    hideError(errorEl);
    hide($("#results-area"));

    // Validate required state
    if (!state.dateStr || !state.dateDisplay) {
        showError(errorEl, "Please fetch content for a date first.");
        return;
    }

    // The date box must match what was actually fetched
    var dateInput = $("#date-input");
    if (dateInput && dateInput.value && dateInput.value !== state.dateStr) {
        showError(errorEl,
            "The date box shows " + dateInput.value + " but the fetched content is for " +
            state.dateStr + ". Click Fetch Content on Step 1 before generating.");
        return;
    }

    var selectedDocs = docOverride ||
        Array.from($$('input[name="doc_select"]:checked')).map(function(el) { return el.value; });
    if (selectedDocs.length === 0) {
        showError(errorEl, "Select at least one document to generate.");
        return;
    }
    if (!validateMemorialAcclamationMode(errorEl)) {
        return;
    }

    const formData = collectFormData();
    formData.selected_docs = selectedDocs;

    // Warn if any hymns lack lyrics (Large Print will show title only)
    var missingLyrics = [];
    ["gathering", "sermon", "communion", "sending"].forEach(function(slot) {
        var hymn = state.hymns[slot];
        if (!hymn || !hymn.number) return;
        // The hymn was fetched but lyrics may not have loaded
        if (hymn.title && !hymn.hasLyrics) {
            var label = slot.charAt(0).toUpperCase() + slot.slice(1);
            missingLyrics.push(label + " (" + hymn.collection + " " + hymn.number + ")");
        }
    });
    if (missingLyrics.length > 0) {
        var proceed = confirm(
            "The following hymns have no lyrics text — Large Print will show title only:\n\n" +
            missingLyrics.join("\n") +
            "\n\nContinue anyway?"
        );
        if (!proceed) return;
    }

    generationInProgress = true;
    generateBtn.disabled = true;
    $$(".regen-single-btn").forEach(function(el) { el.disabled = true; });
    show($("#progress-area"));
    $("#progress-fill").style.width = "0%";
    $("#progress-status").textContent = "Starting generation...";
    const bar = document.querySelector(".progress-bar");
    if (bar) bar.setAttribute("aria-valuenow", 0);

    const result = await api.generate_all(formData);

    generationInProgress = false;
    generateBtn.disabled = false;

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
            const name = result.results[key];

            var link = document.createElement("a");
            link.href = api.file_url(key);
            link.textContent = (DOC_LABELS[key] || key) + " \u2014 " + name;
            link.setAttribute("download", name);
            li.appendChild(link);

            // Single-doc regenerate link
            var regenLink = document.createElement("button");
            regenLink.type = "button";
            regenLink.className = "btn-link regen-single-btn";
            regenLink.textContent = "Regenerate";
            regenLink.addEventListener("click", function() {
                regenerateSingleDoc(key);
            });
            li.appendChild(regenLink);

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

    // Show/hide success banner
    var banner = $("#success-banner");
    if (Object.keys(result.errors || {}).length === 0 && Object.keys(result.results || {}).length > 0) {
        show(banner);
    } else {
        hide(banner);
    }



    state.unsavedWork = false;
    show($("#results-area"));
    $("#results-area").scrollIntoView({ behavior: "smooth", block: "start" });

    // Save this run for Past Runs recall
    if (Object.keys(result.results || {}).length > 0) {
        savePastRun(formData);
    }
}

/** Regenerate a single document by key, then restore all checkboxes. */
async function regenerateSingleDoc(docKey) {
    await runGeneration([docKey]);
}

function setupGenerate() {
    $("#generate-btn").addEventListener("click", function() {
        runGeneration();
    });

    // Generate Again button
    $("#generate-again-btn").addEventListener("click", function() {
        hide($("#results-area"));
        hide($("#success-banner"));
        $$('input[name="doc_select"]').forEach(function(el) { el.checked = true; });
    });

    // Download-all button
    $("#download-zip-btn").addEventListener("click", function() {
        window.location.href = api.zip_url();
    });
}

// ── Init ─────────────────────────────────────────────────────────────

function setupBaptismToggle() {
    $("#include-baptism").addEventListener("change", function() {
        if (this.checked) {
            show($("#baptism-details"));
        } else {
            hide($("#baptism-details"));
            $("#baptism-names").value = "";
        }
    });
}

function setupMemorialAcclamationModeToggle() {
    $("#include-memorial").addEventListener("change", function() {
        updateMemorialAcclamationModeControls();
    });
    $$('input[name="memorial_acclamation_mode"]').forEach(function(el) {
        el.addEventListener("change", function() {
            var settingsError = $("#settings-error");
            if (settingsError) hideError(settingsError);
        });
    });
    updateMemorialAcclamationModeControls();
}

// Back/refresh/close protection: a fetched-but-not-generated bulletin
// represents real volunteer effort — make the browser ask first.
window.addEventListener("beforeunload", function(e) {
    if (state.unsavedWork) {
        e.preventDefault();
        e.returnValue = "";
    }
});

function setupA11y() {
    // Announce errors, warnings, and status changes to assistive tech
    $$(".error-msg").forEach(function(el) { el.setAttribute("role", "alert"); });
    $$(".warning-msg").forEach(function(el) { el.setAttribute("role", "status"); });
    $$(".spinner").forEach(function(el) { el.setAttribute("role", "status"); });
    var progressStatus = $("#progress-status");
    if (progressStatus) progressStatus.setAttribute("role", "status");

    // Associate the per-slot hymn labels with their inputs
    $$(".hymn-slot").forEach(function(slot) {
        var slotName = slot.dataset.slot;
        var numberInput = slot.querySelector(".hymn-number");
        var collectionSelect = slot.querySelector(".hymn-collection");
        numberInput.id = "hymn-number-" + slotName;
        collectionSelect.id = "hymn-collection-" + slotName;
        var labels = slot.querySelectorAll(".field label");
        if (labels[0]) labels[0].setAttribute("for", numberInput.id);
        if (labels[1]) labels[1].setAttribute("for", collectionSelect.id);
    });
}

document.addEventListener("DOMContentLoaded", function() {
    // Pre-fill date with next Sunday
    $("#date-input").value = getNextSunday();
    setupA11y();

    setupAuth();
    setupSettings();
    setupLogout();
    setupNewBulletin();
    setupHelp();
    setupDateFetch();
    setupResetDefaults();
    setupHymnFetch();
    setupFetchAllHymns();
    setupFilePickers();
    setupGenerate();
    setupBaptismToggle();
    setupMemorialAcclamationModeToggle();
    setupPastRuns();
    setupWizardNav();
    setupWizardStepKeys();
    initAuth();
});
