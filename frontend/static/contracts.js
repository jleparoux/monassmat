(function () {
  const cards = Array.from(document.querySelectorAll(".contract-card"));
  if (cards.length === 0) return;

  const filterButtons = Array.from(document.querySelectorAll("[data-filter]"));
  const sortButtons = Array.from(document.querySelectorAll("[data-sort]"));
  const quickActions = Array.from(document.querySelectorAll("[data-quick-action]"));
  const grid = document.querySelector(".contracts-grid");

  function setActiveButton(buttons, active) {
    buttons.forEach((btn) => btn.classList.toggle("is-active", btn === active));
  }

  function activeCards() {
    return cards.filter((card) => !card.classList.contains("is-hidden"));
  }

  function updateQuickActions() {
    const active = activeCards();
    const target = active.length > 0 ? active[0] : cards[0];
    if (!target) return;
    const id = target.dataset.id;
    if (!id) return;
    quickActions.forEach((link) => {
      const action = link.dataset.quickAction;
      if (action === "calendar") link.href = `/contracts/${id}/calendar`;
      if (action === "year") link.href = `/contracts/${id}/summary/year`;
      if (action === "settings") link.href = `/contracts/${id}/settings`;
    });
  }

  function applyFilter(filter) {
    cards.forEach((card) => {
      const status = card.dataset.status || "active";
      const isMatch = filter === "all" || status === filter;
      card.classList.toggle("is-hidden", !isMatch);
    });
    updateQuickActions();
  }

  function applySort(sortKey) {
    const sorted = [...cards].sort((a, b) => {
      if (sortKey === "salary") {
        return Number(b.dataset.salary || 0) - Number(a.dataset.salary || 0);
      }
      if (sortKey === "hours") {
        return Number(b.dataset.hours || 0) - Number(a.dataset.hours || 0);
      }
      return Number(a.dataset.id || 0) - Number(b.dataset.id || 0);
    });
    sorted.forEach((card) => grid.appendChild(card));
  }

  filterButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      setActiveButton(filterButtons, btn);
      applyFilter(btn.dataset.filter);
    });
  });

  sortButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      setActiveButton(sortButtons, btn);
      applySort(btn.dataset.sort);
    });
  });

  applyFilter("all");
  applySort("id");
})();
