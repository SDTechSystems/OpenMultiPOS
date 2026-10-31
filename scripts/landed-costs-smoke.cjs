// Fictional native LCV browser flow. Credentials arrive only via stdin.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { chromium } = require("playwright");
const { AxeBuilder } = require("@axe-core/playwright");
const path = require("node:path");
const out = path.resolve(__dirname, "../test-results/landed-costs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
(async () => {
  const browser = await chromium.launch({
    ...(process.env.OMP_BROWSER_EXECUTABLE
      ? { executablePath: process.env.OMP_BROWSER_EXECUTABLE }
      : { channel: process.env.OMP_BROWSER_CHANNEL || "chrome" }),
    headless: true,
  });
  try {
    const context = await browser.newContext({
      viewport: { width: 1366, height: 900 },
      extraHTTPHeaders: { "X-Frappe-Site-Name": input.site },
    });
    const response = await context.request.post(
      input.base + "/api/method/login",
      { data: { usr: input.user, pwd: input.password } },
    );
    assert.equal(response.status(), 200);
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(input.base + "/omp#costs");
    const ready = () =>
      page.waitForFunction(
        () =>
          window.OMPWorkspace?.state.boot && !window.OMPWorkspace.state.busy,
      );
    await ready();
    await page.evaluate(async (brand) => {
      const W = window.OMPWorkspace;
      W.active(brand);
      await W.run(() => window.OMPLandedCosts.enter());
    }, input.brand);
    await ready();
    await page.locator("#valuation summary").focus();
    await page.keyboard.press("Enter");
    await page.locator("#valuation-refresh").focus();
    await page.keyboard.press("Enter");
    await ready();
    assert.match(
      await page.locator("#valuation-status").textContent(),
      /Sin recálculos abiertos/,
    );
    assert.match(
      await page.locator("#valuation-result").textContent(),
      new RegExp(input.item_code),
    );
    assert.equal(await page.locator("#valuation-native").isVisible(), true);
    fs.mkdirSync(out, { recursive: true });
    await page
      .locator("#valuation")
      .screenshot({ path: path.join(out, "margin.png") });
    const fromDate = await page.locator("#valuation-from").inputValue();
    await page.locator("#valuation-from").fill("2000-01-01");
    assert.equal(await page.locator("#valuation-result").textContent(), "");
    assert.equal(await page.locator("#valuation-native").isVisible(), false);
    await page.locator("#valuation-from").fill(fromDate);
    await page.locator("#valuation-refresh").click();
    await ready();
    await page
      .locator("#cost-receipts label")
      .filter({ hasText: input.receipt })
      .locator("input")
      .check();
    await page.locator("#cost-charges select").selectOption(input.account);
    await page.locator("#cost-charges input").nth(0).fill("Flete ficticio");
    await page.locator("#cost-charges input").nth(1).fill("500.00");
    await page.locator("#cost-charges input").nth(2).fill("1");
    await page.locator("#cost-preview").focus();
    await page.keyboard.press("Enter");
    await ready();
    assert.equal(await page.locator("#cost-review").isVisible(), true);
    assert.match(await page.locator("#cost-summary").textContent(), /500/);
    await page.locator("#cost-confirm").check();
    await page.locator("#cost-draft").focus();
    await page.keyboard.press("Enter");
    await ready();
    assert.match(
      await page.locator("#cost-state").textContent(),
      /Estimación en borrador/,
    );
    assert.equal(await page.locator("#valuation-result").textContent(), "");
    const journal = await page.evaluate(() =>
      Object.entries(localStorage).find(([k]) =>
        k.startsWith("omp:landed-costs:"),
      ),
    );
    await page.reload();
    await ready();
    assert.match(
      await page.locator("#cost-state").textContent(),
      /Estimación en borrador/,
    );
    assert.equal(await page.locator("#business-picker").isDisabled(), true);
    await page.locator("#cost-confirm").check();
    await page.locator("#cost-submit-draft").click();
    await ready();
    assert.match(
      await page.locator("#cost-state").textContent(),
      /Distribución enviada/,
    );
    assert.equal(
      await page.evaluate(
        (key) => JSON.parse(localStorage.getItem(key)).request_id,
        journal[0],
      ),
      JSON.parse(journal[1]).request_id,
    );
    await page.locator("#cost-status").click();
    await ready();
    await page.locator("#valuation summary").click();
    await page.locator("#valuation-refresh").click();
    await ready();
    const valuation = await page.locator("#valuation-status").textContent();
    assert.match(valuation, /Hay recálculos abiertos|Sin recálculos abiertos/);
    if (valuation.includes("Hay recálculos abiertos")) {
      assert.equal(await page.locator("#valuation-native").isVisible(), false);
      assert.equal(
        await page
          .getByRole("columnheader", { name: "Margen bruto", exact: true })
          .count(),
        0,
      );
    }
    const desktop = await page.evaluate(() => ({
      viewport: innerWidth,
      width: document.documentElement.scrollWidth,
    }));
    assert.ok(desktop.width <= desktop.viewport);
    const axe = await new AxeBuilder({ page })
      .include("#view-costs")
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();
    assert.deepEqual(axe.violations, []);
    fs.mkdirSync(out, { recursive: true });
    await page.evaluate(() => scrollTo(0, 0));
    await page.screenshot({
      path: path.join(out, "desktop.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    const mobile = await page.evaluate(() => ({
      viewport: innerWidth,
      width: document.documentElement.scrollWidth,
    }));
    assert.ok(mobile.width <= mobile.viewport);
    await page.locator("#cost-status").focus();
    await page.keyboard.press("Tab");
    const focus = await page.evaluate(() => ({
      tag: document.activeElement.tagName,
      tabIndex: document.activeElement.tabIndex,
    }));
    assert.notEqual(focus.tag, "BODY");
    assert.ok(focus.tabIndex >= 0);
    await page.screenshot({
      path: path.join(out, "mobile.png"),
      fullPage: true,
    });
    await page.locator("#cost-new").click();
    await ready();
    await page
      .locator("#cost-receipts label")
      .filter({ hasText: input.pending_receipt })
      .locator("input")
      .check();
    await page.locator("#cost-charges select").selectOption(input.account);
    await page
      .locator("#cost-charges input")
      .nth(0)
      .fill("Flete ficticio pendiente");
    await page.locator("#cost-charges input").nth(1).fill("500.00");
    await page.locator("#cost-charges input").nth(2).fill("1");
    await page.locator("#cost-preview").click();
    await ready();
    await page.locator("#cost-confirm").check();
    await page.route(
      "**/api/method/open_multi_pos.landed_costs.save",
      (route) => route.abort("failed"),
      { times: 1 },
    );
    await page.locator("#cost-send").click();
    await ready();
    await page.reload();
    await ready();
    assert.equal(await page.locator("#cost-new").isDisabled(), true);
    assert.equal(await page.locator("#cost-abandon").isVisible(), true);
    const pending = await page.evaluate(
      (key) => JSON.parse(localStorage.getItem(key)),
      journal[0],
    );
    assert.notEqual(pending.request_id, JSON.parse(journal[1]).request_id);
    const pendingAxe = await new AxeBuilder({ page })
      .include("#view-costs")
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();
    assert.deepEqual(pendingAxe.violations, []);
    // The server commits abandonment, but its response is lost before the browser sees it.
    await page.route(
      "**/api/method/open_multi_pos.landed_costs.abandon",
      async (route) => {
        const response = await route.fetch();
        assert.equal(response.status(), 200);
        await route.abort("failed");
      },
      { times: 1 },
    );
    await page.locator("#cost-abandon").focus();
    await page.keyboard.press("Enter");
    await ready();
    assert.equal(
      await page.evaluate(
        (key) => JSON.parse(localStorage.getItem(key)).request_id,
        journal[0],
      ),
      pending.request_id,
    );
    await page.reload();
    await ready();
    assert.match(
      await page.locator("#cost-state").textContent(),
      /Intento abandonado en el servidor/,
    );
    assert.equal(await page.locator("#cost-new").isEnabled(), true);
    await page.locator("#cost-new").click();
    await ready();
    assert.equal(
      await page.evaluate((key) => localStorage.getItem(key), journal[0]),
      null,
    );
    assert.equal(await page.locator("#cost-inputs").isVisible(), true);
    assert.deepEqual(errors, []);
    console.log(
      JSON.stringify({
        desktop,
        mobile,
        keyboard: true,
        recovery: true,
        draftSubmitted: true,
        abandonmentRecovered: true,
        axeViolations: axe.violations.length,
      }),
    );
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
