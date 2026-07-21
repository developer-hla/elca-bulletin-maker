/* Bulletin Maker — Wizard navigation, review outline, reset */

import { $, $$, show, hide, showError, hideError, hideWarning } from "./dom.js";
import { state, STEP_IDS, SEASON_LABELS, SEASON_COLORS, CANTICLE_LABELS, initialState } from "./state.js";
import {
    validateMemorialAcclamationMode,
    getMemorialAcclamationMode,
    getOffertoryType,
    setOffertoryType,
    offertoryTypeLabel,
    findOptionData,
} from "./texts.js";

/** Formats "2026-02-22" as "February 22, 2026". */
export function formatDate(dateStr) {
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
export function applySeasonTheme(season) {
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

/** Returns the next Sunday's date as "YYYY-MM-DD". */
export function getNextSunday() {
    var d = new Date();
    d.setDate(d.getDate() + ((7 - d.getDay()) % 7 || 7));
    var y = d.getFullYear();
    var m = String(d.getMonth() + 1).padStart(2, "0");
    var day = String(d.getDate()).padStart(2, "0");
    return y + "-" + m + "-" + day;
}

// ── Wizard Navigation ────────────────────────────────────────────────

/** Shows the given step (1-based) and updates step indicator. */
export function showStep(n) {
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
export function setupWizardStepKeys() {
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

export function setupWizardNav() {
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
          detail: (state.paperLabel || "Legal booklet") + " · " + (state.settingLabel || "Setting Two") },
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
        icon.textContent = item.ok ? "✓" : "!";
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
        return { label: label, value: hymn.collection + " " + hymn.number + " — " + hymn.title };
    }
    return { label: label, value: "(not set)", empty: true };
}

/** Returns the source label for a liturgical text choice. */
function getTextSourceLabel(key) {
    var tc = state.textChoices[key];
    if (!tc) return "This Week’s (S&S)";
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
    if (season === "advent") return "“Wait for the Lord”";
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
    title.textContent = "SERVICE ORDER — " + dayName;
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
        preludeVal = (pt ? "“" + pt + "”" : "") + (pc ? " — " + pc : "");
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
    items.push({ label: "Prayer of Day", value: "This Week’s (S&S)", textKey: "prayer_of_day" });

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
        items.push({ label: "Creed", value: creedType === "nicene" ? "Nicene Creed" : "Apostles’ Creed" });
    }

    // Prayers
    items.push({ label: "Prayers", value: "This Week’s (S&S)" });

    // Offering Prayer
    items.push({ label: "Offering Prayer", value: getTextSourceLabel("offering_prayer"), textKey: "offering_prayer" });

    // Offertory
    var offertoryType = getOffertoryType();
    var ot = $("#offertory-title").value.trim();
    var oc = $("#offertory-composer").value.trim();
    var op = $("#offertory-performer").value.trim();
    var offVal = "";
    if (ot || oc || op) {
        offVal = (ot ? "“" + ot + "”" : "") + (oc ? " — " + oc : "") + (op ? " / " + op : "");
    }
    items.push({ label: offertoryTypeLabel(offertoryType), value: offVal || "(not set)", empty: !offVal });

    // Choral
    var choralTitle = $("#choral-title").value.trim();
    var choralComposer = $("#choral-composer").value.trim();
    if (choralTitle) {
        items.push({
            label: "Choral Call",
            value: "“" + choralTitle + "”" + (choralComposer ? " — " + choralComposer : ""),
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
        postVal = (pot ? "“" + pot + "”" : "") + (poc ? " — " + poc : "");
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
            peekBtn.textContent = "▶";
            peekBtn.title = "Preview text";
            (function(key) {
                peekBtn.addEventListener("click", function(e) {
                    e.stopPropagation();
                    var existing = wrapper.querySelector(".outline-peek");
                    if (existing) {
                        existing.hidden = !existing.hidden;
                        peekBtn.textContent = existing.hidden ? "▶" : "▼";
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
                    peekBtn.textContent = "▼";
                });
            })(item.textKey);
            row.appendChild(peekBtn);
        }

        wrapper.appendChild(row);
        list.appendChild(wrapper);
    });

    outline.appendChild(list);
}

export function setupNewBulletin() {
    $("#new-bulletin-link").addEventListener("click", function(e) {
        e.preventDefault();
        if (state.dateStr || Object.values(state.hymns).some(function(h) { return h; })) {
            if (!confirm("Start over? All current entries will be cleared.")) return;
        }
        resetAll();
    });
}

export function setupHelp() {
    function openHelp(e) {
        e.preventDefault();
        window.open("/help.html", "_blank");
    }
    const helpLink = $("#help-link");
    if (helpLink) helpLink.addEventListener("click", openHelp);
    const loginHelpLink = $("#login-help-link");
    if (loginHelpLink) loginHelpLink.addEventListener("click", openHelp);
}

/** Resets hymn slot UI and service detail fields (shared by resetAll and date re-fetch). */
export function resetFormUI() {
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
export function resetAll() {
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
    // Same default as core.library.SUNDAY_COMMUNION_RITE_ID — options are
    // loaded once at sign-in, so reset the selection, not the list.
    var riteSelect = $("#rite-select");
    if (riteSelect) {
        riteSelect.value = "elw_sunday_communion";
        // Re-render per-service variable inputs for the reset rite (the change
        // listener lives in readings.js; a programmatic .value set won't fire).
        riteSelect.dispatchEvent(new Event("change"));
    }

    // Reset liturgical texts
    $("#texts-panels").innerHTML = "";
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
