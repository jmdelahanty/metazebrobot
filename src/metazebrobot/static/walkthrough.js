/**
 * In-browser guided walkthrough using Driver.js.
 *
 * Tour state persists in localStorage so it survives page navigation.
 * Each page load checks if a tour is active and runs the steps that
 * match the current URL.
 */

(function () {
  "use strict";

  var KEY_ACTIVE = "walkthrough_active";
  var KEY_STEP = "walkthrough_step";
  var KEY_DATA = "walkthrough_data";

  // ── Tour step definitions ──────────────────────────────────────
  // page: URL path pattern (exact match or prefix with *)
  // element: CSS selector to highlight (null = floating popover)
  // title / description: tooltip content
  // waitFor: "next" = wait for Next button, "click" = wait for click on element
  // navigateTo: URL to go to after this step (null = stay on page)

  // Helper: get the first dish ID from the table on the current page
  function getFirstDishId() {
    var cell = document.querySelector("table tbody tr:first-child td:first-child");
    return cell ? cell.textContent.trim() : null;
  }

  var STEPS = [
    // -- Screening dish list --
    {
      page: "/screening/",
      element: "#scan-input",
      title: "Welcome to MetaZebrobot!",
      description: "This input lets you scan a barcode or type a dish ID. We've pre-filled the first dish — press Enter to navigate to it, or click Next to continue the tour.",
      waitFor: "next",
      onShow: function () {
        var input = document.getElementById("scan-input");
        var dishId = getFirstDishId();
        if (input && dishId) {
          input.value = dishId;
          input.focus();
        }
      },
    },
    {
      page: "/screening/",
      element: "table tbody tr:first-child",
      title: "Pick a Dish",
      description: "Each row is an active dish. Click 'Screen' to open the screening form for a dish.",
      waitFor: "next",
    },
    {
      page: "/screening/",
      element: "table tbody tr:first-child a[href*='/screening/']",
      title: "Open Screening",
      description: "Click this button to start screening.",
      waitFor: "click",
    },
    // -- Screening form --
    {
      page: "/screening/*",
      element: ".protocol-box",
      title: "Screening Protocol",
      description: "The recommended protocol is shown here based on the dish's genotype and DPF. Reference images from your lab are displayed for each indicator.",
      waitFor: "next",
    },
    {
      page: "/screening/*",
      element: "details.protocol-box:nth-of-type(2)",
      title: "Atlas Reference",
      description: "Expression pattern images from the mapzebrain atlas are shown automatically for recognised transgenic lines.",
      waitFor: "next",
      optional: true,
    },
    {
      page: "/screening/*",
      element: "#steps-table",
      title: "Screening Steps",
      description: "Previous screening steps are listed here. New steps are added via the form below.",
      waitFor: "next",
    },
    {
      page: "/screening/*",
      element: null,
      title: "Screening Complete!",
      description: "You can add steps, upload images, finalize screening, and create derived dishes. Let's check out daily care next.",
      waitFor: "next",
      navigateTo: "/care/",
    },
    // -- Care dish list --
    {
      page: "/care/",
      element: "#scan-input",
      title: "Daily Care",
      description: "Dishes not checked today are highlighted in red. The first dish ID has been pre-filled — press Enter to navigate, or click Next.",
      waitFor: "next",
      onShow: function () {
        var input = document.getElementById("scan-input");
        var dishId = getFirstDishId();
        if (input && dishId) {
          input.value = dishId;
          input.focus();
        }
      },
    },
    {
      page: "/care/",
      element: "table tbody tr:first-child",
      title: "Check a Dish",
      description: "Click 'Check' to log feeding, water changes, and mortality.",
      waitFor: "next",
    },
    {
      page: "/care/",
      element: "table tbody tr:first-child a[href*='/care/']",
      title: "Open Care Form",
      description: "Click to open the care form for this dish.",
      waitFor: "click",
    },
    // -- Care form --
    {
      page: "/care/*",
      element: "form",
      title: "Care Form",
      description: "Log feeding, water changes, and dead fish. For well plates, each unit gets its own row. Submit saves the check and updates the history below.",
      waitFor: "next",
    },
    {
      page: "/care/*",
      element: "a[href*='/label']",
      title: "Print Label",
      description: "Click 'Print Label' to generate a label with a QR code. Print it and stick it on the dish — scanning it brings you right back here!",
      waitFor: "next",
    },
    {
      page: "/care/*",
      element: "a[href*='/fish/']",
      title: "Fish Management",
      description: "Click 'Fish' to manage individual fish, housing units, and see the plate map.",
      waitFor: "click",
    },
    // -- Fish list --
    {
      page: "/dishes/*/fish/",
      element: "#plate-map",
      title: "Housing Map",
      description: "For well plates, occupied wells are shown in green with fish labels. Unassigned fish are listed below the grid.",
      waitFor: "next",
    },
    {
      page: "/dishes/*/fish/",
      element: "#fish-table",
      title: "Registered Fish",
      description: "All registered fish for this dish are listed here. You can register new fish individually or in batches.",
      waitFor: "next",
    },
    {
      page: "/dishes/*/fish/",
      element: null,
      title: "Tour Complete!",
      description: "You've seen screening, daily care, fish management, plate maps, labels, and atlas references. Happy fish tracking!",
      waitFor: "next",
    },
  ];

  // ── Helpers ────────────────────────────────────────────────────

  function pathMatches(pattern, path) {
    if (pattern.endsWith("*")) {
      return path.startsWith(pattern.slice(0, -1));
    }
    // Handle /dishes/*/fish/ patterns
    if (pattern.includes("*")) {
      var regex = new RegExp(
        "^" + pattern.replace(/\*/g, "[^/]+") + "$"
      );
      return regex.test(path);
    }
    return path === pattern;
  }

  function getGlobalStep() {
    return parseInt(localStorage.getItem(KEY_STEP) || "0", 10);
  }

  function setGlobalStep(n) {
    localStorage.setItem(KEY_STEP, String(n));
  }

  function isActive() {
    return localStorage.getItem(KEY_ACTIVE) === "true";
  }

  function stopTour() {
    // Cleanup test data if any
    var dataStr = localStorage.getItem(KEY_DATA);
    if (dataStr) {
      try {
        var data = JSON.parse(dataStr);
        var xhr = new XMLHttpRequest();
        xhr.open("POST", "/walkthrough/cleanup", false); // synchronous so it finishes before nav
        xhr.setRequestHeader("Content-Type", "application/json");
        xhr.send(JSON.stringify(data));
      } catch (e) {
        console.warn("Walkthrough cleanup failed:", e);
      }
    }
    localStorage.removeItem(KEY_ACTIVE);
    localStorage.removeItem(KEY_STEP);
    localStorage.removeItem(KEY_DATA);
  }

  function startTour() {
    // Setup test data via API
    var xhr = new XMLHttpRequest();
    xhr.open("POST", "/walkthrough/setup", false); // synchronous
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.send("{}");
    if (xhr.status === 200) {
      var data = JSON.parse(xhr.responseText);
      localStorage.setItem(KEY_DATA, JSON.stringify(data));
    }
    localStorage.setItem(KEY_ACTIVE, "true");
    localStorage.setItem(KEY_STEP, "0");
    window.location.href = "/screening/";
  }

  // ── Tour runner ────────────────────────────────────────────────

  function runTour() {
    if (typeof window.driver === "undefined") return;

    var currentPath = window.location.pathname;
    var globalStep = getGlobalStep();

    // Find the current global step
    if (globalStep >= STEPS.length) {
      stopTour();
      return;
    }

    var step = STEPS[globalStep];

    // If current page doesn't match this step's page, navigate there
    if (!pathMatches(step.page, currentPath)) {
      // Maybe we're ahead — skip optional steps
      for (var i = globalStep; i < STEPS.length; i++) {
        if (pathMatches(STEPS[i].page, currentPath)) {
          setGlobalStep(i);
          step = STEPS[i];
          globalStep = i;
          break;
        }
      }
      // Still doesn't match — navigate
      if (!pathMatches(step.page, currentPath)) {
        return; // Don't navigate automatically, wait for user
      }
    }

    // Collect consecutive steps on this page
    var pageSteps = [];
    for (var j = globalStep; j < STEPS.length; j++) {
      if (!pathMatches(STEPS[j].page, currentPath)) break;
      var s = STEPS[j];
      // Skip optional steps whose element doesn't exist
      if (s.optional && s.element && !document.querySelector(s.element)) {
        continue;
      }
      pageSteps.push({ globalIndex: j, def: s });
    }

    if (pageSteps.length === 0) return;

    var driverSteps = pageSteps.map(function (ps) {
      var dStep = {
        popover: {
          title: ps.def.title,
          description: ps.def.description,
        },
      };
      if (ps.def.element) {
        dStep.element = ps.def.element;
      }
      if (ps.def.onShow) {
        dStep.onHighlighted = ps.def.onShow;
      }
      return dStep;
    });

    var driverObj = window.driver.js.driver({
      showProgress: true,
      showButtons: ["next", "previous", "close"],
      steps: driverSteps,
      onCloseClick: function () {
        stopTour();
        driverObj.destroy();
      },
      onDestroyed: function () {
        // If tour is still active, we just finished this page's steps
      },
      onNextClick: function () {
        var localIdx = driverObj.getActiveIndex();
        var ps = pageSteps[localIdx];

        if (ps.def.waitFor === "click" && ps.def.element) {
          // Don't advance — wait for user to click the element
          return;
        }

        // Advance
        var nextGlobal = ps.globalIndex + 1;

        // Skip any optional steps that don't have matching elements
        while (nextGlobal < STEPS.length && STEPS[nextGlobal].optional &&
               STEPS[nextGlobal].element && !document.querySelector(STEPS[nextGlobal].element)) {
          nextGlobal++;
        }

        setGlobalStep(nextGlobal);

        if (ps.def.navigateTo) {
          driverObj.destroy();
          window.location.href = ps.def.navigateTo;
          return;
        }

        if (localIdx < driverSteps.length - 1) {
          driverObj.moveNext();
        } else {
          // End of page steps
          driverObj.destroy();
          if (nextGlobal >= STEPS.length) {
            stopTour();
          }
        }
      },
    });

    // Set up click listeners for "waitFor: click" steps
    pageSteps.forEach(function (ps, localIdx) {
      if (ps.def.waitFor === "click" && ps.def.element) {
        var el = document.querySelector(ps.def.element);
        if (el) {
          el.addEventListener("click", function () {
            var nextGlobal = ps.globalIndex + 1;
            setGlobalStep(nextGlobal);
            // Navigation happens naturally from the link click
          }, { once: true });
        }
      }
    });

    // Start the driver
    driverObj.drive();
  }

  // ── Initialization ─────────────────────────────────────────────

  // Expose startTour globally for the nav button
  window.startWalkthrough = startTour;

  // Run tour on page load if active
  document.addEventListener("DOMContentLoaded", function () {
    if (isActive()) {
      // Small delay to let HTMX partials load
      setTimeout(runTour, 300);
    }
  });
})();
