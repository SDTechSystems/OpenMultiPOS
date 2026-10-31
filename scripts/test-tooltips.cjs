const assert = require("node:assert/strict");
const path = require("node:path");
const { chromium } = require("playwright");
(async () => {
  const browser = await chromium.launch({
    channel: process.env.OMP_BROWSER_CHANNEL || "chrome",
  });
  try {
    const page = await browser.newPage();
    await page.setContent(
      '<button data-tooltip="Consulta existencias" aria-describedby="original">Inventario</button><p id="original">Negocio activo</p><button id="next">Siguiente</button>',
    );
    await page.evaluate(() => {
      window.OMPWorkspace = { t: (text) => text };
    });
    await page.addStyleTag({
      path: path.join(__dirname, "../open_multi_pos/public/workspace.css"),
    });
    await page.addScriptTag({
      path: path.join(
        __dirname,
        "../open_multi_pos/public/workspace-tooltips.js",
      ),
    });
    const button = page.locator("[data-tooltip]"),
      tip = page.getByRole("tooltip");
    await button.focus();
    assert.equal(await tip.textContent(), "Consulta existencias");
    assert.equal(await tip.isVisible(), true);
    assert.equal(
      await button.getAttribute("aria-describedby"),
      "original workspace-tooltip",
    );
    await page.keyboard.press("Escape");
    assert.equal(await tip.isVisible(), false);
    assert.equal(await button.getAttribute("aria-describedby"), "original");
    await button.hover();
    assert.equal(await tip.isVisible(), true);
    await tip.hover();
    await page.waitForTimeout(200);
    assert.equal(
      await tip.isVisible(),
      true,
      "Pointer can move onto and read the tooltip",
    );
    await page.locator("#next").hover();
    await tip.waitFor({ state: "hidden" });
    await page.setViewportSize({ width: 390, height: 768 });
    await page.evaluate(() => new Promise(requestAnimationFrame));
    await page.locator("#next").focus();
    await button.focus();
    await tip.waitFor({ state: "visible" });
    const box = await tip.boundingBox();
    assert.ok(box.x >= 0 && box.x + box.width <= 390);
    await page.keyboard.press("Tab");
    assert.equal(await tip.isVisible(), false);
    console.log(
      "Tooltips: keyboard, Escape, existing descriptions, hover persistence and mobile bounds passed.",
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
