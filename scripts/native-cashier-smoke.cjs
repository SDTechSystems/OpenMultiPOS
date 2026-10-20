// Real cookie/CSRF UI against disposable Bench. Input secrets only through stdin.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");
const { AxeBuilder } = require("@axe-core/playwright");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const out = path.resolve(__dirname, "../test-results/native-cashier");
const endpoint = (method) => `**/api/method/open_multi_pos.${method}`;
const enabled = (page, id) =>
  page.waitForFunction((name) => !document.getElementById(name).disabled, id);
const status = (page, text) =>
  page.waitForFunction(
    (value) => document.getElementById("message").textContent.includes(value),
    text,
  );
async function journal(page) {
  return page.evaluate(() => {
    const key = Object.keys(localStorage).find(
      (name) => name.startsWith("omp:checkout:v1:") && !name.endsWith(":probe"),
    );
    return key ? JSON.parse(localStorage.getItem(key)) : null;
  });
}
async function scan(page, value) {
  await enabled(page, "search");
  await page.locator("#search").fill(value);
  await page.locator("#search").press("Enter");
  await page.waitForFunction(
    () => document.querySelectorAll("#cart .cart-row").length === 1,
  );
}
async function quote(page, amount = "1000.00") {
  await page.locator("#quote").click();
  await page.locator("#payment-form").waitFor({ state: "visible" });
  await enabled(page, "payment-0");
  await page.locator("#payment-0").fill(amount);
}
async function fresh(page) {
  await enabled(page, "new-sale");
  await page.locator("#new-sale").click();
  await enabled(page, "search");
}
async function login(browser, fixture) {
  const context = await browser.newContext({
    viewport: { width: 1366, height: 900 },
    extraHTTPHeaders: { "X-Frappe-Site-Name": input.site },
  });
  const response = await context.request.post(
    `${input.base}/api/method/login`,
    {
      data: { usr: fixture.user, pwd: fixture.password },
    },
  );
  assert.equal(response.status(), 200, "Fictional cashier cookie login");
  const page = await context.newPage();
  await page.goto(`${input.base}/omp_pos`);
  await status(page, "Seleccione la terminal");
  await page.locator("#terminal").selectOption(fixture.terminal);
  await status(page, "Terminal lista");
  return { context, page };
}
async function open(page) {
  await page.locator("#balance-0").fill("100.00");
  await page.locator("#opening-form button").click();
  await status(page, "Caja abierta");
  await enabled(page, "search");
}
(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({
    channel: process.env.OMP_BROWSER_CHANNEL || "chrome",
    headless: true,
  });
  try {
    const guest = await browser.newContext({
      extraHTTPHeaders: { "X-Frappe-Site-Name": input.site },
    });
    const landing = await guest.request.get(`${input.base}/omp_pos`, {
      maxRedirects: 0,
    });
    assert.ok([301, 302, 303].includes(landing.status()));
    assert.match(landing.headers().location, /login/);
    await guest.close();
    const { context, page } = await login(browser, input.logins[0]);
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    assert.equal(
      await page
        .locator(`#terminal option[value="${input.logins[1].terminal}"]`)
        .count(),
      0,
    );
    // Cookie-authenticated mutations without the page's CSRF token must fail.
    const csrfFailure = await context.request.post(
      `${input.base}/api/method/open_multi_pos.checkout.open_shift`,
      {
        data: { data: { terminal: input.logins[0].terminal, balances: [] } },
        headers: { "X-Frappe-CSRF-Token": "invalid-test-token" },
      },
    );
    assert.equal(csrfFailure.status(), 400);
    await open(page);
    await page.locator("#scanner-us").check();
    // Physical HID code mapping while OS characters differ.
    await page.locator("#search").focus();
    await page.evaluate((barcode) => {
      const input = document.getElementById("search");
      for (const character of barcode) {
        const code = /[A-Z]/.test(character)
          ? `Key${character}`
          : /[0-9]/.test(character)
            ? `Digit${character}`
            : "Minus";
        input.dispatchEvent(
          new KeyboardEvent("keydown", {
            key: "mismatched-layout",
            code,
            shiftKey: /[A-Z]/.test(character),
            bubbles: true,
            cancelable: true,
          }),
        );
      }
    }, input.barcode);
    assert.equal(await page.locator("#search").inputValue(), input.barcode);
    await page.locator("#search").press("Enter");
    await page.waitForFunction(
      () => document.querySelectorAll(".cart-row").length === 1,
    );
    await quote(page, "700.00");
    await page.locator("#payment-1").fill("500.00");
    assert.match(await page.locator("#change").textContent(), /200,00/);
    const checks = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    assert.deepEqual(
      checks.violations.map((row) => `${row.id}:${row.nodes.length}`),
      [],
    );
    for (const width of [1366, 768, 390]) {
      await page.setViewportSize({ width, height: 900 });
      assert.ok(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        `No horizontal overflow ${width}`,
      );
      await page.screenshot({
        path: path.join(out, `cashier-${width}.png`),
        fullPage: true,
      });
    }
    await page.setViewportSize({ width: 1366, height: 900 });
    let commits = 0;
    page.on("request", (request) => {
      if (request.url().endsWith("/open_multi_pos.checkout.checkout"))
        commits += 1;
    });
    // Commit happens on Bench; the response is deliberately lost at the browser.
    await page.route(endpoint("checkout.checkout"), async (route) => {
      const response = await route.fetch();
      assert.equal(response.status(), 200);
      await route.abort("connectionreset");
    });
    await page.locator("#payment-1").focus();
    await page.locator("#payment-1").press("Tab");
    assert.equal(
      await page
        .locator("#checkout")
        .evaluate((node) => node === document.activeElement),
      true,
    );
    await page.locator("#checkout").press("Enter");
    await enabled(page, "recover");
    const uncertain = await journal(page);
    assert.equal(uncertain.status, "pending");
    assert.equal(commits, 1);
    assert.equal(await page.locator("#quote").isDisabled(), true);
    const second = await context.newPage();
    await second.goto(`${input.base}/omp_pos`);
    await status(second, "Venta guardada");
    assert.equal(
      (await journal(second)).payload.request_id,
      uncertain.payload.request_id,
    );
    await page.unroute(endpoint("checkout.checkout"));
    await page.reload();
    await status(page, "Venta guardada");
    await enabled(page, "print");
    assert.equal(
      (await journal(page)).payload.request_id,
      uncertain.payload.request_id,
    );
    assert.equal(commits, 1, "Reload/status never resubmits checkout");
    const receiptText = await page
      .frameLocator("#receipt")
      .locator("body")
      .textContent();
    assert.match(receiptText, /SIN VALIDEZ FISCAL/);
    assert.match(receiptText, /200/);
    assert.doesNotMatch(receiptText, /DEMO ·/);
    for (const [profile, width] of [
      ["jaltech-jal58m", 48],
      ["generic-58", 58],
      ["generic-80", 80],
    ]) {
      await page.locator("#printer").selectOption(profile);
      await enabled(page, "print");
      const frame = page.frames().find((frame) => frame.parentFrame());
      assert.equal(
        await frame.locator("body").getAttribute("data-paper-mm"),
        String(width),
      );
      const height = Number(
        await frame.locator("body").getAttribute("data-receipt-height-mm"),
      );
      assert.ok(height > 40 && height < 180);
      // Chromium PDF only proves browser layout, never physical paper.
      const pdf = await context.newPage();
      await pdf.setContent(await frame.content());
      await pdf.pdf({
        path: path.join(out, `native-${width}.pdf`),
        preferCSSPageSize: true,
      });
      await pdf.close();
    }
    // A receipt failure must leave the completed sale and request untouched.
    await page.route(endpoint("cashier.receipt"), (route) =>
      route.fulfill({
        status: 503,
        contentType: "application/json",
        body: "{}",
      }),
    );
    await page.locator("#preview").click();
    await enabled(page, "preview");
    assert.equal(await page.locator("#print").isDisabled(), true);
    assert.equal((await journal(page)).status, "completed");
    assert.equal(commits, 1);
    await page.unroute(endpoint("cashier.receipt"));
    await page.locator("#preview").click();
    await enabled(page, "print");
    // Stub only the physical dialog; use the real server receipt request.
    await page.addInitScript(() => {
      window.print = () => {
        window.testPrintDialog = true;
      };
    });
    await page.locator("#print").click();
    await status(page, "Diálogo de impresión solicitado");
    assert.equal(commits, 1);
    console.log(
      "PASS cookie auth, CSRF, HID scan, mixed payment, lost committed response, reload recovery, receipt profiles, print isolation, keyboard/mobile/axe",
    );

    await second.close();
    await fresh(page);
    await scan(page, input.logins[0].item);
    await quote(page);
    await page.route(endpoint("checkout.checkout"), (route) =>
      route.abort("connectionreset"),
    );
    await page.locator("#checkout").click();
    await enabled(page, "recover");
    const retryable = await journal(page);
    await page.unroute(endpoint("checkout.checkout"));
    await page.locator("#retry").click();
    await status(page, "Venta guardada");
    assert.equal(
      (await journal(page)).payload.request_id,
      retryable.payload.request_id,
    );
    console.log("PASS explicit retry keeps the original operation key");

    await fresh(page);
    await scan(page, input.logins[0].item);
    await quote(page);
    // Lost before send: persist key, status not_found, then atomic abandonment.
    await page.route(endpoint("checkout.checkout"), (route) =>
      route.abort("connectionreset"),
    );
    await page.locator("#checkout").click();
    await enabled(page, "recover");
    const absent = await journal(page);
    await page.locator("#recover").click();
    await status(page, "No se encontró");
    assert.equal(
      (await journal(page)).payload.request_id,
      absent.payload.request_id,
    );
    await page.unroute(endpoint("checkout.checkout"));
    await page.locator("#abandon").click();
    await status(page, "Intento bloqueado sin factura");
    const late = await page.evaluate(async (payload) => {
      const result = await fetch(
        "/api/method/open_multi_pos.checkout.checkout",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Frappe-CSRF-Token": document.querySelector(
              'meta[name="csrf-token"]',
            ).content,
          },
          body: JSON.stringify({ data: payload }),
        },
      );
      return result.status;
    }, absent.payload);
    assert.equal(late, 409, "Delayed checkout cannot commit after abandonment");
    console.log(
      "PASS lost unsent response, same durable key, atomic abandonment, delayed request fenced",
    );

    await fresh(page);
    await scan(page, input.logins[0].item);
    await quote(page);
    const parallel = await context.newPage();
    await parallel.goto(`${input.base}/omp_pos`);
    await enabled(parallel, "search");
    await scan(parallel, input.logins[0].item);
    await quote(parallel);
    const requests = [];
    context.on("request", (request) => {
      if (request.url().endsWith("/open_multi_pos.checkout.checkout"))
        requests.push(request);
    });
    await Promise.all([
      page.evaluate(() =>
        document.getElementById("payment-form").requestSubmit(),
      ),
      parallel.evaluate(() =>
        document.getElementById("payment-form").requestSubmit(),
      ),
    ]);
    await status(page, "Venta guardada");
    await status(parallel, "Venta guardada");
    assert.equal(
      requests.length,
      1,
      "Web lock permits only one new operation across tabs",
    );
    assert.equal(
      (await journal(page)).payload.request_id,
      (await journal(parallel)).payload.request_id,
    );
    await parallel.close();
    console.log("PASS concurrent tabs create one checkout operation");

    await fresh(page);
    await page.locator("#summary").click();
    await page.locator("#closing-form").waitFor({ state: "visible" });
    // Opening100 + net500cash +1000retry +1000tabs =2600; bank500.
    await page.locator("#count-0").fill("2600.00");
    await page.locator("#count-1").fill("500.00");
    await page.locator("#closing-form button[type=submit]").click();
    await status(page, "Cierre guardado");
    await page.waitForFunction(
      () =>
        document.getElementById("basket-controls").disabled &&
        !document.getElementById("opening-panel").hidden,
    );

    const other = await login(browser, input.logins[1]);
    await other.page.setViewportSize({ width: 390, height: 844 });
    assert.equal(
      await other.page
        .locator(`#terminal option[value="${input.logins[0].terminal}"]`)
        .count(),
      0,
    );
    const denied = await other.context.request.get(
      `${input.base}/api/method/open_multi_pos.cashier.context`,
      { params: { terminal: input.logins[0].terminal } },
    );
    assert.equal(denied.status(), 403);
    await open(other.page);
    await scan(other.page, input.logins[1].item);
    await quote(other.page);
    await other.page.locator("#checkout").click();
    await status(other.page, "Venta guardada");
    assert.equal((await journal(other.page)).status, "completed");
    assert.deepEqual(errors, []);
    console.log(
      "PASS native closing counts, second cashier, foreign terminal rejection, mobile sale",
    );
    await other.context.close();
    await context.close();
  } finally {
    await browser.close();
  }
})().catch((error) => {
  // No payloads, cookies, passwords or tracebacks from the ERP framework.
  console.error(error.stack);
  process.exitCode = 1;
});
