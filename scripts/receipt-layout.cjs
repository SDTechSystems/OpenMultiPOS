const assert = require("node:assert/strict");
const path = require("node:path");
module.exports = async function receiptLayouts(page, out) {
  for (const profile of ["jaltech-jal58m", "generic-58", "generic-80"]) {
    await page.locator("#printer").selectOption(profile);
    await page.waitForFunction(
      () => !document.querySelector("#print").disabled,
    );
    const frame = page.frames().find((f) => f.parentFrame());
    await frame.waitForFunction(() => window.ompReceiptReady);
    const geometry = async () =>
      frame.evaluate(() => {
        const a = document.querySelector("article").getBoundingClientRect();
        const b = document.body.getBoundingClientRect();
        return {
          left: a.left - b.left,
          right: b.right - a.right,
          width: b.width,
          overflow: document.documentElement.scrollWidth > innerWidth,
        };
      });
    const screen = await geometry();
    await page.emulateMedia({ media: "print" });
    await frame.evaluate(() => window.dispatchEvent(new Event("beforeprint")));
    const print = await geometry();
    assert.ok(
      Math.abs(print.left - print.right) < 0.1,
      `${profile}: unequal print margins`,
    );
    assert.ok(
      Math.abs(screen.left - print.left) < 0.1,
      `${profile}: margin shift when printing`,
    );
    assert.ok(!print.overflow);
    const pdfPage = await page.context().newPage();
    const html = await frame.content();
    await pdfPage.goto(page.url());
    await pdfPage.waitForSelector(".product");
    await pdfPage.setContent(html);
    await pdfPage.waitForFunction(() => window.ompReceiptReady);
    await pdfPage.pdf({
      path: path.join(out, `${profile}-short.pdf`),
      preferCSSPageSize: true,
      printBackground: true,
    });
    await pdfPage.evaluate(async () => {
      const tbody = document.querySelector("tbody");
      tbody.replaceChildren();
      for (let i = 1; i <= 50; i++) {
        const row = document.createElement("tr");
        const name = document.createElement("td");
        const price = document.createElement("td");
        name.textContent = `ITEM-${String(i).padStart(3, "0")} NombreMuyLargoSinEspaciosParaProbarElAjuste`;
        price.textContent = "$ 123.456.789,99";
        row.append(name, price);
        tbody.append(row);
      }
      document.querySelector("footer small").textContent = "END-OF-RECEIPT";
      await window.ompPrepareReceipt();
      for (const cell of document.querySelectorAll("td")) {
        const range = document.createRange();
        range.selectNodeContents(cell);
        const text = range.getBoundingClientRect(),
          box = cell.getBoundingClientRect();
        if (text.left < box.left - 1 || text.right > box.right + 1)
          throw Error("Text outside column");
      }
    });
    await pdfPage.pdf({
      path: path.join(out, `${profile}-long.pdf`),
      preferCSSPageSize: true,
      printBackground: true,
    });
    await pdfPage.close();
    await page.emulateMedia({ media: null });
  }
};
