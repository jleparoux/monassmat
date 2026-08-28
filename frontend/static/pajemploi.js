(function () {
  async function copyText(value) {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(value);
      return;
    }

    var textarea = document.createElement("textarea");
    textarea.value = value;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  }

  document.querySelectorAll("[data-copy-value]").forEach(function (button) {
    button.addEventListener("click", async function () {
      var initialLabel = button.textContent;
      try {
        await copyText(button.dataset.copyValue);
        button.textContent = "Copié";
        button.classList.add("is-copied");
      } catch (error) {
        button.textContent = "Échec";
      }
      window.setTimeout(function () {
        button.textContent = initialLabel;
        button.classList.remove("is-copied");
      }, 1400);
    });
  });
})();
