/* Bulletin Maker — Church settings panel */

import { $, $$, show, hide, showError, hideError, hideWarning, showBtnSpinner, hideBtnSpinner } from "./dom.js";
import { state } from "./state.js";
import { api } from "./api.js";
import { loadChurchLabels } from "./auth.js";

// ── Church settings panel ────────────────────────────────────────────

export function showSettingsPanel(visible) {
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

export function setupSettings() {
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
