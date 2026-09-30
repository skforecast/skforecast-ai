/*
 * Window with real answers of ask() (docs/overrides/partials/ask-window.html),
 * on the home page and on the "Ask the assistant" page.
 *
 * Highlights the Python of every `code[data-hl]` inside `.sk-ask` and switches
 * the tabs, with the arrow keys of the WAI-ARIA tabs pattern. The highlighter
 * is also exposed as `window.skHighlight` for home.js, which is loaded after
 * this file. With navigation.instant, `document$` emits on every page change;
 * the listeners live on elements that are replaced with the page, so there is
 * nothing to destroy.
 */
(function () {
  "use strict";

  /* ---------- syntax highlight ---------- */
  var KEYWORDS = { from: 1, import: 1, None: 1, True: 1, False: 1, def: 1, return: 1, for: 1, in: 1, if: 1, as: 1 };
  function esc(t) { return t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
  function wrap(cls, t) { return cls ? '<span class="' + cls + '">' + esc(t) + "</span>" : esc(t); }
  function hl(src) {
    var re = /(#[^\n]*)|("[^"\n]*"?|'[^'\n]*'?)|([A-Za-z_]\w*)|(\d+(?:\.\d+)?)|([()[\]{},.:=+\-*\/])/g;
    var out = "", last = 0, inFrom = false, m;
    while ((m = re.exec(src)) !== null) {
      out += esc(src.slice(last, m.index));
      last = re.lastIndex;
      var tok = m[0], cls = "";
      if (m[1]) cls = "tk-m";
      else if (m[2]) cls = "tk-s";
      else if (m[4]) cls = "tk-n";
      else if (m[5]) cls = "tk-p";
      else if (KEYWORDS[tok]) {
        cls = "tk-k";
        if (tok === "from") inFrom = true;
        if (tok === "import") inFrom = false;
      } else if (inFrom) {
        cls = "";                                   /* module path */
      } else {
        var rest = src.slice(last);
        if (/^[A-Z]/.test(tok)) cls = "tk-c";       /* class */
        else if (/^\s*\(/.test(rest)) cls = "tk-f"; /* function or method call */
        else if (tok === "f" && /^["']/.test(rest)) cls = "tk-s";  /* f-string prefix */
      }
      out += wrap(cls, tok);
    }
    return out + esc(src.slice(last));
  }
  window.skHighlight = hl;

  /* ---------- tabs ---------- */
  function initWindow(win) {
    Array.prototype.forEach.call(win.querySelectorAll("code[data-hl]"), function (c) {
      c.innerHTML = hl(c.textContent);
    });
    var tabs = Array.prototype.slice.call(win.querySelectorAll(".ask-tab"));
    function show(k, focus) {
      tabs.forEach(function (b, j) {
        var on = j === k;
        b.classList.toggle("on", on);
        b.setAttribute("aria-selected", on ? "true" : "false");
        b.tabIndex = on ? 0 : -1;
        document.getElementById(b.getAttribute("aria-controls")).classList.toggle("on", on);
      });
      if (focus) tabs[k].focus();
    }
    tabs.forEach(function (b, k) {
      b.addEventListener("click", function () { show(k, false); });
      b.addEventListener("keydown", function (e) {
        var n = tabs.length;
        var to = e.key === "ArrowRight" ? (k + 1) % n : e.key === "ArrowLeft" ? (k + n - 1) % n :
          e.key === "Home" ? 0 : e.key === "End" ? n - 1 : -1;
        if (to >= 0) { e.preventDefault(); show(to, true); }
      });
    });
  }

  function onDocument() {
    Array.prototype.forEach.call(document.querySelectorAll(".sk-ask"), initWindow);
  }
  if (typeof document$ !== "undefined") {
    document$.subscribe(onDocument);
  } else {
    document.addEventListener("DOMContentLoaded", onDocument);
  }
})();
