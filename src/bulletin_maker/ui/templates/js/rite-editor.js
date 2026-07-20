/* Bulletin Maker — Structured rite editor (LWS-2)

   Admin-only. Forks a starter rite into an editable church copy and edits it
   structurally: reorder blocks, enable/disable them, edit the text of
   text-bearing blocks, edit each block's visibility condition (season list +
   toggle map), and set the role-label convention. Layout, fonts, margins, and
   spacing are deliberately NOT editable — this is structure and text only.

   Round-trip fidelity: the editor loads the full rite from the server and
   mutates the loaded block dicts in place (only the fields it exposes). Every
   other field rides along untouched, so save -> reload yields an equal rite. */

import { $, show, hide, showError, hideError, escapeHtml } from "./dom.js";
import { state } from "./state.js";
import { api } from "./api.js";
import { SEASON_LABELS } from "./state.js";

// Which block types carry directly-editable text, and where it lives.
var HEADING_TEXT_TYPES = ["heading", "rubric"];

function panel() { return $("#rite-editor-panel"); }

export function showRiteEditorPanel(visible) {
    document.querySelector(".wizard-nav").hidden = visible;
    document.querySelectorAll(".wizard-panel").forEach(function(p) {
        p.style.display = visible ? "none" : "";
    });
    panel().hidden = !visible;
    if (visible) window.scrollTo(0, 0);
}

// ── Rite list ─────────────────────────────────────────────────────────

function riteRow(rite, isLibrary) {
    var row = document.createElement("div");
    row.className = "rite-row";

    var info = document.createElement("div");
    info.className = "rite-row-info";
    var name = document.createElement("span");
    name.className = "rite-row-name";
    name.textContent = rite.name;
    var meta = document.createElement("span");
    meta.className = "rite-row-meta";
    meta.textContent = (isLibrary ? "Starter rite" : "Your church")
        + (rite.occasion ? " · " + rite.occasion : "");
    info.appendChild(name);
    info.appendChild(meta);
    row.appendChild(info);

    var actions = document.createElement("div");
    actions.className = "rite-row-actions";
    if (isLibrary) {
        actions.appendChild(button("Use as starting point", "btn secondary",
            function() { forkRite(rite.id); }));
    } else {
        actions.appendChild(button("Edit", "btn secondary",
            function() { openRite(rite.id); }));
        actions.appendChild(button("Delete", "btn-link",
            function() { deleteRite(rite); }));
    }
    row.appendChild(actions);
    return row;
}

function button(label, cls, onClick) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = cls;
    b.textContent = label;
    b.addEventListener("click", onClick);
    return b;
}

async function loadRiteList() {
    hideError($("#rite-editor-error"));
    show($("#rite-list-spinner"));
    var result = await api.get_rites();
    hide($("#rite-list-spinner"));
    if (!result.success) {
        showError($("#rite-editor-error"), result.error || "Could not load rites.");
        return;
    }
    var list = $("#rite-list");
    list.innerHTML = "";
    var own = result.rites.filter(function(r) { return r.church_id !== null; });
    var library = result.rites.filter(function(r) { return r.church_id === null; });

    list.appendChild(subheading("Your rites"));
    if (!own.length) {
        list.appendChild(hint("None yet — fork a starter rite below to begin."));
    }
    own.forEach(function(r) { list.appendChild(riteRow(r, false)); });

    list.appendChild(subheading("Starter rites (read-only)"));
    library.forEach(function(r) { list.appendChild(riteRow(r, true)); });
}

function subheading(text) {
    var h = document.createElement("h3");
    h.textContent = text;
    return h;
}

function hint(text) {
    var p = document.createElement("p");
    p.className = "section-hint";
    p.textContent = text;
    return p;
}

// ── Fork / delete ─────────────────────────────────────────────────────

async function forkRite(fromRiteId) {
    hideError($("#rite-editor-error"));
    var result = await api.fork_rite(fromRiteId);
    if (!result.success) {
        showError($("#rite-editor-error"), result.error || "Could not fork the rite.");
        return;
    }
    await loadRiteList();
    openRiteObject(result.rite);
}

async function deleteRite(rite) {
    if (!window.confirm('Delete "' + rite.name + '"? This cannot be undone.'))
        return;
    hideError($("#rite-editor-error"));
    var result = await api.delete_rite(rite.id);
    if (!result.success) {
        showError($("#rite-editor-error"), result.error || "Could not delete.");
        return;
    }
    if (state.editingRite && state.editingRite.id === rite.id) {
        hide($("#rite-edit-card"));
        hide($("#rite-preview-card"));
        state.editingRite = null;
    }
    loadRiteList();
}

// ── Editor ────────────────────────────────────────────────────────────

async function openRite(riteId) {
    hideError($("#rite-editor-error"));
    var result = await api.get_rite(riteId);
    if (!result.success) {
        showError($("#rite-editor-error"), result.error || "Could not load the rite.");
        return;
    }
    openRiteObject(result.rite);
}

function openRiteObject(rite) {
    state.editingRite = rite;
    $("#rite-edit-title").textContent = "Edit: " + rite.name;
    $("#rite-name-input").value = rite.name || "";
    var roles = (rite.meta && rite.meta.role_labels) || {};
    $("#rite-role-leader").value = roles.leader || "P";
    $("#rite-role-congregation").value = roles.congregation || "C";
    renderBlocks(rite);
    hide($("#rite-saved"));
    hideError($("#rite-save-error"));
    show($("#rite-edit-card"));
    buildPreviewControls(rite);
    show($("#rite-preview-card"));
    $("#rite-edit-card").scrollIntoView({ behavior: "smooth" });
}

function renderBlocks(rite) {
    var container = $("#rite-blocks");
    container.innerHTML = "";
    rite.blocks.forEach(function(block, index) {
        container.appendChild(blockRow(rite, block, index));
    });
}

function blockRow(rite, block, index) {
    var row = document.createElement("div");
    row.className = "rite-block-row" + (block.enabled === false ? " disabled" : "");

    row.appendChild(blockOrderControls(rite, index));

    var main = document.createElement("div");
    main.className = "rite-block-main";
    main.appendChild(blockHeader(block));
    var textEditor = blockTextEditor(block);
    if (textEditor) main.appendChild(textEditor);
    main.appendChild(conditionEditor(block));
    row.appendChild(main);

    return row;
}

function blockOrderControls(rite, index) {
    var box = document.createElement("div");
    box.className = "rite-block-order";
    var up = button("▲", "btn-link", function() { moveBlock(rite, index, -1); });
    up.disabled = index === 0;
    var down = button("▼", "btn-link", function() { moveBlock(rite, index, 1); });
    down.disabled = index === rite.blocks.length - 1;
    box.appendChild(up);
    box.appendChild(down);
    return box;
}

function moveBlock(rite, index, delta) {
    var target = index + delta;
    if (target < 0 || target >= rite.blocks.length) return;
    var tmp = rite.blocks[index];
    rite.blocks[index] = rite.blocks[target];
    rite.blocks[target] = tmp;
    renderBlocks(rite);
}

function blockHeader(block) {
    var header = document.createElement("div");
    header.className = "rite-block-header";

    var label = document.createElement("span");
    label.className = "rite-block-label";
    label.innerHTML = "<strong>" + escapeHtml(block.title || block.id) + "</strong>"
        + ' <span class="rite-block-type">' + escapeHtml(block.type) + "</span>";
    header.appendChild(label);

    var toggle = document.createElement("label");
    toggle.className = "rite-block-enable";
    var cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = block.enabled !== false;
    cb.addEventListener("change", function() {
        block.enabled = cb.checked;
        var row = header.closest(".rite-block-row");
        if (row) row.classList.toggle("disabled", !cb.checked);
    });
    toggle.appendChild(cb);
    toggle.appendChild(document.createTextNode(" Enabled"));
    header.appendChild(toggle);

    return header;
}

/** Editable text controls for text-bearing blocks (returns null otherwise). */
function blockTextEditor(block) {
    if (HEADING_TEXT_TYPES.indexOf(block.type) !== -1) {
        return textareaFor(block, "text", "Text");
    }
    if (block.type === "literal_text" && typeof block.text === "string") {
        return textareaFor(block, "text", "Text");
    }
    if (block.type === "dialogue" && Array.isArray(block.lines)) {
        return dialogueEditor(block);
    }
    return null;
}

function textareaFor(block, key, labelText) {
    var wrap = document.createElement("div");
    wrap.className = "field";
    var label = document.createElement("label");
    label.textContent = labelText;
    wrap.appendChild(label);
    var ta = document.createElement("textarea");
    ta.className = "rite-block-text";
    ta.rows = 2;
    ta.value = block[key] || "";
    ta.addEventListener("input", function() { block[key] = ta.value; });
    wrap.appendChild(ta);
    return wrap;
}

function dialogueEditor(block) {
    var wrap = document.createElement("div");
    wrap.className = "rite-dialogue-editor";
    block.lines.forEach(function(line) {
        var rowEl = document.createElement("div");
        rowEl.className = "rite-dialogue-line";
        var role = document.createElement("span");
        role.className = "rite-dialogue-role";
        role.textContent = line.role || "none";
        rowEl.appendChild(role);
        var ta = document.createElement("textarea");
        ta.rows = 1;
        ta.value = line.text || "";
        ta.addEventListener("input", function() { line.text = ta.value; });
        rowEl.appendChild(ta);
        wrap.appendChild(rowEl);
    });
    return wrap;
}

// ── Condition editor (season list + toggle map + invert) ──────────────

function conditionEditor(block) {
    var details = document.createElement("details");
    details.className = "rite-condition-editor";
    var summary = document.createElement("summary");
    summary.textContent = "Visibility condition";
    details.appendChild(summary);

    var cond = block.condition || {};
    details.appendChild(seasonCheckboxes(block, cond));
    details.appendChild(toggleMapEditor(block, cond));
    details.appendChild(invertToggle(block, cond));
    return details;
}

/** Ensures block.condition exists; drops it again when fully empty. */
function ensureCondition(block) {
    if (!block.condition) block.condition = {};
    return block.condition;
}

function pruneCondition(block) {
    var c = block.condition;
    if (!c) return;
    if (c.seasons && !c.seasons.length) delete c.seasons;
    if (c.toggles && !Object.keys(c.toggles).length) delete c.toggles;
    if (c.invert === false) delete c.invert;
    if (!c.seasons && !c.toggles && !c.feasts && !c.invert) delete block.condition;
}

function seasonCheckboxes(block, cond) {
    var wrap = document.createElement("div");
    wrap.className = "rite-condition-seasons";
    var label = document.createElement("div");
    label.className = "rite-condition-label";
    label.textContent = "Only in these seasons (none = all seasons):";
    wrap.appendChild(label);

    var known = Object.keys(SEASON_LABELS);
    (cond.seasons || []).forEach(function(s) {
        if (known.indexOf(s) === -1) known.push(s);
    });
    known.forEach(function(season) {
        var l = document.createElement("label");
        l.className = "rite-condition-season";
        var cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = (cond.seasons || []).indexOf(season) !== -1;
        cb.addEventListener("change", function() {
            var c = ensureCondition(block);
            var seasons = c.seasons || [];
            if (cb.checked) {
                if (seasons.indexOf(season) === -1) seasons.push(season);
            } else {
                seasons = seasons.filter(function(x) { return x !== season; });
            }
            c.seasons = seasons;
            pruneCondition(block);
        });
        l.appendChild(cb);
        l.appendChild(document.createTextNode(" " + (SEASON_LABELS[season] || season)));
        wrap.appendChild(l);
    });
    return wrap;
}

function toggleMapEditor(block, cond) {
    var wrap = document.createElement("div");
    wrap.className = "rite-condition-toggles";
    var label = document.createElement("div");
    label.className = "rite-condition-label";
    label.textContent = "Only when these toggles match:";
    wrap.appendChild(label);

    var rows = document.createElement("div");
    rows.className = "rite-toggle-rows";
    wrap.appendChild(rows);

    Object.keys(cond.toggles || {}).forEach(function(name) {
        rows.appendChild(toggleRow(block, name, cond.toggles[name]));
    });

    wrap.appendChild(button("+ Add toggle", "btn secondary", function() {
        rows.appendChild(toggleRow(block, "", true));
    }));
    return wrap;
}

function toggleRow(block, name, value) {
    var row = document.createElement("div");
    row.className = "rite-toggle-row";

    var nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.placeholder = "toggle name (e.g. baptism)";
    nameInput.value = name;

    var valueSelect = document.createElement("select");
    ["true", "false"].forEach(function(v) {
        var opt = document.createElement("option");
        opt.value = v;
        opt.textContent = v === "true" ? "must be ON" : "must be OFF";
        if (String(value) === v) opt.selected = true;
        valueSelect.appendChild(opt);
    });

    function sync() {
        var c = ensureCondition(block);
        var toggles = {};
        row.parentElement.querySelectorAll(".rite-toggle-row").forEach(function(r) {
            var n = r.querySelector("input").value.trim();
            if (n) toggles[n] = r.querySelector("select").value === "true";
        });
        c.toggles = toggles;
        pruneCondition(block);
    }
    nameInput.addEventListener("input", sync);
    valueSelect.addEventListener("change", sync);

    var remove = button("×", "btn entry-remove-btn", function() {
        row.remove();
        sync();
    });

    row.appendChild(nameInput);
    row.appendChild(valueSelect);
    row.appendChild(remove);
    return row;
}

function invertToggle(block, cond) {
    var l = document.createElement("label");
    l.className = "rite-condition-invert";
    var cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = !!cond.invert;
    cb.addEventListener("change", function() {
        ensureCondition(block).invert = cb.checked;
        pruneCondition(block);
    });
    l.appendChild(cb);
    l.appendChild(document.createTextNode(" Invert (show when the above does NOT match)"));
    return l;
}

// ── Save ──────────────────────────────────────────────────────────────

async function saveRite() {
    var rite = state.editingRite;
    if (!rite) return;
    hide($("#rite-saved"));
    hideError($("#rite-save-error"));

    rite.name = $("#rite-name-input").value.trim();
    if (!rite.name) {
        showError($("#rite-save-error"), "Give the rite a name.");
        return;
    }
    if (!rite.meta) rite.meta = {};
    rite.meta.role_labels = {
        leader: $("#rite-role-leader").value.trim() || "P",
        congregation: $("#rite-role-congregation").value.trim() || "C",
    };

    var btn = $("#rite-save-btn");
    btn.disabled = true;
    var result = await api.save_rite(rite.id, rite);
    btn.disabled = false;
    if (!result.success) {
        showError($("#rite-save-error"), result.error || "Could not save the rite.");
        return;
    }
    state.editingRite = result.rite;
    show($("#rite-saved"));
    loadRiteList();
}

// ── Preview ───────────────────────────────────────────────────────────

function buildPreviewControls(rite) {
    var select = $("#rite-preview-season");
    select.innerHTML = "";
    Object.keys(SEASON_LABELS).forEach(function(key) {
        var opt = document.createElement("option");
        opt.value = key;
        opt.textContent = SEASON_LABELS[key];
        select.appendChild(opt);
    });

    var togglesEl = $("#rite-preview-toggles");
    togglesEl.innerHTML = "";
    collectToggleNames(rite).forEach(function(name) {
        var l = document.createElement("label");
        l.className = "rite-preview-toggle";
        var cb = document.createElement("input");
        cb.type = "checkbox";
        cb.dataset.toggle = name;
        l.appendChild(cb);
        l.appendChild(document.createTextNode(" " + name));
        togglesEl.appendChild(l);
    });
    $("#rite-preview-list").innerHTML = "";
}

function collectToggleNames(rite) {
    var names = {};
    rite.blocks.forEach(function(b) {
        var toggles = (b.condition && b.condition.toggles) || {};
        Object.keys(toggles).forEach(function(n) { names[n] = true; });
    });
    return Object.keys(names).sort();
}

async function refreshPreview() {
    var rite = state.editingRite;
    if (!rite) return;
    var toggles = {};
    $("#rite-preview-toggles").querySelectorAll("input[data-toggle]").forEach(
        function(cb) { toggles[cb.dataset.toggle] = cb.checked; });
    var context = { season: $("#rite-preview-season").value, toggles: toggles };
    var result = await api.preview_rite(rite.id, context);
    var listEl = $("#rite-preview-list");
    listEl.innerHTML = "";
    if (!result.success) {
        showError($("#rite-editor-error"), result.error || "Preview failed.");
        return;
    }
    result.blocks.forEach(function(b) {
        var item = document.createElement("div");
        item.className = "rite-preview-item" + (b.visible ? "" : " hidden-block");
        item.textContent = (b.visible ? "✓ " : "· ") + (b.title || b.id)
            + "  (" + b.type + ")";
        listEl.appendChild(item);
    });
}

// ── Wiring ────────────────────────────────────────────────────────────

export function setupRiteEditor() {
    var link = $("#rites-link");
    if (link) {
        link.addEventListener("click", function(e) {
            e.preventDefault();
            showRiteEditorPanel(true);
            loadRiteList();
        });
    }
    $("#rite-editor-back-btn").addEventListener("click", function() {
        showRiteEditorPanel(false);
    });
    $("#rite-cancel-btn").addEventListener("click", function() {
        hide($("#rite-edit-card"));
        hide($("#rite-preview-card"));
        state.editingRite = null;
    });
    $("#rite-save-btn").addEventListener("click", saveRite);
    $("#rite-preview-btn").addEventListener("click", refreshPreview);
}
