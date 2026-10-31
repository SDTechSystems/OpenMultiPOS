// Fictional setup flow. Fixture credentials arrive through stdin only.
const assert = require("node:assert/strict");
const fs = require("node:fs");
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
    page.on("pageerror", (error) => errors.push(error.message));
    const ready = () =>
      page.waitForFunction(
        () =>
          window.OMPWorkspace?.state.boot && !window.OMPWorkspace.state.busy,
      );
    await page.goto(input.base + "/omp");
    await ready();
    await page.locator("#setup-open").focus();
    await page.keyboard.press("Enter");
    await ready();
    assert.equal(
      await page.locator("#setup-title").textContent(),
      "Tu cuenta personal",
    );
    await page.getByRole("button", { name: "Siguiente", exact: true }).click();
    await ready();
    assert.equal(
      await page.locator("#setup-title").textContent(),
      "Preferencias",
    );
    await page.reload();
    await ready();
    assert.equal(
      await page.locator("#setup-title").textContent(),
      "Preferencias",
    );
    assert.equal(
      await page
        .locator("#setup-title")
        .evaluate((node) => document.activeElement === node),
      true,
    );
    for (let step = 0; step < 4; step++) {
      await page
        .getByRole("button", { name: "Siguiente", exact: true })
        .click();
      await ready();
    }
    assert.equal(
      await page
        .getByRole("button", { name: "Terminar preparación", exact: true })
        .isDisabled(),
      true,
    );
    for (const width of [1366, 390]) {
      await page.setViewportSize({ width, height: 900 });
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        true,
      );
      const results = await new AxeBuilder({ page })
        .include("#setup-wizard")
        .analyze();
      assert.deepEqual(
        results.violations.map((row) => row.id),
        [],
      );
    }
    await page.route(
      "**/api/method/open_multi_pos.onboarding.apply",
      async (route) => {
        assert.equal((await route.fetch()).status(), 200);
        await route.abort("failed");
      },
      { times: 1 },
    );
    await page.evaluate(
      async ({ email, password }) => {
        await window.OMPWorkspace.run(() =>
          window.OMPOnboarding.create("user", {
            email,
            full_name: "Cuenta ficticia de navegador",
            password,
            role: "admin",
            brands: [],
          }),
        );
      },
      { email: input.new_user, password: input.new_password },
    );
    await ready();
    assert.equal(await page.locator("#setup-operation").isVisible(), true);
    const saved = await page.evaluate(() =>
      Object.entries(localStorage)
        .filter(([key]) => key.startsWith("omp:setup:v1:"))
        .map(([, value]) => value)
        .join(""),
    );
    assert.equal(saved.includes(input.new_password), false);
    assert.equal(saved.includes('"password"'), false);
    await page.reload();
    await ready();
    assert.equal(await page.locator("#setup-operation").isVisible(), true);
    await page
      .getByRole("button", {
        name: "Consultar configuración pendiente",
        exact: true,
      })
      .click();
    await ready();
    assert.equal(await page.locator("#setup-operation").isVisible(), false);
    assert.deepEqual(errors, []);
    console.log(
      "Setup: server resume, keyboard, lost response recovery, password exclusion, mobile and axe passed.",
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
