"use strict";
(async () => {
  const $ = (id) => document.getElementById(id);
  const frame = $("preview-frame");
  const status = $("preview-status");
  let documents = [];
  let generation = 0;
  let busy = false;
  async function api(method, args = {}) {
    const url = new URL(
      "/api/method/open_multi_pos." + method,
      location.origin,
    );
    for (const [key, value] of Object.entries(args))
      url.searchParams.set(key, value);
    const response = await fetch(url, {
      credentials: "same-origin",
      cache: "no-store",
      signal: AbortSignal.timeout(20000),
    });
    if (!response.ok)
      throw new Error(
        "No se pudo abrir el recibo. Comprueba el negocio, el documento y tus permisos; si la sesión venció, vuelve a iniciar sesión.",
      );
    return (await response.json()).message;
  }
  function invalidate() {
    generation++;
    frame.hidden = true;
    frame.srcdoc = "";
    $("print-preview").disabled = true;
    status.textContent = "Pulsa Ver recibo para actualizar la vista previa.";
  }
  function selection() {
    const source = $("preview-source").value;
    if (source === "sample")
      return { brand: $("preview-brand").value, kind: "sample" };
    const invoice = $("invoice-name").value.trim();
    const row = documents[Number($("preview-document").value)];
    if (!invoice && !row)
      throw new Error(
        "Selecciona una venta o escribe el número completo de una factura.",
      );
    return {
      brand: $("preview-brand").value,
      kind: invoice ? "invoice" : row.kind,
      document: invoice || row.document,
    };
  }
  async function show() {
    const current = ++generation;
    frame.hidden = true;
    $("print-preview").disabled = true;
    const result = await api("receipt_preview.preview", selection());
    if (current !== generation) return false;
    await new Promise((resolve, reject) => {
      const timer = setTimeout(
        () =>
          reject(
            new Error("La vista previa tardó demasiado. Intenta de nuevo."),
          ),
        15000,
      );
      frame.onload = async () => {
        try {
          if (!frame.contentWindow.ompPrepareReceipt) return;
          await frame.contentWindow.ompPrepareReceipt();
          clearTimeout(timer);
          resolve();
        } catch (error) {
          clearTimeout(timer);
          reject(error);
        }
      };
      frame.hidden = false;
      frame.srcdoc = result.html;
    });
    if (current !== generation) return false;
    frame.hidden = false;
    const heightMm = Number(
      frame.contentDocument.body.dataset.printPageHeightMm,
    );
    frame.style.height =
      Math.min(900, Math.max(170, (heightMm * 96) / 25.4 + 12)) + "px";
    $("print-preview").disabled = false;
    status.textContent = result.sample
      ? "Muestra: producto e importe de ejemplo. No es una venta."
      : "Recibo guardado: datos originales de la venta.";
    return true;
  }
  async function run(action) {
    if (busy) return;
    busy = true;
    for (const control of document.querySelectorAll("select, input"))
      control.disabled = true;
    $("show-preview").disabled = true;
    $("print-preview").disabled = true;
    status.textContent = "Cargando…";
    try {
      await action();
    } catch (error) {
      invalidate();
      status.textContent = error.message;
    } finally {
      busy = false;
      $("show-preview").disabled = false;
      for (const control of document.querySelectorAll("select, input"))
        control.disabled = false;
    }
  }
  async function loadDocuments() {
    const brand = $("preview-brand").value;
    const rows = await api("receipt_preview.documents", { brand });
    if (brand !== $("preview-brand").value) return;
    documents = rows;
    $("preview-document").replaceChildren(
      ...rows.map((row, index) => new Option(row.label, String(index))),
    );
    if (!rows.length)
      $("preview-document").add(
        new Option("No hay ventas recientes disponibles", ""),
      );
  }
  $("preview-form").onsubmit = (event) => {
    event.preventDefault();
    run(show);
  };
  $("print-preview").onclick = () =>
    run(async () => {
      // Fresh authorization immediately before the explicit browser print action.
      if (await show()) {
        frame.contentWindow.focus();
        frame.contentWindow.print();
      }
    });
  $("preview-brand").onchange = () => {
    invalidate();
    run(async () => {
      await loadDocuments();
      status.textContent = "Pulsa Ver recibo para actualizar la vista previa.";
    });
  };
  $("preview-source").onchange = () => {
    invalidate();
    const saved = $("preview-source").value === "saved";
    $("saved-options").hidden = !saved;
    $("preview-help").textContent = saved
      ? "Se usan los datos originales de la venta. Cambiar opciones actuales no modifica este recibo."
      : "La muestra usa los datos y opciones guardados del negocio seleccionado, con un producto y un importe de ejemplo. No es una venta.";
  };
  $("preview-document").onchange = invalidate;
  $("invoice-name").oninput = invalidate;
  await run(async () => {
    const boot = await api("workspace.boot");
    $("preview-brand").replaceChildren(
      ...boot.businesses.map(
        (brand) => new Option(brand.display_name, brand.brand),
      ),
    );
    const initial = new URLSearchParams(location.search).get("brand");
    if (boot.businesses.some((brand) => brand.brand === initial))
      $("preview-brand").value = initial;
    if (!boot.businesses.length)
      throw new Error("Primero configura un negocio en Administración.");
    await loadDocuments();
    status.textContent = "Selecciona el contenido y pulsa Ver recibo.";
  });
})();
