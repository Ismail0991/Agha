/* =========================================================
   Aghaz Limited — shared UI layer
   - Ambient page animations (reveal, gradient shift, float)
   - Micro-interactions (button press/hover, card & row hover)
   - Global loading states: top progress bar + button/link spinners
   Self-contained: injects its own CSS. Include once per page.
   ========================================================= */
(function () {
  "use strict";

  // ---------- Injected styles ----------
  var css = `
  /* Top progress bar */
  #ui-topbar{position:fixed;top:0;left:0;height:3px;width:0;z-index:99999;
    background:linear-gradient(90deg,#ef4444,#f59e0b,#ef4444);
    box-shadow:0 0 10px rgba(239,68,68,.6);opacity:1;
    transition:width .4s ease,opacity .4s ease;}
  #ui-topbar.active{width:90%;}
  #ui-topbar.done{width:100%;opacity:0;}

  /* Spinner appended to buttons/links */
  .ui-spinner{display:inline-block;width:1em;height:1em;margin-left:.5em;
    border:2px solid currentColor;border-right-color:transparent;border-radius:50%;
    vertical-align:-2px;animation:ui-spin .6s linear infinite;}
  @keyframes ui-spin{to{transform:rotate(360deg);}}

  /* Reveal-on-load */
  @keyframes ui-reveal{from{opacity:0;transform:translateY(16px);}to{opacity:1;transform:translateY(0);}}

  /* Slow gradient drift on branding / headers */
  @keyframes ui-gradient{0%{background-position:0% 50%;}50%{background-position:100% 50%;}100%{background-position:0% 50%;}}
  [class*="bg-gradient"]{background-size:200% 200%;animation:ui-gradient 14s ease infinite;}

  /* Floating illustrations */
  @keyframes ui-float{0%,100%{transform:translateY(0);}50%{transform:translateY(-10px);}}
  .ui-float{animation:ui-float 4.5s ease-in-out infinite;}

  /* Toast slide-in (used by index/dashboards) */
  @keyframes slideIn{from{opacity:0;transform:translateX(40px);}to{opacity:1;transform:translateX(0);}}
  .animate-slideIn{animation:slideIn .45s cubic-bezier(.2,.8,.2,1);}

  /* Micro-interactions */
  button,a{transition:transform .15s ease,box-shadow .2s ease,filter .2s ease,background-color .2s ease,opacity .2s ease;}
  button:not(:disabled):hover{transform:translateY(-1px);filter:brightness(1.04);}
  button:not(:disabled):active{transform:translateY(0) scale(.97);}
  button:disabled{opacity:.7;cursor:not-allowed;}
  a[class*="bg-"]:hover{transform:translateY(-1px);filter:brightness(1.04);}
  a[class*="bg-"]:active{transform:translateY(0) scale(.98);}

  /* Card & table row hover */
  .search-row{transition:transform .2s ease,box-shadow .2s ease;}
  .search-row:hover{transform:translateY(-3px);box-shadow:0 12px 24px rgba(0,0,0,.10);}
  tbody tr{transition:background-color .15s ease;}
  tbody tr:hover{background-color:rgba(220,38,38,.05);}

  /* Inputs focus polish */
  input,select,textarea{transition:box-shadow .2s ease,border-color .2s ease;}

  /* Live-update badge */
  #ui-live{position:fixed;left:12px;bottom:12px;z-index:99998;display:flex;align-items:center;gap:7px;
    background:#fff;border:1px solid #eee;color:#374151;font:500 12px system-ui,sans-serif;
    padding:6px 11px;border-radius:999px;box-shadow:0 4px 14px rgba(0,0,0,.10);opacity:.9;}
  #ui-live .dot{width:8px;height:8px;border-radius:50%;background:#22c55e;animation:ui-pulse 2s infinite;}
  @keyframes ui-pulse{0%{box-shadow:0 0 0 0 rgba(34,197,94,.5);}70%{box-shadow:0 0 0 8px rgba(34,197,94,0);}100%{box-shadow:0 0 0 0 rgba(34,197,94,0);}}
  #ui-live.flash{animation:ui-liveflash .6s ease;}
  @keyframes ui-liveflash{0%{transform:scale(1);}50%{transform:scale(1.08);background:#ecfdf5;}100%{transform:scale(1);}}

  /* Install (PWA) button */
  #ui-install{position:fixed;right:14px;bottom:14px;z-index:99998;display:none;align-items:center;gap:8px;
    background:linear-gradient(135deg,#ef4444,#dc2626);color:#fff;font:600 13px system-ui,sans-serif;
    padding:10px 16px;border:none;border-radius:999px;box-shadow:0 8px 22px rgba(220,38,38,.38);cursor:pointer;
    animation:ui-float 4.5s ease-in-out infinite;}
  #ui-install:hover{filter:brightness(1.06);}
  #ui-install.show{display:flex;}

  @media (prefers-reduced-motion: reduce){
    *{animation:none !important;transition:none !important;}
  }`;
  var style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  // ---------- Top progress bar ----------
  var bar = document.createElement("div");
  bar.id = "ui-topbar";
  function startBar() { bar.classList.remove("done"); bar.classList.add("active"); }
  function finishBar() { bar.classList.remove("active"); bar.classList.add("done"); }

  function makeSpinner() {
    var s = document.createElement("span");
    s.className = "ui-spinner";
    return s;
  }

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  ready(function () {
    document.body.appendChild(bar);

    // 1) Reveal major cards/sections with a gentle stagger
    var blocks = document.querySelectorAll(
      "main > *, section, .bg-white.shadow-lg, .bg-white.shadow-2xl, .bg-white.shadow"
    );
    var seen = [], i = 0;
    blocks.forEach(function (el) {
      if (seen.indexOf(el) !== -1) return;
      seen.push(el);
      el.style.opacity = "0";
      el.style.animation = "ui-reveal .5s ease forwards";
      el.style.animationDelay = (i * 0.07).toFixed(2) + "s";
      i++;
    });

    // 2) Float branding illustrations
    document.querySelectorAll('img[alt*="Illustration"], img[alt="branding"], img[alt="Employee"], img[alt="No Image"]').forEach(function (img) {
      // only float standalone branding images, not list avatars
      if (img.closest(".search-row")) return;
      img.classList.add("ui-float");
    });

    // 3) Loading state on form submit (only fires when native validation passes)
    document.querySelectorAll("form").forEach(function (f) {
      f.addEventListener("submit", function () {
        var btn = f.querySelector('button[type="submit"], button:not([type])');
        if (btn && !btn.dataset.uiBusy) {
          btn.dataset.uiBusy = "1";
          // Don't double up if the page already has its own animate-spin spinner
          if (!btn.querySelector(".animate-spin") && !btn.querySelector(".ui-spinner")) {
            btn.appendChild(makeSpinner());
          }
          // Disable AFTER the tick so submission still goes through
          setTimeout(function () { btn.disabled = true; }, 0);
          // Fallback: file-download forms don't navigate — restore after 6s
          setTimeout(function () {
            btn.disabled = false;
            delete btn.dataset.uiBusy;
            var sp = btn.querySelector(".ui-spinner");
            if (sp) sp.remove();
            finishBar();
          }, 6000);
        }
        startBar();
      });
    });

    // 4) Loading state on action navigation links
    var ACTION = /\/delete\/|\/edit\/|\/leaves\/|\/generate_invite|\/logout/;
    document.querySelectorAll("a[href]").forEach(function (a) {
      var href = a.getAttribute("href");
      if (!href || href.charAt(0) === "#" || a.target === "_blank" || href.indexOf("javascript:") === 0) return;
      a.addEventListener("click", function () {
        startBar();
        if (ACTION.test(href) && !a.dataset.uiBusy) {
          a.dataset.uiBusy = "1";
          a.appendChild(makeSpinner());
          a.style.pointerEvents = "none";
          a.classList.add("opacity-80");
        }
      });
    });
  });

  // ---------- Seamless live updates ----------
  // Poll the current URL and swap in only the [data-live] regions that changed.
  // Skips while the user is interacting (typing, open modal/menu) or the tab is hidden.
  ready(function () {
    var liveEls = document.querySelectorAll("[data-live]");
    if (!liveEls.length) return;

    var badge = document.createElement("div");
    badge.id = "ui-live";
    badge.innerHTML = '<span class="dot"></span><span>Live</span>';
    document.body.appendChild(badge);

    var INTERVAL = 6000;

    function interacting() {
      var a = document.activeElement;
      if (a && (a.tagName === "INPUT" || a.tagName === "SELECT" || a.tagName === "TEXTAREA")) return true;
      if (document.querySelector(".modal:not(.hidden)")) return true;   // letter modal open
      if (document.querySelector(".menu:not(.hidden)")) return true;    // dropdown open
      return false;
    }

    function reapplyState() {
      // Re-apply client-side filters/search after a swap (controls live outside the swapped body)
      ["searchInput", "searchInputMobile"].forEach(function (id) {
        var s = document.getElementById(id);
        if (s && s.value) s.dispatchEvent(new Event("input"));
      });
      if (typeof window.filterLeaves === "function") { try { window.filterLeaves(); } catch (e) {} }
      if (typeof window.filterAtt === "function") { try { window.filterAtt(); } catch (e) {} }
    }

    function poll() {
      if (document.hidden || interacting()) return;
      // Cache-bust so proxies/CDNs (e.g. Render's edge) can't serve a stale page
      var base = window.location.href.split("#")[0];
      var url = base + (base.indexOf("?") === -1 ? "?" : "&") + "_ts=" + Date.now();
      fetch(url, { credentials: "same-origin", cache: "no-store", headers: { "X-Requested-With": "fetch" } })
        .then(function (res) { return res.ok ? res.text() : null; })
        .then(function (html) {
          if (!html) return;
          var doc = new DOMParser().parseFromString(html, "text/html");
          var changed = false;
          document.querySelectorAll("[data-live]").forEach(function (el) {
            if (!el.id) return;
            var fresh = doc.getElementById(el.id);
            if (fresh && fresh.innerHTML !== el.innerHTML) {
              el.innerHTML = fresh.innerHTML;
              changed = true;
            }
          });
          if (changed) {
            reapplyState();
            badge.classList.remove("flash");
            void badge.offsetWidth; // restart animation
            badge.classList.add("flash");
          }
        })
        .catch(function () { /* transient network error — ignore */ });
    }

    setInterval(poll, INTERVAL);
  });

  // ---------- PWA: service worker registration + install button ----------
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js").catch(function () {});
    });
  }

  ready(function () {
    var btn = document.createElement("button");
    btn.id = "ui-install";
    btn.type = "button";
    btn.innerHTML = "⬇️ Install App";
    document.body.appendChild(btn);

    var deferred = null;
    var isStandalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
    var isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);

    // Chrome / Edge / Android: capture the install prompt and reveal the button
    window.addEventListener("beforeinstallprompt", function (e) {
      e.preventDefault();
      deferred = e;
      if (!isStandalone) btn.classList.add("show");
    });

    btn.addEventListener("click", function () {
      if (deferred) {
        deferred.prompt();
        deferred.userChoice.finally(function () {
          deferred = null;
          btn.classList.remove("show");
        });
      } else if (isIOS) {
        alert("To install on iPhone/iPad:\n\n1. Tap the Share button (□↑) in Safari\n2. Choose 'Add to Home Screen'");
      }
    });

    window.addEventListener("appinstalled", function () {
      btn.classList.remove("show");
    });

    // iOS Safari has no install prompt — show the button with instructions instead
    if (isIOS && !isStandalone) btn.classList.add("show");
  });

  // Finish the bar + clear any stuck spinners when the page (re)appears
  window.addEventListener("load", finishBar);
  window.addEventListener("pageshow", function () {
    finishBar();
    document.querySelectorAll(".ui-spinner").forEach(function (s) { s.remove(); });
    document.querySelectorAll("[data-ui-busy]").forEach(function (el) {
      delete el.dataset.uiBusy;
      if (el.tagName === "BUTTON") el.disabled = false;
      el.style.pointerEvents = "";
      el.classList.remove("opacity-80");
    });
  });
})();
