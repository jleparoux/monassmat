(function () {
  const el = document.getElementById("calendar");
  if (!el) return;

  const contractId = el.dataset.contractId;
  let current = el.dataset.initialDate ? new Date(el.dataset.initialDate) : new Date();

  const monthTitle = document.getElementById("monthTitle");
  const summaryPeriod = document.getElementById("summaryPeriod");
  const prevBtn = document.getElementById("prevMonth");
  const nextBtn = document.getElementById("nextMonth");
  const toggleSelectionBtn = document.getElementById("toggleSelection");
  const editSelectionBtn = document.getElementById("editSelection");
  const clearSelectionBtn = document.getElementById("clearSelection");
  const selectionCount = document.getElementById("selectionCount");

  const modal = document.getElementById("dayModal");
  const modalTitle = document.getElementById("modalTitle");
  const modalContent = document.getElementById("modalContent");

  let selectionMode = false;
  let selectedDays = new Set();
  let lastSelectedDay = null;

  function ymd(d) {
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd}`;
  }

  function startOfMonth(d) {
    return new Date(d.getFullYear(), d.getMonth(), 1);
  }

  function endOfMonth(d) {
    return new Date(d.getFullYear(), d.getMonth() + 1, 0);
  }

  function dowHeaders(container) {
    const names = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];
    const row = document.createElement("div");
    row.className = "grid grid--header";
    for (const n of names) {
      const c = document.createElement("div");
      c.className = "dow";
      c.textContent = n;
      row.appendChild(c);
    }
    container.appendChild(row);
  }

  function jsDowToMonFirst(jsDow) {
    return (jsDow + 6) % 7;
  }

  async function fetchMonthData(d) {
    const start = startOfMonth(d);
    const end = endOfMonth(d);
    const url = `/api/contracts/${contractId}/workdays?start=${ymd(start)}&end=${ymd(end)}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error("Failed to fetch workdays");
    return await res.json();
  }

  async function fetchHtml(url) {
    const res = await fetch(url, { headers: { "X-Requested-With": "fetch" } });
    if (!res.ok) throw new Error("Failed to fetch HTML");
    return await res.text();
  }

  function kindBadge(kind) {
    if (kind === "normal") return ["cell--work", "Travaille"];
    if (kind === "absence") return ["cell--absence", "Absence"];
    if (kind === "assmat_leave") return ["cell--assmat", "Conge assmat"];
    if (kind === "unpaid_leave") return ["cell--unpaid", "Sans solde"];
    if (kind === "holiday") return ["cell--holiday", "Jour ferie"];
    return ["", ""];
  }

  function updateSelectionUI() {
    const count = selectedDays.size;
    if (selectionCount) {
      if (count === 0) {
        selectionCount.textContent = "Aucun jour selectionne";
      } else if (count === 1) {
        selectionCount.textContent = "1 jour selectionne";
      } else {
        selectionCount.textContent = `${count} jours selectionnes`;
      }
    }

    if (editSelectionBtn) editSelectionBtn.disabled = count === 0;
    if (clearSelectionBtn) clearSelectionBtn.disabled = count === 0;
    if (toggleSelectionBtn) {
      toggleSelectionBtn.textContent = selectionMode
        ? "Quitter la selection"
        : "Selection multiple";
    }
    if (el) el.classList.toggle("calendar--selecting", selectionMode);
  }

  function applySelectionClasses() {
    const cells = el.querySelectorAll(".cell[data-day]");
    cells.forEach((cell) => {
      const day = cell.dataset.day;
      if (!day) return;
      cell.classList.toggle("cell--selected", selectedDays.has(day));
    });
  }

  function clearSelection() {
    selectedDays = new Set();
    lastSelectedDay = null;
    applySelectionClasses();
    updateSelectionUI();
  }

  function dateFromKey(key) {
    const [y, m, d] = key.split("-").map(Number);
    return new Date(y, m - 1, d);
  }

  function isSameMonth(a, b) {
    return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth();
  }

  function selectRange(fromKey, toKey) {
    const from = dateFromKey(fromKey);
    const to = dateFromKey(toKey);
    if (!isSameMonth(from, current) || !isSameMonth(to, current)) {
      selectedDays.add(toKey);
      return;
    }

    const start = from <= to ? from : to;
    const end = from <= to ? to : from;
    for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
      selectedDays.add(ymd(d));
    }
  }

  function toggleSelection(dayKey, useRange) {
    if (useRange && lastSelectedDay) {
      selectRange(lastSelectedDay, dayKey);
    } else if (selectedDays.has(dayKey)) {
      selectedDays.delete(dayKey);
    } else {
      selectedDays.add(dayKey);
    }
    lastSelectedDay = dayKey;
    applySelectionClasses();
    updateSelectionUI();
  }

  function render(d, workdaysByDate) {
    el.innerHTML = "";

    const m = d.toLocaleDateString("fr-FR", { month: "long", year: "numeric" });
    const label = m.charAt(0).toUpperCase() + m.slice(1);
    monthTitle.textContent = label;
    if (summaryPeriod) summaryPeriod.textContent = label;

    dowHeaders(el);

    const grid = document.createElement("div");
    grid.className = "grid grid--days";

    const first = startOfMonth(d);
    const last = endOfMonth(d);
    const firstOffset = jsDowToMonFirst(first.getDay());

    for (let i = 0; i < firstOffset; i++) {
      const cell = document.createElement("div");
      cell.className = "cell cell--muted";
      grid.appendChild(cell);
    }

    for (let day = 1; day <= last.getDate(); day++) {
      const dt = new Date(d.getFullYear(), d.getMonth(), day);
      const key = ymd(dt);
      const wd = workdaysByDate.get(key);
      const isToday = dt.toDateString() === new Date().toDateString();
      const isWeekend = dt.getDay() === 0 || dt.getDay() === 6;

      const cell = document.createElement("div");
      const classes = ["cell"];
      if (isToday) classes.push("cell--today");
      if (isWeekend) classes.push("cell--weekend");

      let statusLabel = "";
      if (wd) {
        const [kindClass, kindLabel] = kindBadge(wd.kind);
        if (kindClass) classes.push(kindClass);
        statusLabel = kindLabel;
      }

      cell.className = classes.join(" ");
      cell.dataset.day = key;

      const num = document.createElement("div");
      num.className = "daynum";
      num.textContent = String(day);
      cell.appendChild(num);

      if (wd && (wd.fee_meal || wd.fee_maintenance)) {
        const indicator = document.createElement("div");
        indicator.className = "fee-indicator";
        if (wd.fee_meal) {
          const meal = document.createElement("div");
          meal.className = "fee-dot fee-dot--meal";
          indicator.appendChild(meal);
        }
        if (wd.fee_maintenance) {
          const maintenance = document.createElement("div");
          maintenance.className = "fee-dot fee-dot--maintenance";
          indicator.appendChild(maintenance);
        }
        cell.appendChild(indicator);
      }

      if (statusLabel) {
        const meta = document.createElement("div");
        meta.className = "cell__meta";
        meta.textContent = statusLabel;
        cell.appendChild(meta);
      }

      if (wd && wd.start_time && wd.end_time) {
        const timeRange = document.createElement("div");
        timeRange.className = "cell__time";
        timeRange.textContent = `${wd.start_time} - ${wd.end_time}`;
        cell.appendChild(timeRange);
      }

      if (wd && wd.hours && wd.hours > 0) {
        const hours = document.createElement("div");
        hours.className = "cell__hours";
        const hoursValue = Number(wd.hours);
        hours.textContent = `${hoursValue.toFixed(2)}h`;
        cell.appendChild(hours);
      }

      cell.addEventListener("click", (event) => {
        if (selectionMode) {
          toggleSelection(key, event.shiftKey);
          return;
        }
        openDay(key);
      });
      if (selectedDays.has(key)) {
        cell.classList.add("cell--selected");
      }
      grid.appendChild(cell);
    }

    el.appendChild(grid);
  }

  function openModal() {
    if (!modal) return;
    modal.classList.add("is-open");
    modal.setAttribute("aria-hidden", "false");
  }

  function closeModal() {
    if (!modal) return;
    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
  }

  function parseTime(value) {
    if (!value) return null;
    const [hh, mm] = value.split(":").map(Number);
    if (!Number.isFinite(hh) || !Number.isFinite(mm)) return null;
    return hh * 60 + mm;
  }

  function formatHours(minutes) {
    const hours = minutes / 60;
    return `${hours.toFixed(2).replace(".00", "")}h`;
  }

  function updatePreview(container) {
    const preview = container.querySelector("#dayPreviewValue");
    if (!preview) return;
    const startInput = container.querySelector("input[name='start_time']");
    const endInput = container.querySelector("input[name='end_time']");
    if (!startInput || !endInput) return;

    const startValue = parseTime(startInput.value);
    const endValue = parseTime(endInput.value);

    if (startValue !== null && endValue !== null && endValue > startValue) {
      const minutes = endValue - startValue;
      preview.textContent = `${startInput.value} - ${endInput.value} (${formatHours(minutes)})`;
      return;
    }

    if (startInput.value || endInput.value) {
      preview.textContent = `${startInput.value || "--:--"} - ${endInput.value || "--:--"}`;
      return;
    }

    preview.textContent = "0 h";
  }

  async function openDay(day) {
    if (modalTitle) modalTitle.textContent = `Jour ${day}`;
    if (modalContent) {
      modalContent.innerHTML = '<div class="empty">Chargement…</div>';
    }
    openModal();

    const url = `/contracts/${contractId}/day_form?day=${day}`;
    if (window.htmx && typeof window.htmx.ajax === "function") {
      window.htmx.ajax("GET", url, { target: "#modalContent", swap: "innerHTML" });
      return;
    }

    try {
      const html = await fetchHtml(url);
      if (modalContent) modalContent.innerHTML = html;
      updatePreview(modalContent);
    } catch (err) {
      if (modalContent) {
        modalContent.innerHTML = '<div class="empty">Impossible de charger le formulaire.</div>';
      }
      console.error(err);
    }
  }

  async function openBulkForm() {
    const days = Array.from(selectedDays).sort();
    if (days.length === 0) return;
    const query = encodeURIComponent(days.join(","));
    const url = `/contracts/${contractId}/bulk_form?days=${query}`;

    if (modalTitle) {
      modalTitle.textContent = `Selection (${days.length} jours)`;
    }
    if (modalContent) {
      modalContent.innerHTML = '<div class="empty">Chargement…</div>';
    }
    openModal();

    if (window.htmx && typeof window.htmx.ajax === "function") {
      window.htmx.ajax("GET", url, { target: "#modalContent", swap: "innerHTML" });
      return;
    }

    try {
      const html = await fetchHtml(url);
      if (modalContent) modalContent.innerHTML = html;
    } catch (err) {
      if (modalContent) {
        modalContent.innerHTML = '<div class="empty">Impossible de charger la selection.</div>';
      }
      console.error(err);
    }
  }

  function showSummaryError() {
    const target = document.getElementById("monthSummary");
    if (target) {
      target.innerHTML = '<div class="empty">Synthese indisponible pour ce mois.</div>';
    }
  }

  function refreshSummary() {
    const start = startOfMonth(current);
    const end = endOfMonth(current);
    const url = `/contracts/${contractId}/month_summary?start=${ymd(start)}&end=${ymd(end)}`;

    fetchHtml(url)
      .then((html) => {
        const target = document.getElementById("monthSummary");
        if (target) target.innerHTML = html;
      })
      .catch((err) => {
        console.error(err);
        showSummaryError();
      });
  }

  async function refresh() {
    let payload = { items: [] };
    try {
      payload = await fetchMonthData(current);
    } catch (err) {
      console.error(err);
    }
    const byDate = new Map(payload.items.map(x => [x.date, x]));
    render(current, byDate);
    refreshSummary();
    applySelectionClasses();
    updateSelectionUI();
  }

  prevBtn?.addEventListener("click", async () => {
    current = new Date(current.getFullYear(), current.getMonth() - 1, 1);
    clearSelection();
    await refresh();
  });

  nextBtn?.addEventListener("click", async () => {
    current = new Date(current.getFullYear(), current.getMonth() + 1, 1);
    clearSelection();
    await refresh();
  });

  toggleSelectionBtn?.addEventListener("click", () => {
    selectionMode = !selectionMode;
    if (!selectionMode) {
      clearSelection();
    }
    updateSelectionUI();
  });

  clearSelectionBtn?.addEventListener("click", () => {
    clearSelection();
  });

  editSelectionBtn?.addEventListener("click", () => {
    openBulkForm();
  });

  modal?.addEventListener("click", (event) => {
    const target = event.target;
    if (target && target instanceof HTMLElement && target.dataset.close) {
      closeModal();
    }
  });

  modalContent?.addEventListener("input", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (
      target.matches("input[name='start_time']") ||
      target.matches("input[name='end_time']")
    ) {
      updatePreview(modalContent);
    }
  });

  document.addEventListener("htmx:afterSwap", (event) => {
    const target = event.target;
    if (target && target.id === "modalContent") {
      updatePreview(target);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeModal();
  });

  document.body.addEventListener("workday:changed", async () => {
    closeModal();
    selectionMode = false;
    clearSelection();
    await refresh();
  });

  refresh().catch(console.error);
  updateSelectionUI();
})();
