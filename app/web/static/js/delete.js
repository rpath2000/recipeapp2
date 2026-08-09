/**
 * Delete confirmation modal wiring: opens a confirm dialog before issuing
 * the DELETE (POST /recipes/{id}/delete) call, and closes cleanly on cancel
 * without making any network request.
 */
(function () {
  "use strict";

  function openModal(modal) {
    if (!modal) return;
    modal.classList.add("open");
    modal.setAttribute("aria-hidden", "false");
    const focusTarget = modal.querySelector("[data-modal-confirm]");
    if (focusTarget) focusTarget.focus();
  }

  function closeModal(modal) {
    if (!modal) return;
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden", "true");
  }

  function initDeleteTriggers() {
    document.querySelectorAll("[data-delete-trigger]").forEach(function (trigger) {
      trigger.addEventListener("click", function (e) {
        e.preventDefault();
        const modalId = trigger.getAttribute("data-modal-target");
        const modal = modalId
          ? document.getElementById(modalId)
          : document.querySelector("[data-delete-modal]");
        openModal(modal);
      });
    });
  }

  function initModalCancel() {
    document.querySelectorAll("[data-modal-cancel]").forEach(function (cancelBtn) {
      cancelBtn.addEventListener("click", function (e) {
        e.preventDefault();
        const modal = cancelBtn.closest("[data-delete-modal]") || cancelBtn.closest(".modal");
        closeModal(modal);
      });
    });

    document.querySelectorAll("[data-delete-modal]").forEach(function (modal) {
      modal.addEventListener("click", function (e) {
        if (e.target === modal) {
          closeModal(modal);
        }
      });
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        document.querySelectorAll("[data-delete-modal].open").forEach(closeModal);
      }
    });
  }

  function initModalConfirm() {
    document.querySelectorAll("[data-modal-confirm]").forEach(function (confirmBtn) {
      confirmBtn.addEventListener("click", function (e) {
        const recipeId = confirmBtn.getAttribute("data-recipe-id");
        const form = confirmBtn.closest("form");

        if (form) {
          return;
        }

        if (!recipeId) return;

        e.preventDefault();
        confirmBtn.disabled = true;
        confirmBtn.textContent = "Deleting...";

        fetch(`/recipes/${encodeURIComponent(recipeId)}/delete`, {
          method: "POST",
          headers: { "X-Requested-With": "XMLHttpRequest" },
        })
          .then(function (resp) {
            if (resp.redirected) {
              window.location.href = resp.url;
              return;
            }
            if (resp.ok) {
              window.location.href = "/recipes";
            } else {
              throw new Error("Delete failed");
            }
          })
          .catch(function () {
            confirmBtn.disabled = false;
            confirmBtn.textContent = "Confirm";
            const errorEl = document.querySelector("[data-delete-error]");
            if (errorEl) {
              errorEl.textContent = "Unable to delete recipe. Please try again.";
            }
          });
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initDeleteTriggers();
    initModalCancel();
    initModalConfirm();
  });

  window.RecipeDelete = {
    openModal,
    closeModal,
  };
})();
