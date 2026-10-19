// Render a trusted, locally generated demo receipt URL to a bounded PBM raster.
// Usage: node scripts/render-receipt-raster.cjs URL output-prefix
const fs = require("node:fs");
const { chromium } = require("playwright");
(async () => {
  const url = new URL(process.argv[2]);
  if (
    url.protocol !== "http:" ||
    !["127.0.0.1", "localhost"].includes(url.hostname) ||
    url.pathname !== "/api/receipt"
  )
    throw Error("Use a local demo receipt URL");
  const prefix = process.argv[3] || "test-results/receipt-native";
  const browser = await chromium.launch({
    channel: process.env.OMP_BROWSER_CHANNEL || "chrome",
    headless: true,
  });
  try {
    const context = await browser.newContext({
      viewport: { width: 500, height: 600 },
      deviceScaleFactor: 203 / 96,
    });
    const page = await context.newPage();
    await page.goto(url.href);
    await page.waitForFunction(() => window.ompReceiptReady);
    const profile = await page.evaluate(async () => {
      const d = document.body.dataset;
      const printable = Number(d.printableMm),
        margin = Number(d.marginMm);
      // Raster starts at the printer's printable origin. Encode margins inside it.
      document.documentElement.style.width = `${printable}mm`;
      document.body.style.width = `${printable}mm`;
      document.querySelector("article").style.width =
        `${printable - 2 * margin}mm`;
      await window.ompPrepareReceipt();
      return {
        dots: Number(d.dots),
        dpi: Number(d.dpi),
        printableMm: printable,
      };
    });
    const png = await page.locator("body").screenshot();
    const raster = await page.evaluate(
      async ({ png, expected }) => {
        const image = new Image();
        image.src = `data:image/png;base64,${png}`;
        await image.decode();
        if (
          image.width < expected ||
          image.width > expected + 1 ||
          expected % 8 ||
          image.height > 30000
        )
          throw Error(`Unexpected raster ${image.width}x${image.height}`);
        const canvas = document.createElement("canvas");
        canvas.width = image.width;
        canvas.height = image.height;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(image, 0, 0);
        const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
        // Chromium can round the CSS bounding box up by one white pixel.
        // Remove that rounding column only after checking no ink is lost.
        if (canvas.width > expected)
          for (let y = 0; y < canvas.height; y++) {
            const i = (y * canvas.width + expected) * 4;
            if (Math.min(pixels[i], pixels[i + 1], pixels[i + 2]) < 250)
              throw Error("Ink outside printable width");
          }
        const packed = new Uint8Array((expected / 8) * canvas.height);
        for (let y = 0; y < canvas.height; y++)
          for (let x = 0; x < expected; x++) {
            const i = (y * canvas.width + x) * 4;
            if (
              (pixels[i] * 299 + pixels[i + 1] * 587 + pixels[i + 2] * 114) /
                1000 <
              170
            )
              packed[y * (expected / 8) + (x >> 3)] |= 0x80 >> x % 8;
          }
        return {
          width: expected,
          height: canvas.height,
          data: Array.from(packed),
        };
      },
      { png: png.toString("base64"), expected: profile.dots },
    );
    fs.writeFileSync(`${prefix}.png`, png);
    fs.writeFileSync(
      `${prefix}.pbm`,
      Buffer.concat([
        Buffer.from(`P4\n${raster.width} ${raster.height}\n`),
        Buffer.from(raster.data),
      ]),
    );
    console.log(
      JSON.stringify({
        width: raster.width,
        height: raster.height,
        estimatedContentMm: Math.round((raster.height / profile.dpi) * 25.4),
        profile,
      }),
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
