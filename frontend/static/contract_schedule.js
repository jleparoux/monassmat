(function () {
  document.querySelectorAll("[data-weekly-schedule]").forEach(function (section) {
    var form = section.closest("form");
    var weeklyHours = form.querySelector("[data-weekly-hours]");
    var dayInputs = Array.from(section.querySelectorAll("[data-schedule-hours]"));
    var totalOutput = section.querySelector("[data-schedule-total]");

    function formatHours(value) {
      return value.toLocaleString("fr-FR", { maximumFractionDigits: 2 });
    }

    function updateTotal() {
      var hasSchedule = dayInputs.some(function (input) { return input.value !== ""; });
      if (!hasSchedule) {
        totalOutput.textContent = "Non renseigne";
        section.classList.remove("is-mismatch");
        return;
      }

      var total = dayInputs.reduce(function (sum, input) {
        return sum + (Number(input.value) || 0);
      }, 0);
      var expected = Number(weeklyHours.value) || 0;
      totalOutput.textContent = formatHours(total) + " h / " + formatHours(expected) + " h";
      section.classList.toggle("is-mismatch", Math.abs(total - expected) > 0.01);
    }

    dayInputs.forEach(function (input) { input.addEventListener("input", updateTotal); });
    weeklyHours.addEventListener("input", updateTotal);
    updateTotal();
  });
})();
