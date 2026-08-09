/**
 * Recipe list view: pagination controls, rendering of recipe cards/rows.
 * Works against the server-rendered /recipes page and augments it with
 * client-side pagination fetches (HTMX-compatible, progressive enhancement).
 */
(function () {
  "use strict";

  const PAGE_SIZE = 10;

  function qs(name, fallback) {
    const params = new URLSearchParams(window.location.search);
    return params.has(name) ? params.get(name) : fallback;
  }

  function buildUrl(page) {
    const params = new URLSearchParams(window.location.search);
    params.set("page", page);
    params.set("page_size", PAGE_SIZE);
    return `/recipes?${params.toString()}`;
  }

  function goToPage(page) {
    if (page < 1) return;
    window.location.href = buildUrl(page);
  }

  function initPaginationControls() {
    const root = document.querySelector("[data-recipe-list]") || document;

    const prevBtn = root.querySelector("[data-page-prev]");
    const nextBtn = root.querySelector("[data-page-next]");
    const pageButtons = root.querySelectorAll("[data-page-number]");

    const currentPage = parseInt(qs("page", "1"), 10) || 1;
    const totalPages = parseInt(
      root.getAttribute("data-total-pages") ||
        (root.querySelector("[data-total-pages]") &&
          root.querySelector("[data-total-pages]").getAttribute("data-total-pages")) ||
        "1",
      10
    );

    if (prevBtn) {
      prevBtn.disabled = currentPage <= 1;
      prevBtn.addEventListener("click", function (e) {
        e.preventDefault();
        if (currentPage > 1) goToPage(currentPage - 1);
      });
    }

    if (nextBtn) {
      nextBtn.disabled = totalPages > 0 && currentPage >= totalPages;
      nextBtn.addEventListener("click", function (e) {
        e.preventDefault();
        if (!totalPages || currentPage < totalPages) goToPage(currentPage + 1);
      });
    }

    pageButtons.forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        const target = parseInt(btn.getAttribute("data-page-number"), 10);
        if (!Number.isNaN(target)) goToPage(target);
      });
    });
  }

  function initRowNavigation() {
    document.querySelectorAll("[data-recipe-row]").forEach(function (row) {
      row.addEventListener("click", function (e) {
        if (e.target.closest("a,button,input,select,textarea")) return;
        const id = row.getAttribute("data-recipe-id");
        if (id) {
          window.location.href = `/recipes/${encodeURIComponent(id)}`;
        }
      });
      row.style.cursor = "pointer";
    });
  }

  function markCurrentPageActive() {
    const currentPage = parseInt(qs("page", "1"), 10) || 1;
    document.querySelectorAll("[data-page-number]").forEach(function (btn) {
      const num = parseInt(btn.getAttribute("data-page-number"), 10);
      if (num === currentPage) {
        btn.classList.add("active");
        btn.setAttribute("aria-current", "page");
      } else {
        btn.classList.remove("active");
        btn.removeAttribute("aria-current");
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initPaginationControls();
    initRowNavigation();
    markCurrentPageActive();
  });

  window.RecipeList = {
    goToPage,
    buildUrl,
  };
})();
