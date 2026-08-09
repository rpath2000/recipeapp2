/**
 * Recipe create/edit form: client-side validation, category dropdown with
 * free-form entry, and image upload preview. Server errors (rendered inline
 * by Jinja) are respected and not clobbered until the user resubmits.
 */
(function () {
  "use strict";

  const REQUIRED_FIELDS = [
    { name: "name", message: "Recipe Name is required" },
    { name: "description", message: "Description is required" },
    { name: "ingredients", message: "Ingredients are required" },
    { name: "instructions", message: "Instructions are required" },
  ];

  function findForm() {
    return document.querySelector("[data-recipe-form]");
  }

  function clearErrors(form) {
    form.querySelectorAll("[data-error-for]").forEach(function (el) {
      el.textContent = "";
    });
    form.querySelectorAll(".field-error").forEach(function (el) {
      el.classList.remove("field-error");
    });
  }

  function showError(form, fieldName, message) {
    const errorEl = form.querySelector(`[data-error-for="${fieldName}"]`);
    if (errorEl) {
      errorEl.textContent = message;
    }
    const input = form.querySelector(`[name="${fieldName}"]`);
    if (input) {
      input.classList.add("field-error");
      input.setAttribute("aria-invalid", "true");
    }
  }

  function getCategoryValue(form) {
    const select = form.querySelector('[name="category"]');
    const custom = form.querySelector('[name="custom_category"]');
    if (custom && custom.value && custom.value.trim()) {
      return custom.value.trim();
    }
    return select ? select.value : "";
  }

  function validate(form) {
    let valid = true;
    clearErrors(form);

    REQUIRED_FIELDS.forEach(function (field) {
      const input = form.querySelector(`[name="${field.name}"]`);
      const value = input ? input.value.trim() : "";
      if (!value) {
        showError(form, field.name, field.message);
        valid = false;
      }
    });

    const category = getCategoryValue(form);
    if (!category) {
      showError(form, "category", "Category is required");
      valid = false;
    }

    return valid;
  }

  function initCategoryDropdown(form) {
    const select = form.querySelector('[name="category"]');
    const customWrapper = form.querySelector("[data-custom-category-wrapper]");
    const customInput = form.querySelector('[name="custom_category"]');
    if (!select) return;

    function toggleCustom() {
      const isCustom = select.value === "__custom__" || select.value === "";
      if (customWrapper) {
        customWrapper.style.display = isCustom ? "block" : "none";
      }
    }

    select.addEventListener("change", toggleCustom);
    toggleCustom();

    if (customInput) {
      customInput.addEventListener("input", function () {
        if (customInput.value.trim()) {
          const errorEl = form.querySelector('[data-error-for="category"]');
          if (errorEl) errorEl.textContent = "";
          customInput.classList.remove("field-error");
        }
      });
    }
  }

  function initImagePreview(form) {
    const fileInput = form.querySelector('[name="image"]');
    const preview = form.querySelector("[data-image-preview]");
    if (!fileInput || !preview) return;

    fileInput.addEventListener("change", function () {
      const file = fileInput.files && fileInput.files[0];
      if (!file) {
        preview.style.display = "none";
        return;
      }
      if (!file.type.startsWith("image/")) {
        preview.style.display = "none";
        return;
      }
      const reader = new FileReader();
      reader.onload = function (e) {
        preview.src = e.target.result;
        preview.style.display = "block";
      };
      reader.readAsDataURL(file);
    });
  }

  function initSubmitGuard(form) {
    form.addEventListener("submit", function (e) {
      if (!validate(form)) {
        e.preventDefault();
        const firstError = form.querySelector(".field-error");
        if (firstError) firstError.focus();
        return false;
      }

      const submitBtn = form.querySelector('[type="submit"]');
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.setAttribute("data-original-text", submitBtn.textContent);
        submitBtn.textContent = "Saving...";
      }
    });
  }

  function initLiveValidation(form) {
    REQUIRED_FIELDS.concat([{ name: "category" }]).forEach(function (field) {
      const input = form.querySelector(`[name="${field.name}"]`);
      if (!input) return;
      input.addEventListener("blur", function () {
        if (input.value.trim()) {
          const errorEl = form.querySelector(`[data-error-for="${field.name}"]`);
          if (errorEl) errorEl.textContent = "";
          input.classList.remove("field-error");
        }
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    const form = findForm();
    if (!form) return;

    initCategoryDropdown(form);
    initImagePreview(form);
    initSubmitGuard(form);
    initLiveValidation(form);
  });

  window.RecipeForm = {
    validate,
    clearErrors,
    showError,
  };
})();
