// Run against a disposable demo DB: node scripts/ui-smoke.cjs [base-url] [output-dir]
// npm install --no-save playwright@1.62.1 @axe-core/playwright@4.10.2
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require(process.env.OMP_PLAYWRIGHT_MODULE || "playwright");
const base = process.argv[2] || "http://127.0.0.1:8765";
const out = process.argv[3] || "test-results";
(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({
    channel: process.env.OMP_BROWSER_CHANNEL || "chrome",
    headless: true,
  });
  const context = await browser.newContext({
    viewport: { width: 1366, height: 768 },
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(base);
  await page.waitForSelector(".product");
  assert.equal(await page.locator(".product").count(), 4);
  await page.screenshot({
    path: path.join(out, "desktop.png"),
    fullPage: true,
  });
  await page.locator("#search").fill("7700000000011");
  await page.locator("#search").press("Enter");
  assert.equal(await page.locator(".cart-row").count(), 1);
  await page.locator("#cash").fill("10000");
  await page.locator("#transfer").fill("18000");
  await page.locator("#checkout").click();
  await page.waitForFunction(() =>
    document
      .querySelector("#message")
      .textContent.includes("Venta simulada guardada"),
  );
  await page.waitForFunction(() => !document.querySelector("#print").disabled);
  assert.equal(await page.locator(".cart-row").count(), 0);
  const frame = page.frames().find((f) => f.parentFrame());
  await frame.waitForFunction(() => window.ompReceiptReady);
  const heightMm = await frame
    .locator("body")
    .getAttribute("data-receipt-height-mm");
  assert.ok(
    Number(heightMm) < 130,
    `One-item receipt too long: ${heightMm} mm`,
  );
  assert.ok(
    (await frame.locator("#receipt-page-size").textContent()).includes(
      `mm ${heightMm}mm`,
    ),
  );
  assert.ok(
    (await frame.locator("body").textContent()).includes("SIN VALIDEZ FISCAL"),
  );
  assert.ok(
    (await frame.locator("body").textContent()).includes("Taller Aurora"),
  );
  assert.equal(await frame.locator("img").count(), 1);
  await require("./receipt-layout.cjs")(page, out);
  await page.locator("#printer").selectOption("generic-80");
  await page.waitForFunction(() => !document.querySelector("#print").disabled);
  await page.screenshot({
    path: path.join(out, "receipt-80.png"),
    fullPage: true,
  });
  await page.locator("#brand").selectOption("tech");
  await page.waitForFunction(
    () =>
      document.querySelector("#brand-name").textContent === "Nexo Digital" &&
      document.querySelector(".product h3")?.textContent ===
        "Cargador compacto",
  );
  await page.locator("#user").selectOption("cashier");
  await page.waitForFunction(
    () => document.querySelector("#brand").options.length === 1,
  );
  assert.equal(await page.locator("#brand option").count(), 1);
  assert.equal(
    await page.evaluate(() => document.querySelector("#brand").value),
    "atelier",
  );
  const forbidden = await page.evaluate(
    async () =>
      (
        await fetch("/api/catalog?brand=tech", {
          headers: { "X-Demo-User": "cashier" },
        })
      ).status,
  );
  assert.equal(forbidden, 403);
  await page.locator("#scanner-code").fill("https://example.com/atelier");
  await page.locator("#scanner-code").press("Enter");
  assert.ok(
    (await page.locator("#scanner-result").textContent()).includes(
      "https://example.com/atelier",
    ),
  );
  assert.equal(page.url(), base + "/");
  await page.locator("#scanner-us").check();
  await page.locator("#scanner-expected").fill("https://example.com/atelier");
  await page.locator("#scanner-code").evaluate((input) => {
    const expected = "https://example.com/atelier";
    const punctuation = {
      ":": { key: "Ñ", code: "Semicolon", shiftKey: true },
      "/": { key: "-", code: "Slash" },
      ".": { key: ".", code: "Period" },
    };
    for (const character of expected) {
      const event = punctuation[character] || {
        key: character,
        code: `Key${character.toUpperCase()}`,
      };
      input.dispatchEvent(
        new KeyboardEvent("keydown", {
          ...event,
          bubbles: true,
          cancelable: true,
        }),
      );
    }
  });
  assert.equal(
    await page.locator("#scanner-code").inputValue(),
    "https://example.com/atelier",
  );
  await page.locator("#scanner-code").press("Enter");
  assert.ok(
    (await page.locator("#scanner-result").textContent()).includes(
      "Coincide exactamente",
    ),
  );
  await page.locator("#scanner-expected").fill("different-reference");
  assert.ok(
    (await page.locator("#scanner-result").textContent()).includes(
      "NO coincide",
    ),
  );
  await page.locator("#scanner-expected").fill(" https://example.com/atelier ");
  assert.ok(
    (await page.locator("#scanner-result").textContent()).includes(
      "Coincide exactamente",
    ),
  );
  await page.locator("#scanner-us").uncheck();
  await page.keyboard.press("Tab");
  assert.notEqual(
    await page.evaluate(() => document.activeElement.tagName),
    "BODY",
  );
  for (const width of [390, 768, 1366]) {
    await page.setViewportSize({ width, height: 844 });
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      `Overflow at ${width}px`,
    );
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: path.join(out, "mobile.png"), fullPage: true });
  if (process.env.OMP_AXE_MODULE) {
    const { default: AxeBuilder } = require(process.env.OMP_AXE_MODULE);
    const audit = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();
    fs.writeFileSync(
      path.join(out, "accessibility.json"),
      JSON.stringify(audit.violations, null, 2),
    );
    assert.deepEqual(
      audit.violations.map((v) => v.id),
      [],
    );
  }
  assert.deepEqual(errors, []);
  await browser.close();
  console.log(
    "PASS: checkout mixto, recibo/QR, perfiles, aislamiento API, teclado, 390/768/1366px y errores JS.",
  );
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
