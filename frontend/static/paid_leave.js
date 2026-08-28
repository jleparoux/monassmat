(function () {
  const modeSelect = document.getElementById("paidLeaveBasisMode");
  if (!modeSelect) return;

  const fieldGroups = document.querySelectorAll("[data-basis-fields]");

  function syncBasisFields() {
    fieldGroups.forEach((group) => {
      const active = group.dataset.basisFields === modeSelect.value;
      group.hidden = !active;
      group.querySelectorAll("input, select, textarea").forEach((field) => {
        field.disabled = !active;
      });
    });
  }

  modeSelect.addEventListener("change", syncBasisFields);
  syncBasisFields();
})();
