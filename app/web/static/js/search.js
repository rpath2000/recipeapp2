/**
 * Search bar and category filter controls for the recipe list page.
 * Debounces text input, supports multi-select category filters, and
 * updates the URL / reloads results via GET /recipes/search.
 */
(function () {
  "use strict";

  const DEBOUNCE_MS = 350;

  function debounce(fn, delay) {
    let timer = null;
    return function (...args) {
      clearTimeout(timer);
      timer = setTimeout(function () {
        fn.apply(null, args);
      }, delay);
    };
  }

  function getSelectedCategories(container) {
    const checkboxes = container.querySelectorAll('[data-category-checkbox]:checked');
    return Array.from(checkboxes).map(function (cb) {
      return cb.value;
    });
  }

  function buildSearchUrl(query, categories) {
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (categories && categories.length === 1) {
      params.set("category", categories[0]);
    } else if (categories && categories.length > 1) {
      categories.forEach(function (c) {
        params.append("category", c);
      });
    }
    params.set("page", "1");
    return `/recipes/search?${params.toString()}`;
  }

  function performSearch(query, categories) {
    const url = buildSearchUrl(query, categories);
    const resultsContainer = document.querySelector("[data-search-results]");

    if (!resultsContainer) {
      window.location.href = url;
      return;
    }

    resultsContainer.setAttribute("aria-busy", "true");

    fetch(url, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (resp) {
        if (!resp.ok) throw new Error("Search request failed");
        return resp.text();
      })
      .then(function (html) {
        resultsContainer.innerHTML = html;
        resultsContainer.removeAttribute("aria-busy");
        window.history.replaceState(null, "", `/recipes?${url.split("?")[1] || ""}`);
      })
      .catch(function () {
        resultsContainer.removeAttribute("aria-busy");
        resultsContainer.innerHTML =
          '<p class="no-results" role="alert">Unable to load results. Please try again.</p>';
      });
  }

  function initSearchBar() {
    const searchInput = document.querySelector("[data-search-input]");
    const categoryContainer = document.querySelector("[data-category-filters]");

    if (!searchInput && !categoryContainer) return;

    const debouncedSearch = debounce(function () {
      const query = searchInput ? searchInput.value.trim() : "";
      const categories = categoryContainer ? getSelectedCategories(categoryContainer) : [];
      performSearch(query, categories);
    }, DEBOUNCE_MS);

    if (searchInput) {
      searchInput.addEventListener("input", debouncedSearch);
      searchInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          e.preventDefault();
          const query = searchInput.value.trim();
          const categories = categoryContainer ? getSelectedCategories(categoryContainer) : [];
          performSearch(query, categories);
        }
      });
    }

    if (categoryContainer) {
      categoryContainer.querySelectorAll('[data-category-checkbox]').forEach(function (cb) {
        cb.addEventListener("change", function () {
          const query = searchInput ? searchInput.value.trim() : "";
          const categories = getSelectedCategories(categoryContainer);
          performSearch(query, categories);
        });
      });
    }

    const categorySelect = document.querySelector("[data-category-select]");
    if (categorySelect) {
      categorySelect.addEventListener("change", function () {
        const query = searchInput ? searchInput.value.trim() : "";
        const value = categorySelect.value;
        performSearch(query, value ? [value] : []);
      });
    }
  }

  document.addEventListener("DOMContentLoaded", initSearchBar);

  window.RecipeSearch = {
    buildSearchUrl,
    performSearch,
  };
})();
