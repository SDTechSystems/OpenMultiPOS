// Synthetic fixture capture and cookie/CSRF browser checks. Secrets enter only via stdin.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");
const { AxeBuilder } = require("@axe-core/playwright");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const out = path.resolve(__dirname, "../test-results/workspace");
const ready = (page) =>
  page.waitForFunction(
    () => window.OMPWorkspace?.state.boot && !window.OMPWorkspace.state.busy,
  );
async function go(page, id) {
  await ready(page);
  await page.locator(`[data-view="${id}"]`).click();
  await ready(page);
  assert.equal(
    await page.locator("#page-title").textContent(),
    {
      home: "Inicio",
      sales: "Ventas",
      returns: "Devoluciones",
      warranty: "Garantías",
      imports: "Importar inventario",
      inventory: "Inventario",
      purchases: "Compras",
      finances: "Finanzas",
      customers: "Clientes y pedidos",
      businesses: "Negocios",
      team: "Equipo",
      settings: "Ajustes",
      help: "Ayuda",
    }[id],
  );
}
(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({
    channel: process.env.OMP_BROWSER_CHANNEL || "chrome",
    headless: true,
  });
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
      extraHTTPHeaders: { "X-Frappe-Site-Name": input.site },
    });
    const login = await context.request.post(input.base + "/api/method/login", {
      data: { usr: input.user, pwd: input.password },
    });
    assert.equal(login.status(), 200, "Fictional administrator cookie login");
    const page = await context.newPage();
    if (!input.probe) {
      await page.route(
        "**/api/method/open_multi_pos.workspace.recovery_status*",
        async (route) => {
          const response = await route.fetch();
          assert.equal(response.status(), 200, "Administrator recovery status");
          const body = await response.json();
          assert.deepEqual(Object.keys(body.message).sort(), [
            "backup_at",
            "backup_recent",
            "restore_at",
          ]);
          // Public manual images use invented operation dates, never local logs.
          await route.fulfill({
            response,
            json: {
              message: {
                backup_at: "2026-01-15T08:15:00+00:00",
                backup_recent: true,
                restore_at: "2026-01-14T16:00:00+00:00",
              },
            },
          });
        },
      );
      await page.route(
        "**/api/method/open_multi_pos.workspace.team*",
        async (route) => {
          const response = await route.fetch();
          const body = await response.json();
          body.message = body.message.filter((row) => row.name === input.user);
          await route.fulfill({ response, json: body });
        },
      );
      await page.route(
        "**/api/method/open_multi_pos.workspace.boot*",
        async (route) => {
          const response = await route.fetch();
          const body = await response.json();
          body.message.businesses = body.message.businesses.filter((b) =>
            input.businesses.some((f) => f.brand === b.brand),
          );
          body.message.companies = body.message.companies.filter((row) =>
            input.businesses.some((b) => b.company === row.name),
          );
          body.message.suggestions = "";
          await route.fulfill({ response, json: body });
        },
      );
    }
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(input.base + "/omp");
    await ready(page);
    if (input.probe) {
      console.log("portal ready");
      for (const id of [
        "home",
        "inventory",
        "businesses",
        "team",
        "settings",
        "help",
        "purchases",
        "finances",
        "customers",
        "sales",
      ]) {
        await go(page, id);
        console.log(id, "notice:", await page.locator("#notice").textContent());
        if (["purchases", "finances", "customers"].includes(id)) {
          const frame = page.locator("#view-" + id + " iframe");
          await frame.waitFor();
          await page.waitForTimeout(1800);
          console.log(id, "frame URL:", page.frames().at(-1).url());
          console.log(
            "frame title:",
            await frame.contentFrame().locator("h1,h2,h3").allTextContents(),
          );
        }
        await page.screenshot({
          path: path.join(out, id + ".png"),
          fullPage: id === "businesses",
        });
      }
      console.log("page errors", errors);
      return;
    }
    assert.ok(
      input.businesses.every((b) =>
        b.display_name.startsWith("Negocio ficticio "),
      ),
      "Only synthetic fixtures may generate public screenshots",
    );
    const boot = await page.evaluate(() => window.OMPWorkspace.state.boot);
    assert.ok(boot.full_name.includes("ficticio"), "Only fictional actor");
    assert.ok(
      boot.businesses.every((b) =>
        b.display_name.startsWith("Negocio ficticio "),
      ),
      "No private businesses in captures",
    );
    for (const id of [
      "home",
      "inventory",
      "businesses",
      "team",
      "settings",
      "help",
      "purchases",
      "finances",
      "customers",
    ]) {
      await go(page, id);
      if (["purchases", "finances", "customers"].includes(id)) {
        const iframe = page.locator("#view-" + id + " iframe");
        await iframe
          .contentFrame()
          .locator(".list-row-head,.page-head h3,.page-title,.list-no-result")
          .first()
          .waitFor({ timeout: 30000 });
        assert.ok(
          !page.frames().at(-1).url().includes("setup-wizard"),
          "Native tool must load",
        );
      }
      await page.screenshot({
        path: path.join(out, id + ".png"),
        fullPage: id === "businesses",
      });
    }
    for (const id of ["purchases", "finances", "customers"]) {
      await go(page, id);
      const prefix = {
        purchases: "purchase",
        finances: "finance",
        customers: "customer",
      }[id];
      const count = await page.locator("#" + prefix + "-tools button").count();
      for (let index = 1; index < count; index++) {
        await page
          .locator("#" + prefix + "-tools button")
          .nth(index)
          .click();
        const iframe = page.locator("#" + prefix + "-native iframe");
        await iframe
          .contentFrame()
          .locator(
            ".list-row-head,.page-title,.list-no-result,.report-wrapper,.tree-node,.tree-link,.tree-container",
          )
          .first()
          .waitFor({ timeout: 30000 });
        const appFrame = page
          .frames()
          .find(
            (f) =>
              f.parentFrame() === page.mainFrame() &&
              f.url().includes("/desk/"),
          );
        assert.ok(appFrame, "Native module frame");
        const text = await iframe.contentFrame().locator("body").innerText();
        assert.ok(
          !text.includes("Not permitted") &&
            !text.includes("No se encuentra") &&
            !text.includes("Not Found"),
          "Native tool access",
        );
      }
    }
    console.log("PASS all native purchasing, finance and customer tools");
    await go(page, "inventory");
    await page.locator("#add-product").click();
    assert.ok(await page.locator("#product-code").evaluate((n) => n.readOnly));
    await page.locator("#product-name").fill("Producto ficticio del manual");
    await page.locator("#product-barcode").fill(input.newBarcode);
    await page.locator("#product-price").fill("3000");
    let newCode,
      lostProduct = false;
    assert.ok(
      (await page.locator("#product-code").inputValue()).includes(
        "PRODUCTO-FICTICIO",
      ),
    );
    const previewSku = await page.locator("#product-code").inputValue();
    await page.screenshot({ path: path.join(out, "product-form.png") });
    await page.route(
      "**/api/method/open_multi_pos.workspace.create_product",
      async (route) => {
        const response = await route.fetch();
        assert.equal(response.status(), 200);
        newCode = (await response.json()).message.item_code;
        lostProduct = true;
        await route.abort("failed");
      },
    );
    await page.locator("#dialog-save").click();
    await page.waitForFunction(
      () => !document.getElementById("dialog-error").hidden,
    );
    assert.ok(lostProduct);
    assert.ok(newCode.startsWith(previewSku.replace(/…$/, "")));
    assert.match(newCode, /-[0-9]{5,}$/);
    await page.unroute("**/api/method/open_multi_pos.workspace.create_product");
    await page.reload();
    await ready(page);
    await page.locator("#retry-product").click();
    await ready(page);
    await page.locator("#product-recovery").waitFor({ state: "hidden" });
    assert.equal(
      await page.evaluate(
        () =>
          JSON.parse(
            localStorage.getItem(
              Object.keys(localStorage).find((k) =>
                k.startsWith("omp:product:v1:"),
              ),
            ),
          ).item_code,
      ),
      newCode,
    );
    console.log("PASS automatic SKU and product lost-response recovery");
    await page.screenshot({ path: path.join(out, "inventory.png") });
    await page.locator("#add-stock").click();
    await page.locator("#stock-code").selectOption(newCode);
    await page.locator("#stock-qty").fill("5");
    await page.locator("#stock-cost").fill("900");
    let lostStock = false;
    await page.route(
      "**/api/method/open_multi_pos.workspace.receive_stock",
      async (route) => {
        const response = await route.fetch();
        assert.equal(response.status(), 200);
        lostStock = true;
        await route.abort("failed");
      },
    );
    await page.locator("#dialog-save").click();
    await page.waitForFunction(
      () => !document.getElementById("dialog-error").hidden,
    );
    assert.ok(lostStock);
    await page.unroute("**/api/method/open_multi_pos.workspace.receive_stock");
    await page.reload();
    await ready(page);
    await page.locator("#retry-stock").click();
    await ready(page);
    await page.locator("#stock-recovery").waitFor({ state: "hidden" });
    console.log("PASS inventory creation and lost-response recovery");
    await go(page, "sales");
    for (const btn of await page.locator("#shift-strip button").all()) {
      if ((await btn.textContent()) !== "Abrir caja") continue;
      await btn.click();
      await page.locator("#dialog-save").click();
      await page.locator("#form-dialog").waitFor({ state: "hidden" });
      await ready(page);
    }
    for (const code of input.items) {
      await page.locator("#scan").fill(code);
      await page.locator("#scan").press("Enter");
      await ready(page);
    }
    assert.equal(await page.locator(".basket-row").count(), 2);
    await page.screenshot({ path: path.join(out, "sales.png") });
    await page.locator("#calculate").click();
    await ready(page);
    await page.locator("#pay-form").waitFor();
    let lost = false;
    await page.route(
      "**/api/method/open_multi_pos.batch.checkout",
      async (route) => {
        const response = await route.fetch();
        assert.equal(response.status(), 200);
        lost = true;
        await route.abort("failed");
      },
    );
    await page.locator("#save-sale").click();
    await ready(page);
    assert.ok(lost);
    await page.locator("#sale-recovery").waitFor();
    const saved = await page.evaluate(() =>
      JSON.stringify(window.OMPSales.state.journal.payload),
    );
    await page.unroute("**/api/method/open_multi_pos.batch.checkout");
    await page.reload();
    await ready(page);
    assert.equal(
      await page.evaluate(() =>
        JSON.stringify(window.OMPSales.state.journal.payload),
      ),
      saved,
    );
    await page.locator("#receipt-preview").waitFor();
    await page.waitForFunction(
      () => !document.getElementById("print-receipt").disabled,
    );
    assert.equal(
      await page
        .locator("#receipt-preview")
        .contentFrame()
        .locator("section")
        .count(),
      2,
    );
    const frame = page.locator("#receipt-preview").contentFrame();
    const total = await frame.locator(".total").textContent();
    assert.ok(total.includes("5.000"));

    const receipt = page.frames().find((f) => f.url() === "about:srcdoc");
    const pdfPage = await context.newPage();
    await pdfPage.setContent(await receipt.content());
    await pdfPage.addScriptTag({
      path: path.resolve(
        __dirname,
        "../open_multi_pos/public/receipt-print.js",
      ),
    });
    await pdfPage.evaluate(() => window.ompPrepareReceipt());
    await pdfPage.pdf({
      path: path.join(out, "compact-receipt.pdf"),
      preferCSSPageSize: true,
      printBackground: true,
    });
    await pdfPage.close();
    console.log("PASS mixed native sale and lost-response recovery");
    await go(page, "settings");
    await context.addInitScript(() => {
      window.print = () => {
        window.top.__receiptPrintCalls =
          (window.top.__receiptPrintCalls || 0) + 1;
      };
    });
    const [preview] = await Promise.all([
      context.waitForEvent("page"),
      page.locator("#open-receipt-preview").click(),
    ]);
    await preview.locator("#show-preview").waitFor();
    await preview.waitForFunction(
      () =>
        !document.getElementById("show-preview").disabled &&
        document.getElementById("preview-brand").options.length > 0,
    );
    await preview.locator("#show-preview").focus();
    await preview.keyboard.press("Enter");
    await preview.waitForFunction(
      () => !document.getElementById("print-preview").disabled,
    );
    assert.match(
      await preview.locator("#preview-status").textContent(),
      /Muestra/,
    );
    await preview
      .locator("#preview-frame")
      .contentFrame()
      .getByText("MUESTRA · NO ES UNA VENTA")
      .waitFor();
    await preview.screenshot({
      path: path.join(out, "receipt-preview.png"),
      fullPage: true,
    });
    const previewAxe = await new AxeBuilder({ page: preview })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();
    assert.deepEqual(
      previewAxe.violations
        .filter((v) => ["serious", "critical"].includes(v.impact))
        .map((v) => v.id),
      [],
    );
    assert.equal(
      await preview.evaluate(() => window.__receiptPrintCalls || 0),
      0,
    );
    let freshPreviewRequests = 0;
    preview.on("request", (request) => {
      if (request.url().includes("receipt_preview.preview"))
        freshPreviewRequests++;
    });
    await preview.locator("#print-preview").click();
    await preview.waitForFunction(() => window.__receiptPrintCalls === 1);
    assert.equal(
      freshPreviewRequests,
      1,
      "Explicit printing reauthorizes the receipt",
    );
    await preview.locator("#preview-source").selectOption("saved");
    assert.equal(await preview.locator("#print-preview").isDisabled(), true);
    await preview.locator("#preview-document").selectOption({
      label: (
        await preview.locator("#preview-document option").allTextContents()
      ).find((label) => label.startsWith("Recibo conjunto")),
    });
    await preview.locator("#show-preview").click();
    await preview.waitForFunction(
      () => !document.getElementById("print-preview").disabled,
    );
    for (const brand of input.businesses)
      await preview
        .locator("#preview-frame")
        .contentFrame()
        .getByRole("heading", { name: brand.display_name })
        .waitFor();
    await preview.setViewportSize({ width: 390, height: 844 });
    assert.equal(
      await preview.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
    );
    await preview.locator("summary").focus();
    await preview.keyboard.press("Enter");
    assert.equal(await preview.locator("details").getAttribute("open"), "");
    await preview.close();
    const printing = await context.newPage();
    await printing.goto(input.base + "/desk/print-settings/Print%20Settings");
    const nativePreview = printing.getByRole("button", {
      name: "Vista previa del recibo",
      exact: true,
    });
    await nativePreview.waitFor({ timeout: 60000 });
    const [nativePage] = await Promise.all([
      context.waitForEvent("page"),
      nativePreview.click(),
    ]);
    await nativePage.locator("#preview-brand").waitFor();
    assert.match(nativePage.url(), /omp_receipt_preview/);
    await nativePage.close();
    await printing.close();
    console.log(
      "PASS native Print Settings and portal receipt preview, sample, combined saved receipt, keyboard, mobile and axe",
    );
    await go(page, "returns");
    await page.locator("#return-load-button").click();
    await ready(page);
    await page.locator("#return-qty-0").fill("1");
    await page.locator("#return-calculate").click();
    await ready(page);
    await page
      .locator("#return-reason")
      .fill("Producto ficticio devuelto para el manual");
    await page.locator("#return-checked").check();
    await page.evaluate(() => {
      document.activeElement?.blur();
      window.scrollTo(0, 0);
    });
    await page.screenshot({
      path: path.join(out, "returns.png"),
      fullPage: true,
    });
    const returnAxe = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();
    assert.deepEqual(
      returnAxe.violations
        .filter((v) => ["serious", "critical"].includes(v.impact))
        .map((v) => v.id),
      [],
    );
    let lostReturn = false;
    await page.route(
      "**/api/method/open_multi_pos.returns.submit",
      async (route) => {
        const response = await route.fetch();
        assert.equal(response.status(), 200);
        if (!lostReturn) {
          lostReturn = true;
          await route.abort("failed");
        } else await route.fulfill({ response });
      },
    );
    await page.locator("#return-submit").focus();
    await page.keyboard.press("Enter");
    await ready(page);
    await page.locator("#return-recovery").waitFor();
    await page.reload();
    await ready(page);
    await page.locator("#return-result").waitFor();
    await page
      .locator("#return-receipt")
      .contentFrame()
      .getByText("DEVOLUCIÓN INTERNA SIN VALIDEZ FISCAL")
      .waitFor();
    assert.equal(await page.locator("#return-load-button").isDisabled(), true);
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
    );
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.locator("#return-next").click();
    await ready(page);
    await page.locator("#return-load-button").click();
    await ready(page);
    assert.equal(await page.locator("#return-qty-0").getAttribute("max"), "0");
    await go(page, "settings");
    console.log(
      "PASS guided return, same-key lost-response recovery, original receipt, keyboard, mobile and axe",
    );
    await go(page, "warranty");
    await page.locator("#warranty-new").click();
    await ready(page);
    await page.locator("#warranty-load-button").click();
    await ready(page);
    await page
      .locator("#warranty-complaint")
      .fill("Producto ficticio que no enciende");
    let lostClaim = false;
    await page.route(
      "**/api/method/open_multi_pos.warranty.create",
      async (route) => {
        const response = await route.fetch();
        assert.equal(response.status(), 200);
        if (!lostClaim) {
          lostClaim = true;
          await route.abort("failed");
        } else await route.fulfill({ response });
      },
    );
    await page.locator("#warranty-submit").focus();
    await page.keyboard.press("Enter");
    await ready(page);
    await page.locator("#warranty-recovery").waitFor();
    await page.reload();
    await ready(page);
    await page.locator("#warranty-detail").waitFor();
    assert.equal(await page.locator("#warranty-recovery").isHidden(), true);
    const claim = await page.locator("#warranty-title").textContent();
    assert.equal(
      await page
        .locator("#warranty-list tbody tr")
        .filter({ hasText: claim })
        .count(),
      1,
    );
    await page.locator("#warranty-state").selectOption("Closed");
    await page.locator("#warranty-save").click();
    await ready(page);
    assert.equal(
      await page.locator("#notice").getAttribute("data-error"),
      "true",
    );
    await page
      .locator("#warranty-resolution")
      .fill("Reemplazo ficticio entregado por su flujo propio");
    await page.locator("#warranty-note").fill("Nota ficticia de seguimiento");
    await page.locator("#warranty-save").focus();
    await page.keyboard.press("Enter");
    await ready(page);
    await page
      .locator("#warranty-notes")
      .getByText("Nota ficticia de seguimiento")
      .waitFor();
    assert.equal(await page.locator("#warranty-state").inputValue(), "Closed");
    await page.evaluate(() => {
      document.activeElement?.blur();
      window.scrollTo(0, 0);
    });
    const warrantyAxe = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();
    assert.deepEqual(
      warrantyAxe.violations
        .filter((v) => ["serious", "critical"].includes(v.impact))
        .map((v) => v.id),
      [],
    );
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
    );
    await page.setViewportSize({ width: 1440, height: 1000 });
    await go(page, "settings");
    console.log(
      "PASS warranty claim, same-key lost-response recovery, follow-up, keyboard, mobile and axe",
    );
    await go(page, "imports");
    const [template] = await Promise.all([
      page.waitForEvent("download"),
      page.locator("#import-template").click(),
    ]);
    assert.equal(template.suggestedFilename(), "plantilla-catalogo.csv");
    await page.locator("#import-file").setInputFiles({
      name: "errores-ficticios.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(
        "accion;sku;nombre;codigo_barras;grupo;precio;cantidad;costo\ncrear;;Producto ficticio;;Products;incorrecto;2;800\n",
      ),
    });
    await page.locator("#import-prepare").click();
    await ready(page);
    await page.locator("#import-errors").waitFor();
    assert.match(
      await page.locator("#import-error-table").textContent(),
      /importe/,
    );
    const importText =
      "accion;sku;nombre;codigo_barras;grupo;precio;cantidad;costo\ncrear;;Producto ficticio importado " +
      input.newCode +
      ";;Products;2800,50;2;900,25\n";
    let lostPreview = false;
    await page.route(
      "**/api/method/open_multi_pos.imports.preview",
      async (route) => {
        const response = await route.fetch();
        assert.equal(response.status(), 200);
        if (!lostPreview) {
          lostPreview = true;
          await route.abort("failed");
        } else await route.fulfill({ response });
      },
    );
    await page.locator("#import-file").setInputFiles({
      name: "catalogo-ficticio.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(importText),
    });
    await page.locator("#import-prepare").click();
    await ready(page);
    await page.reload();
    await ready(page);
    await page.locator("#import-review").waitFor();
    assert.match(
      await page.locator("#import-preview-table").textContent(),
      /SKU automático/,
    );
    assert.equal(await page.locator("#business-picker").isDisabled(), true);
    await page.locator("#import-confirm").check();
    await page.evaluate(() => {
      document.activeElement?.blur();
      window.scrollTo(0, 0);
    });
    await page.screenshot({
      path: path.join(out, "imports.png"),
      fullPage: true,
    });
    const importAxe = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();
    assert.deepEqual(
      importAxe.violations
        .filter((v) => ["serious", "critical"].includes(v.impact))
        .map((v) => v.id),
      [],
    );
    let lostImport = false;
    await page.route(
      "**/api/method/open_multi_pos.imports.apply",
      async (route) => {
        const response = await route.fetch();
        assert.equal(response.status(), 200);
        if (!lostImport) {
          lostImport = true;
          await route.abort("failed");
        } else await route.fulfill({ response });
      },
    );
    await page.locator("#import-apply").focus();
    await page.keyboard.press("Enter");
    await ready(page);
    await page.locator("#import-retry").waitFor();
    await page.reload();
    await ready(page);
    await page.locator("#import-result").waitFor();
    assert.match(
      await page.locator("#import-result-summary").textContent(),
      /Entrada de existencias/,
    );
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
    );
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.locator("#import-next").click();
    await ready(page);
    assert.equal(await page.locator("#import-file").isEnabled(), true);
    console.log(
      "PASS import template, validation errors, preparation and apply lost-response recovery, auto SKU, keyboard, mobile and axe",
    );
    await go(page, "settings");
    await page.locator("#setting-language").focus();
    await page.keyboard.press("Tab");
    const axe = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();
    fs.writeFileSync(
      path.join(out, "accessibility.json"),
      JSON.stringify(axe.violations),
    );
    assert.deepEqual(
      axe.violations
        .filter((v) => ["serious", "critical"].includes(v.impact))
        .map((v) => v.id),
      [],
    );
    await page.locator("#settings-fields .help summary").first().focus();
    await page.keyboard.press("Enter");
    assert.equal(
      await page.locator("#settings-fields .help").first().getAttribute("open"),
      "",
    );
    await page.keyboard.press("Escape");
    assert.equal(
      await page.locator("#settings-fields .help").first().getAttribute("open"),
      null,
    );
    await page.locator("#tutorial").click();
    await page.locator("#tour").waitFor();
    await page.locator("#tour-next").click();
    await page.locator("#tour-skip").click();
    await page.locator("#tour").waitFor({ state: "hidden" });
    await page.locator("#setting-language").selectOption("en");
    await page.locator("#setting-locale").selectOption("en-US");
    await page.locator("#settings-form button").click();
    await page.waitForFunction(
      () =>
        window.OMPWorkspace?.state.boot?.settings.interface_language === "en" &&
        !window.OMPWorkspace.state.busy,
    );
    assert.equal(await page.locator("#page-title").textContent(), "Settings");
    assert.equal(
      await page.locator("[data-view=inventory] span").textContent(),
      "Inventory",
    );
    await page.locator("#setting-language").selectOption("es");
    await page.locator("#setting-locale").selectOption("es-CO");
    await page.locator("#settings-form button").click();
    await page.waitForFunction(
      () =>
        window.OMPWorkspace?.state.boot?.settings.interface_language === "es" &&
        !window.OMPWorkspace.state.busy,
    );
    assert.equal(await page.locator("#page-title").textContent(), "Ajustes");
    console.log("PASS editable language and regional settings");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator("#menu-toggle").click();
    await go(page, "inventory");
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    );
    await page.screenshot({ path: path.join(out, "mobile.png") });
    assert.deepEqual(errors, []);
    console.log("PASS manual tutorials, keyboard, accessibility and mobile");
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error.stack);
  process.exitCode = 1;
});
