/* Bulletin Maker — Operator console (service owner) */

import { $, $$, show, hide, showError, hideError, escapeHtml } from "./dom.js";
import { api } from "./api.js";

// ── Panel visibility ─────────────────────────────────────────────────

export function showOperatorPanel(visible) {
    // Mirror the settings panel: hide the wizard via inline display so its
    // own active-class state survives and restores when the panel closes.
    document.querySelector(".wizard-nav").hidden = visible;
    $$(".wizard-panel").forEach(function(panel) {
        panel.style.display = visible ? "none" : "";
    });
    if (visible) $("#settings-panel").hidden = true;
    $("#operator-panel").hidden = !visible;
    if (visible) window.scrollTo(0, 0);
}

// ── Formatting helpers ───────────────────────────────────────────────

function _fmtWhen(iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    return isNaN(d.getTime()) ? escapeHtml(iso) : d.toLocaleString();
}

// ── Churches ─────────────────────────────────────────────────────────

async function loadChurches() {
    hideError($("#operator-churches-error"));
    var result = await api.operator_churches();
    if (!result.success) {
        showError($("#operator-churches-error"),
                  result.error || "Could not load churches.");
        return;
    }
    var rows = result.churches.map(_churchRow).join("");
    $("#operator-churches-body").innerHTML = rows ||
        '<tr><td colspan="7">No churches yet.</td></tr>';
}

function _churchRow(c) {
    var status = c.disabled
        ? '<span class="op-badge op-disabled">Disabled</span>'
        : '<span class="op-badge op-active">Active</span>';
    var toggle = '<button class="btn secondary op-toggle" data-id="' + c.id +
        '" data-disabled="' + (c.disabled ? "1" : "0") +
        '" data-name="' + escapeHtml(c.name) + '">' +
        (c.disabled ? "Enable" : "Disable") + "</button>";
    return "<tr><td>" + escapeHtml(c.name) + "</td><td>" + c.member_count +
        "</td><td>" + escapeHtml(c.plan) + "</td><td>" +
        (c.sns_linked ? "Yes" : "No") + "</td><td>" +
        c.generates_this_month + "</td><td>" + status + "</td><td>" +
        toggle + "</td></tr>";
}

async function _toggleChurch(button) {
    var churchId = button.getAttribute("data-id");
    var currentlyDisabled = button.getAttribute("data-disabled") === "1";
    var name = button.getAttribute("data-name");
    var verb = currentlyDisabled ? "enable" : "disable";
    var warning = currentlyDisabled
        ? "Re-enable " + name + "? Its members will be able to sign in again."
        : "Disable " + name + "? Its members will be signed out and blocked " +
          "from signing in.";
    if (!confirm(warning)) return;
    button.disabled = true;
    var result = await api.operator_set_disabled(churchId, !currentlyDisabled);
    if (!result.success) {
        button.disabled = false;
        showError($("#operator-churches-error"),
                  result.error || "Could not update the church.");
        return;
    }
    loadChurches();
}

// ── Jobs ─────────────────────────────────────────────────────────────

async function loadJobs() {
    hideError($("#operator-jobs-error"));
    var result = await api.operator_jobs();
    if (!result.success) {
        showError($("#operator-jobs-error"),
                  result.error || "Could not load jobs.");
        return;
    }
    var rows = result.jobs.map(_jobRow).join("");
    $("#operator-jobs-body").innerHTML = rows ||
        '<tr><td colspan="4">No jobs yet.</td></tr>';
}

function _jobRow(j) {
    var status = '<span class="op-status op-status-' + escapeHtml(j.status) +
        '">' + escapeHtml(j.status) + "</span>";
    return "<tr><td>" + escapeHtml(j.church_name) + "</td><td>" + status +
        "</td><td>" + _fmtWhen(j.created_at) + "</td><td class=\"op-error\">" +
        escapeHtml(j.error || "") + "</td></tr>";
}

// ── Cache ────────────────────────────────────────────────────────────

async function loadCache() {
    var result = await api.operator_cache();
    if (!result.success) {
        $("#operator-cache-stats").textContent =
            result.error || "Could not load cache stats.";
        return;
    }
    var c = result.cache;
    var kinds = Object.keys(c.by_kind).map(function(k) {
        return k + ": " + c.by_kind[k];
    }).join(", ") || "none";
    $("#operator-cache-stats").textContent =
        c.entries + " entries (" + kinds + "). Oldest " +
        (c.oldest_fetched_at ? new Date(c.oldest_fetched_at).toLocaleString() : "—") +
        ", newest " +
        (c.newest_fetched_at ? new Date(c.newest_fetched_at).toLocaleString() : "—") + ".";
}

// ── Audit ────────────────────────────────────────────────────────────

async function loadAudit() {
    var result = await api.operator_audit();
    if (!result.success) {
        $("#operator-audit-list").innerHTML =
            "<li>" + escapeHtml(result.error || "Could not load audit log.") + "</li>";
        return;
    }
    var items = result.events.map(_auditItem).join("");
    $("#operator-audit-list").innerHTML = items || "<li>No events yet.</li>";
}

function _auditItem(e) {
    var who = e.actor_email ? escapeHtml(e.actor_email) : "system";
    var where = e.church_name ? " · " + escapeHtml(e.church_name) : "";
    return '<li><span class="op-audit-when">' + _fmtWhen(e.at) +
        '</span> <span class="op-audit-action">' + escapeHtml(e.action) +
        "</span> — " + who + where + "</li>";
}

// ── Wiring ───────────────────────────────────────────────────────────

function refreshAll() {
    loadChurches();
    loadJobs();
    loadCache();
    loadAudit();
}

export function setupOperator() {
    var link = $("#operator-link");
    if (link) {
        link.addEventListener("click", function(e) {
            e.preventDefault();
            showOperatorPanel(true);
            refreshAll();
        });
    }
    $("#operator-back-btn").addEventListener("click", function() {
        showOperatorPanel(false);
    });
    $("#operator-churches-refresh").addEventListener("click", loadChurches);
    $("#operator-jobs-refresh").addEventListener("click", loadJobs);
    $("#operator-cache-refresh").addEventListener("click", loadCache);
    $("#operator-audit-refresh").addEventListener("click", loadAudit);
    $("#operator-churches-body").addEventListener("click", function(e) {
        var button = e.target.closest(".op-toggle");
        if (button) _toggleChurch(button);
    });
}
