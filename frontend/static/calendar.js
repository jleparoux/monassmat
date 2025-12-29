(function () {
  const el = document.getElementById("calendar");
  if (!el) return;

  const contractId = el.dataset.contractId;
  let current = el.dataset.initialDate ? new Date(el.dataset.initialDate) : new Date();

  const monthTitle = document.getElementById("monthTitle");
  const summaryPeriod = document.getElementById("summaryPeriod");
  const prevBtn = document.getElementById("prevMonth");
  const nextBtn = document.getElementById("nextMonth");

  const modal = document.getElementById("dayModal");
  const modalTitle = document.getElementById("modalTitle");
  const modalContent = document.getElementById("modalContent");

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
    row.className = "grid";
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
    if (kind === "unpaid_leave") return ["cell--unpaid", "Sans solde"];
    return ["", ""];
  }

  function render(d, workdaysByDate) {
    el.innerHTML = "";

    const m = d.toLocaleDateString("fr-FR", { month: "long", year: "numeric" });
    const label = m.charAt(0).toUpperCase() + m.slice(1);
    monthTitle.textContent = label;
    if (summaryPeriod) summaryPeriod.textContent = label;

    dowHeaders(el);

    const grid = document.createElement("div");
    grid.className = "grid";

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

      if (statusLabel) {
        const meta = document.createElement("div");
        meta.className = "cell__meta";
        meta.textContent = statusLabel;
        cell.appendChild(meta);
      }

      if (wd) {
        const hours = document.createElement("div");
        hours.className = "cell__hours";
        hours.textContent = `${wd.hours}h`;
        cell.appendChild(hours);
      }

      cell.addEventListener("click", () => openDay(key));
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
    } catch (err) {
      if (modalContent) {
        modalContent.innerHTML = '<div class="empty">Impossible de charger le formulaire.</div>';
      }
      console.error(err);
    }
  }

  function refreshSummary() {
    const start = startOfMonth(current);
    const end = endOfMonth(current);
    const url = `/contracts/${contractId}/month_summary?start=${ymd(start)}&end=${ymd(end)}`;

    if (window.htmx && typeof window.htmx.ajax === "function") {
      window.htmx.ajax("GET", url, { target: "#monthSummary", swap: "innerHTML" });
      return;
    }

    fetchHtml(url)
      .then((html) => {
        const target = document.getElementById("monthSummary");
        if (target) target.innerHTML = html;
      })
      .catch((err) => {
        console.error(err);
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
  }

  prevBtn?.addEventListener("click", async () => {
    current = new Date(current.getFullYear(), current.getMonth() - 1, 1);
    await refresh();
  });

  nextBtn?.addEventListener("click", async () => {
    current = new Date(current.getFullYear(), current.getMonth() + 1, 1);
    await refresh();
  });

  modal?.addEventListener("click", (event) => {
    const target = event.target;
    if (target && target instanceof HTMLElement && target.dataset.close) {
      closeModal();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeModal();
  });

  document.body.addEventListener("workday:changed", async () => {
    closeModal();
    await refresh();
  });

  refresh().catch(console.error);
})();
