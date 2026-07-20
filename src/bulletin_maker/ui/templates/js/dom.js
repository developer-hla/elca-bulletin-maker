/* Bulletin Maker — DOM helpers */

// ── Helpers ──────────────────────────────────────────────────────────

export function $(sel) { return document.querySelector(sel); }
export function $$(sel) { return document.querySelectorAll(sel); }

export function show(el) { el.hidden = false; }
export function hide(el) { el.hidden = true; }

export function showError(el, msg) {
    el.textContent = msg;
    show(el);
}

export function hideError(el) {
    el.textContent = "";
    hide(el);
}

/** Replace button text with an inline spinner ring. */
export function showBtnSpinner(btn) {
    btn._savedText = btn.textContent;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-ring" style="width:14px;height:14px;border-width:2px;display:inline-block;vertical-align:middle;"></span>';
}

/** Restore button text after spinner. */
export function hideBtnSpinner(btn, text) {
    btn.disabled = false;
    btn.textContent = text || btn._savedText || "Fetch";
}

export function showWarning(el, msg) {
    el.textContent = msg;
    show(el);
}

export function hideWarning(el) {
    el.textContent = "";
    hide(el);
}

// Allowlist sanitizer for S&S-derived HTML (previews). Keeps textual
// structure, drops every attribute except class and any non-listed tag.
var SANITIZE_ALLOWED_TAGS = {
    P: 1, BR: 1, DIV: 1, SPAN: 1, SUP: 1, SUB: 1, EM: 1, STRONG: 1,
    B: 1, I: 1, H3: 1, H4: 1, UL: 1, OL: 1, LI: 1,
};

export function sanitizeHtml(html) {
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

export function escapeHtml(str) {
    var div = document.createElement("div");
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}
