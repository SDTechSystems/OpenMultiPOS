"use strict";
const $ = (id) => document.getElementById(id);
const format = (cents) =>
  new Intl.NumberFormat("es-CO", {
    style: "currency",
    currency: "COP",
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(cents / 100);
const state = {
  context: null,
  products: [],
  cart: new Map(),
  lastReceipt: null,
  busy: false,
  pending: null,
  catalogVersion: 0,
};
const terminal =
  sessionStorage.getItem("omp-demo-terminal") || crypto.randomUUID();
sessionStorage.setItem("omp-demo-terminal", terminal);
function notify(text) {
  $("message").textContent = text;
}
function element(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}
async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "X-Demo-User": $("user").value,
      "X-Demo-Token": state.context?.token || "",
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || "Solicitud fallida");
  }
  return response.headers.get("Content-Type").includes("application/json")
    ? response.json()
    : response.text();
}
function currentBrand() {
  return state.context.brands.find((brand) => brand.id === $("brand").value);
}
function total() {
  return [...state.cart].reduce(
    (sum, [sku, qty]) =>
      sum + state.products.find((p) => p.sku === sku).price * qty,
    0,
  );
}
function lockInputs(locked) {
  $("user").disabled = locked;
  $("brand").disabled = locked;
  $("cash").disabled = locked;
  $("transfer").disabled = locked;
  $("clear").disabled = locked;
  $("exact").disabled = locked;
  $("checkout").disabled = locked || !state.cart.size;
  document
    .querySelectorAll(".product button,.quantity button")
    .forEach((button) => {
      button.disabled = locked || button.dataset.soldOut === "true";
    });
}
let contextVersion = 0;
async function loadContext() {
  const version = ++contextVersion;
  ++state.catalogVersion;
  const context = await request("/api/context");
  if (version !== contextVersion) return;
  state.context = context;
  state.cart.clear();
  state.pending = null;
  state.lastReceipt = null;
  $("brand").replaceChildren(
    ...context.brands.map((b) => {
      const option = element("option", "", b.name);
      option.value = b.id;
      return option;
    }),
  );
  $("printer").replaceChildren(
    ...context.printers.map((p) => {
      const option = element("option", "", p.name);
      option.value = p.id;
      return option;
    }),
  );
  $("printer").value = "generic-58";
  $("receipt").hidden = true;
  $("preview").disabled = true;
  $("print").disabled = true;
  $("cash").value = "";
  $("transfer").value = "";
  printerDetails();
  await loadBrand();
}
async function loadBrand() {
  const version = ++state.catalogVersion;
  const brand = currentBrand();
  state.cart.clear();
  state.pending = null;
  state.products = [];
  renderCart();
  $("brand-name").textContent = brand.name;
  $("brand-symbol").textContent = brand.symbol;
  $("warehouse").textContent = brand.warehouse + " · " + brand.company;
  $("cart-warehouse").textContent = brand.warehouse;
  document.documentElement.style.setProperty("--accent", brand.color);
  $("cash").value = "";
  $("transfer").value = "";
  $("search").value = "";
  const products = await request(
    `/api/catalog?brand=${encodeURIComponent(brand.id)}`,
  );
  if (version !== state.catalogVersion) return;
  state.products = products;
  renderProducts();
  renderCart();
}
function renderProducts() {
  const query = $("search").value.trim().toLocaleLowerCase("es-CO");
  const shown = state.products.filter((p) =>
    [p.name, p.sku, p.barcode].some((v) =>
      v.toLocaleLowerCase("es-CO").includes(query),
    ),
  );
  $("product-count").textContent = `${shown.length} productos`;
  $("products").replaceChildren(
    ...shown.map((p) => {
      const card = element("article", "product");
      const art = element("div", "product-art");
      const glyph = element("span", "", p.sku.split("-")[0]);
      glyph.setAttribute("aria-hidden", "true");
      art.append(glyph, element("div", "stock", `${p.stock} disponibles`));
      const body = element("div", "product-body");
      body.append(
        element("span", "category", p.category),
        element("h3", "", p.name),
        element("p", "sku", `${p.sku} · ${p.barcode}`),
      );
      const bottom = element("div", "product-bottom");
      const add = element("button", "", "+");
      add.type = "button";
      add.setAttribute("aria-label", `Agregar ${p.name}`);
      add.disabled = state.busy || !p.stock;
      add.dataset.soldOut = String(!p.stock);
      add.addEventListener("click", () => addProduct(p.sku));
      bottom.append(element("strong", "", format(p.price)), add);
      body.append(bottom);
      card.append(art, body);
      return card;
    }),
  );
  if (!shown.length)
    $("products").append(
      element("p", "muted", "No hay productos con esa búsqueda."),
    );
}
function addProduct(sku, delta = 1) {
  if (state.busy) return;
  const product = state.products.find((p) => p.sku === sku);
  const qty = (state.cart.get(sku) || 0) + delta;
  if (qty > product.stock) {
    notify("No hay más unidades disponibles en este almacén.");
    return;
  }
  if (qty <= 0) state.cart.delete(sku);
  else state.cart.set(sku, qty);
  state.pending = null;
  notify("");
  renderCart();
}
function renderCart() {
  $("cart").replaceChildren();
  if (!state.cart.size)
    $("cart").append(
      element(
        "p",
        "empty-cart",
        "Tu carrito está listo. Agrega el primer producto.",
      ),
    );
  for (const [sku, qty] of state.cart) {
    const p = state.products.find((item) => item.sku === sku);
    const row = element("div", "cart-row");
    const info = element("div");
    info.append(
      element("strong", "", p.name),
      element("small", "", format(p.price * qty)),
    );
    const quantity = element("div", "quantity");
    for (const [label, delta] of [
      ["−", -1],
      ["+", 1],
    ]) {
      const button = element("button", "", label);
      button.type = "button";
      button.setAttribute(
        "aria-label",
        `${delta > 0 ? "Aumentar" : "Reducir"} ${p.name}`,
      );
      button.disabled = state.busy;
      button.addEventListener("click", () => addProduct(sku, delta));
      quantity.append(button);
      if (delta === -1) quantity.append(element("span", "", String(qty)));
    }
    row.append(info, quantity);
    $("cart").append(row);
  }
  $("subtotal").textContent = format(total());
  $("total").textContent = format(total());
  $("checkout").disabled = !state.cart.size || state.busy;
}
function printerDetails() {
  const p = state.context.printers.find(
    (profile) => profile.id === $("printer").value,
  );
  $("printer-detail").textContent =
    `Papel ${p.paper_mm} mm · área útil ${p.printable_mm} mm · ${p.dots} puntos · prueba física pendiente. Ajusta tamaño y márgenes en el controlador.`;
}
let receiptVersion = 0;
async function previewReceipt() {
  if (!state.lastReceipt) return;
  const version = ++receiptVersion;
  $("print").disabled = true;
  const html = await request(
    `/api/receipt?id=${encodeURIComponent(state.lastReceipt.id)}&profile=${encodeURIComponent($("printer").value)}`,
  );
  if (version !== receiptVersion) return;
  $("receipt").onload = async () => {
    await $("receipt").contentWindow.ompPrepareReceipt?.();
    if (version === receiptVersion) $("print").disabled = false;
  };
  $("receipt").srcdoc = html;
  $("receipt").hidden = false;
  $("print-status").textContent =
    `Vista previa de ${state.lastReceipt.id} · ${state.lastReceipt.brand.name}. Cambiar el perfil no crea otra venta.`;
}
$("search").addEventListener("input", renderProducts);
$("search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const code = $("search").value.trim();
  const p = state.products.find(
    (p) => p.barcode === code || p.sku.toLowerCase() === code.toLowerCase(),
  );
  if (p) {
    addProduct(p.sku);
    $("search").value = "";
    renderProducts();
  } else
    notify("Código no encontrado. Selecciona un producto o revisa el lector.");
});
$("clear").addEventListener("click", () => {
  if (state.cart.size && window.confirm("¿Vaciar la venta de prueba actual?")) {
    state.cart.clear();
    state.pending = null;
    renderCart();
  }
});
$("exact").addEventListener("click", () => {
  $("cash").value = (total() / 100).toFixed(2);
  $("transfer").value = "0";
  state.pending = null;
});
for (const id of ["cash", "transfer"])
  $(id).addEventListener("input", () => {
    state.pending = null;
  });
$("brand").addEventListener("change", () =>
  loadBrand().catch((e) => notify(e.message)),
);
$("user").addEventListener("change", () =>
  loadContext()
    .then(() =>
      notify(
        "Usuario simulado cambiado. Este selector no es un sistema de autenticación.",
      ),
    )
    .catch((e) => notify(e.message)),
);
$("printer").addEventListener("change", () => {
  printerDetails();
  if (state.lastReceipt) previewReceipt().catch((e) => notify(e.message));
});
$("preview").addEventListener("click", () =>
  previewReceipt().catch((e) => notify(e.message)),
);
$("print").addEventListener("click", async () => {
  try {
    await $("receipt").contentWindow.ompPrepareReceipt?.();
    $("receipt").contentWindow.focus();
    $("receipt").contentWindow.print();
    $("print-status").textContent =
      "Diálogo solicitado. Verifica el papel o cancela; la venta ya está guardada y no se repite.";
  } catch {
    $("print-status").textContent =
      "No se pudo abrir el diálogo. La venta está guardada; puedes volver a intentarlo.";
  }
});
$("payment-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.busy || !state.cart.size) return;
  if (!state.pending)
    state.pending = {
      brand: $("brand").value,
      terminal,
      transaction_id: crypto.randomUUID(),
      items: [...state.cart].map(([sku, qty]) => ({ sku, qty })),
      cash: $("cash").value.trim() || "0",
      transfer: $("transfer").value.trim() || "0",
    };
  state.busy = true;
  lockInputs(true);
  $("checkout").textContent = "Guardando…";
  notify("");
  let saved = false;
  try {
    const result = await request("/api/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(state.pending),
    });
    saved = true;
    state.lastReceipt = result.receipt;
    state.pending = null;
    state.cart.clear();
    $("cash").value = "";
    $("transfer").value = "";
    renderCart();
    $("preview").disabled = false;
    notify(
      `Venta simulada guardada: ${result.receipt.id}. Cambio: ${format(result.receipt.change)}.`,
    );
    await previewReceipt();
    state.products = await request(
      `/api/catalog?brand=${encodeURIComponent($("brand").value)}`,
    );
    renderProducts();
  } catch (error) {
    notify(
      saved
        ? `La venta está guardada. No se pudo actualizar la vista: ${error.message}`
        : `${error.message}. Puedes reintentar; se conserva la clave de transacción.`,
    );
  } finally {
    state.busy = false;
    $("checkout").textContent = "Completar venta demo →";
    renderCart();
    lockInputs(false);
  }
});
loadContext().catch((e) => notify(`No se pudo cargar la demo: ${e.message}`));
let scanStarted = null;
$("scanner-code").addEventListener("input", () => {
  if (scanStarted === null) scanStarted = performance.now();
});
function showScan(terminator) {
  const code = $("scanner-code").value;
  const duration =
    scanStarted === null ? 0 : Math.round(performance.now() - scanStarted);
  $("scanner-result").textContent = code
    ? `Lectura: ${code} · ${code.length} caracteres · terminador: ${terminator} · ${duration} ms. Sin navegación ni envío al servidor.`
    : "No se recibió un código.";
  $("scanner-code").value = "";
  scanStarted = null;
}
$("scanner-code").addEventListener("keydown", (event) => {
  if (["Enter", "Tab"].includes(event.key) && $("scanner-code").value) {
    event.preventDefault();
    showScan(event.key);
  }
});
$("scanner-form").addEventListener("submit", (event) => {
  event.preventDefault();
  showScan("botón");
});
