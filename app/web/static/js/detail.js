/**
 * Recipe detail view enhancements: image fallback, owner-only controls,
 * and wiring of Edit / Delete actions.
 */
(function () {
  "use strict";

  function initImageFallback() {
    document.querySelectorAll("[data-recipe-image]").forEach(function (img) {
      img.addEventListener("error", function () {
        img.style.display = "none";
        const placeholder = document.querySelector("[data-recipe-image-placeholder]");
        if (placeholder) placeholder.style.display = "block";
      });
    });
  }

  function formatDates() {
    document.querySelectorAll("[data-iso-date]").forEach(function (el) {
      const raw = el.getAttribute("data-iso-date");
      if (!raw) return;
      const d = new Date(raw);
      if (!Number.isNaN(d.getTime())) {
        el.textContent = d.toLocaleString();
      }
    });
  }

  function initEditButton() {
    const editBtn = document.querySelector("[data-edit-recipe]");
    if (!editBtn) return;
    editBtn.addEventListener("click", function () {
      const id = editBtn.getAttribute("data-recipe-id");
      if (id) window.location.href = `/recipes/${encodeURIComponent(id)}/edit`;
    });
  }

  function initDeleteButton() {
    const deleteBtn = document.querySelector("[data-delete-recipe]");
    if (!deleteBtn) return;
    deleteBtn.addEventListener("click", function () {
      const id = deleteBtn.getAttribute("data-recipe-id");
      if (id) window.location.href = `/recipes/${encodeURIComponent(id)}/delete-confirm`;
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initImageFallback();
    formatDates();
    initEditButton();
    initDeleteButton();
  });
})();
