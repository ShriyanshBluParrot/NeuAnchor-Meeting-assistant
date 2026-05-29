const btn = document.getElementById("grant");
const out = document.getElementById("result");

btn.addEventListener("click", async () => {
  out.innerHTML = "";
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach((t) => t.stop());
    out.innerHTML =
      '<div class="ok">Granted! You can close this tab and use the extension.</div>';
  } catch (err) {
    out.innerHTML = `<div class="err">${err.message ||
      "Permission was not granted."} If no prompt appeared, see the instructions below.</div>`;
  }
});
