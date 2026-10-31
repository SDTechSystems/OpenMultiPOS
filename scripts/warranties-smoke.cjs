// Fictional warranty flow. Fixture credentials arrive through stdin only.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");
const { AxeBuilder } = require("@axe-core/playwright");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
(async () => {
  const browser = await chromium.launch({
    channel: process.env.OMP_BROWSER_CHANNEL || "chrome",
    headless: true,
  });
  try {
    const context = await browser.newContext({
      viewport: { width: 1366, height: 900 },
      extraHTTPHeaders: { "X-Frappe-Site-Name": input.site },
    });
    assert.equal(
      (
        await context.request.post(input.base + "/api/method/login", {
          data: { usr: input.user, pwd: input.password },
        })
      ).status(),
      200,
    );
    const page = await context.newPage(),
      errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    const ready = () =>
      page.waitForFunction(
        () =>
          window.OMPWorkspace?.state.boot && !window.OMPWorkspace.state.busy,
      );
    await page.goto(input.base + "/omp#warranties");
    await ready();
    await page.evaluate(async (brand) => {
      window.OMPWorkspace.active(brand);
      await window.OMPWorkspace.run(() => window.OMPWarranties.enter());
    }, input.brand);
    await ready();
    async function prepare(text) {
      await page.locator("#warranty-invoice").fill(input.invoice);
      await page
        .getByRole("button", { name: "Consultar venta", exact: true })
        .click();
      await ready();
      await page.locator("#warranty-complaint").fill(text);
    }
    await prepare("Reclamación ficticia: revisar funcionamiento.");
    assert.equal(
      await page
        .locator("#dialog-form")
        .evaluate((form) => form.checkValidity()),
      true,
      "The original sale item must be selected by default",
    );
    await page.route(
      "**/api/method/open_multi_pos.warranties.create",
      async (route) => {
        assert.equal((await route.fetch()).status(), 200);
        await route.abort("failed");
      },
      { times: 1 },
    );
    await page.locator("#dialog-save").focus();
    await page.keyboard.press("Enter");
    await ready();
    await page.locator("#dialog-cancel").click();
    await page.reload();
    await ready();
    assert.equal(
      await page.locator("#notice").textContent(),
      "",
      "Recovery must not fail silently",
    );
    assert.match(
      await page.locator("#warranty-recovery-text").textContent(),
      /registrada/,
    );
    assert.match(
      await page.locator("#warranty-detail").textContent(),
      /revisar funcionamiento/,
    );
    await page
      .getByRole("button", { name: "Actualizar seguimiento", exact: true })
      .click();
    await ready();
    await page.locator("#warranty-status").selectOption("Closed");
    await page
      .locator("#warranty-notes")
      .fill("Revisión ficticia completada sin cobros.");
    await page.locator("#dialog-save").click();
    await ready();
    assert.match(
      await page.locator("#warranty-detail").textContent(),
      /Cerrada/,
    );
    assert.match(
      await page.locator("#warranty-detail").textContent(),
      /sin cobros/,
    );
    const axe = await new AxeBuilder({ page })
      .include("#view-warranties")
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();
    assert.deepEqual(axe.violations, []);
    const out = path.resolve(__dirname, "../test-results/warranties");
    fs.mkdirSync(out, { recursive: true });
    await page.screenshot({
      path: path.join(out, "desktop.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    );
    await page.screenshot({
      path: path.join(out, "mobile.png"),
      fullPage: true,
    });
    await page.locator("#warranty-next").click();
    await ready();
    await prepare("Intento ficticio pendiente.");
    await page.route(
      "**/api/method/open_multi_pos.warranties.create",
      (route) => route.abort("failed"),
      { times: 1 },
    );
    await page.locator("#dialog-save").click();
    await ready();
    await page.locator("#dialog-cancel").click();
    await page.reload();
    await ready();
    assert.match(
      await page.locator("#warranty-recovery-text").textContent(),
      /pendiente/,
    );
    await page.route(
      "**/api/method/open_multi_pos.warranties.abandon",
      async (route) => {
        assert.equal((await route.fetch()).status(), 200);
        await route.abort("failed");
      },
      { times: 1 },
    );
    await page.locator("#warranty-abandon").click();
    await ready();
    await page.reload();
    await ready();
    assert.match(
      await page.locator("#warranty-recovery-text").textContent(),
      /abandonado/,
    );
    await page.locator("#warranty-next").click();
    await ready();
    assert.equal(await page.locator("#warranty-create").isVisible(), true);
    assert.deepEqual(errors, []);
    console.log(
      JSON.stringify({
        createdRecovered: true,
        abandonmentRecovered: true,
        closed: true,
        keyboard: true,
        mobile: true,
        axeViolations: 0,
      }),
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
