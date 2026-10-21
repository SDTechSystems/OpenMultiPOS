"use strict";
// Explicit finite page height: `size: 58mm auto` is invalid CSS and can make
// thermal drivers fall back to their longest (e.g. 3276 mm) paper setting.
function sizeReceiptPage() {
  const article = document.querySelector("article");
  const width = Number(document.body.dataset.paperMm);
  const height = Math.ceil(
    (article.getBoundingClientRect().height * 25.4) / 96 + 1,
  );
  if (!Number.isFinite(width) || width < 30 || width > 120) return;
  let style = document.getElementById("receipt-page-size");
  if (!style) {
    style = document.createElement("style");
    style.id = "receipt-page-size";
    document.head.append(style);
  }
  // Large carts paginate; never request metres of paper as a single page.
  const pageHeight = Math.max(40, Math.min(height, 280));
  style.textContent = `@page { size: ${width}mm ${pageHeight}mm; margin: 0; }`;
  document.body.dataset.printPageHeightMm = String(pageHeight);
  document.body.dataset.receiptHeightMm = String(height);
  window.ompReceiptReady = true;
}
window.ompPrepareReceipt = async function () {
  await document.fonts.ready;
  await Promise.all(
    [...document.images].map((image) => image.decode().catch(() => {})),
  );
  sizeReceiptPage();
};
window.addEventListener("beforeprint", sizeReceiptPage);
window.ompPrepareReceipt();
