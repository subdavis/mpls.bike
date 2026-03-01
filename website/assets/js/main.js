function initShareButton() {
  document.getElementById("share-btn").addEventListener("click", function () {
    if (navigator.share) {
      navigator.share({ title: document.title, url: globalThis.location.href });
    } else {
      navigator.clipboard.writeText(globalThis.location.href).then(function () {
        alert("Link copied to clipboard!");
      });
    }
  });
}

function initRelativeTimeHeaders() {
  let headers = document.querySelectorAll("[data-date]");
  if (!headers.length) return;
  let now = new Date();
  let today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  for (let i = 0; i < 2 && i < headers.length; i++) {
    let parts = headers[i].dataset.date.split("-");
    let d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    let days = Math.round((d - today) / 86400000);
    if (days === 0) headers[i].textContent = "Today";
    else if (days === 1) headers[i].textContent = "Tomorrow";
  }
}

initShareButton();
initRelativeTimeHeaders();
