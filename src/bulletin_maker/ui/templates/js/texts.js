/* Bulletin Maker — Liturgical texts, memorial/offertory controls, baptism */

import { $, $$, show, hide, showError, hideError, escapeHtml } from "./dom.js";
import { state } from "./state.js";
import { api } from "./api.js";

export function getMemorialAcclamationMode() {
    var selected = document.querySelector('input[name="memorial_acclamation_mode"]:checked');
    return selected ? selected.value : null;
}

export function setMemorialAcclamationMode(mode) {
    $$('input[name="memorial_acclamation_mode"]').forEach(function(el) {
        el.checked = !!mode && el.value === mode;
    });
}

export function getOffertoryType() {
    var selected = document.querySelector('input[name="offertory_type"]:checked');
    return selected ? selected.value : "offertory";
}

export function setOffertoryType(type) {
    var value = type === "choral_anthem" ? "choral_anthem" : "offertory";
    $$('input[name="offertory_type"]').forEach(function(el) {
        el.checked = el.value === value;
    });
}

export function offertoryTypeLabel(type) {
    return type === "choral_anthem" ? "Choral Anthem" : "Offertory";
}

export function updateMemorialAcclamationModeControls() {
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

export function validateMemorialAcclamationMode(errorEl) {
    if ($("#include-memorial").checked && !getMemorialAcclamationMode()) {
        showError(errorEl, "Choose whether Memorial Acclamation is sung music or spoken text.");
        return false;
    }
    hideError(errorEl);
    return true;
}

// ── Liturgical Texts Review ──────────────────────────────────────────

/** Role options for structured (call-and-response) text entries. */
var ROLE_OPTIONS = [
    { value: "P", label: "P (Pastor)" },
    { value: "C", label: "C (Congregation)" },
    { value: "instruction", label: "Instruction" },
];

/** Builds a single structured-entry row element. */
export function buildEntryRow(entry) {
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
    removeBtn.textContent = "×";
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
export function collectStructuredEntries(editorEl) {
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
export function findOptionData(options, key) {
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

/** Builds one radio + label for a text-source option and appends it. */
function addRadioOption(radios, radioEls, key, opt, activeKey, onChange) {
    var label = document.createElement("label");
    var radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "text_source_" + key;
    radio.value = opt.key;
    if (opt.key === activeKey) radio.checked = true;
    if (opt.disabled) radio.disabled = true;
    radio.addEventListener("change", function() { onChange(this); });
    label.appendChild(radio);
    label.appendChild(document.createTextNode(" " + opt.label));
    radios.appendChild(label);
    radioEls.push(radio);
    radios.hidden = radioEls.length <= 1;
    return radio;
}

/** Builds the inline "Save to library" control shown for a custom edit. */
function buildSaveToLibraryControl(key, radios, radioEls, onChange, getBody) {
    var wrapper = document.createElement("div");
    wrapper.className = "save-to-library";
    wrapper.hidden = true;

    var nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.className = "save-to-library-name";
    nameInput.placeholder = "Name this text (e.g. “Advent version”)";
    wrapper.appendChild(nameInput);

    var saveBtn = document.createElement("button");
    saveBtn.type = "button";
    saveBtn.className = "btn secondary save-to-library-btn";
    saveBtn.textContent = "Save to library";
    wrapper.appendChild(saveBtn);

    var msg = document.createElement("span");
    msg.className = "save-to-library-msg";
    wrapper.appendChild(msg);

    saveBtn.addEventListener("click", async function() {
        var name = nameInput.value.trim();
        msg.className = "save-to-library-msg";
        msg.textContent = "";
        if (!name) {
            msg.classList.add("error");
            msg.textContent = "Name it first.";
            return;
        }
        saveBtn.disabled = true;
        var result = await api.save_church_text(key, name, getBody());
        saveBtn.disabled = false;
        if (!result.success) {
            msg.classList.add("error");
            msg.textContent = result.error || "Could not save.";
            return;
        }
        var saved = result.text;
        var optKey = "custom:" + saved.id;
        var choice = state.textChoices[key];
        choice.options.push({ key: optKey, label: saved.name, data: saved.body });
        var radio = addRadioOption(radios, radioEls, key, { key: optKey, label: saved.name },
            optKey, onChange);
        radio.checked = true;
        choice.source = optKey;
        choice.isCustom = false;
        nameInput.value = "";
        wrapper.hidden = true;
        msg.classList.add("ok");
        msg.textContent = "Saved — available next time you use this church.";
    });

    return wrapper;
}

/** Loads liturgical texts from the API and builds the review panels. */
export async function loadLiturgicalTexts() {
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

            // Radio buttons for named presets — always built (even with one
            // option today) so a saved-to-library text can join the group
            // later without a full panel rebuild; hidden while <= 1 option.
            var radioEls = [];
            var radios = document.createElement("div");
            radios.className = "text-source-radios";
            body.appendChild(radios);

            var saveControl;

            if (isStructured) {
                // Structured editor for call-and-response texts
                var editor = buildStructuredEditor(key, initialData);
                body.appendChild(editor);

                var onSourceChange = function(radio) {
                    if (!confirmSourceChange(key, radioEls)) return;
                    var choice = state.textChoices[key];
                    choice.source = radio.value;
                    choice.isCustom = false;
                    var newData = findOptionData(choice.options, radio.value) || [];
                    var rowsContainer = editor.querySelector(".entry-rows");
                    rowsContainer.innerHTML = "";
                    newData.forEach(function(entry) {
                        rowsContainer.appendChild(buildEntryRow(entry));
                    });
                    if (saveControl) saveControl.hidden = true;
                };

                options.forEach(function(opt) {
                    addRadioOption(radios, radioEls, key, opt, activeKey, onSourceChange);
                });

                if (state.isAdmin) {
                    saveControl = buildSaveToLibraryControl(key, radios, radioEls,
                        onSourceChange, function() {
                            return collectStructuredEntries(editor);
                        });
                    body.appendChild(saveControl);
                }

                // Detect custom modifications to the entry rows — "input"
                // catches text edits; "click" catches add/remove-row buttons
                // (bubbles after the row is already added/removed).
                var recheckStructuredCustom = function() {
                    var choice = state.textChoices[key];
                    var current = collectStructuredEntries(editor);
                    var matchesAny = choice.options.some(function(opt) {
                        var data = opt.data || [];
                        return JSON.stringify(data) === JSON.stringify(current);
                    });
                    choice.isCustom = matchesAny ? false : current.length > 0;
                    if (saveControl) saveControl.hidden = !choice.isCustom;
                };
                editor.addEventListener("input", recheckStructuredCustom);
                editor.addEventListener("click", recheckStructuredCustom);
            } else {
                // Plain textarea for simple texts
                var textarea = document.createElement("textarea");
                textarea.className = "text-textarea";
                textarea.value = initialData || "";
                textarea.dataset.key = key;
                body.appendChild(textarea);

                var onPlainSourceChange = function(radio) {
                    if (!confirmSourceChange(key, radioEls)) return;
                    var choice = state.textChoices[key];
                    choice.source = radio.value;
                    choice.isCustom = false;
                    var newText = findOptionData(choice.options, radio.value) || "";
                    choice.value = newText;
                    textarea.value = newText;
                    if (saveControl) saveControl.hidden = true;
                };

                options.forEach(function(opt) {
                    addRadioOption(radios, radioEls, key, opt, activeKey, onPlainSourceChange);
                });

                if (state.isAdmin) {
                    saveControl = buildSaveToLibraryControl(key, radios, radioEls,
                        onPlainSourceChange, function() {
                            return textarea.value;
                        });
                    body.appendChild(saveControl);
                }

                // Wire textarea edits — detect custom modifications
                textarea.addEventListener("input", function() {
                    var choice = state.textChoices[key];
                    choice.value = this.value;
                    var matchesAny = choice.options.some(function(opt) {
                        return (opt.data || "") === choice.value;
                    });
                    choice.isCustom = !matchesAny;
                    if (saveControl) saveControl.hidden = !choice.isCustom;
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

export function restoreLiturgicalTextChoices(fd) {
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

export function setupMemorialAcclamationModeToggle() {
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
