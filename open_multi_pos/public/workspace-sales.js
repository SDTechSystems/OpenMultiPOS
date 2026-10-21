"use strict";
window.OMPSales = (() => {
  const W = window.OMPWorkspace,
    { $, el, api, run, notice, fields, value, form, cents, money, decimal } = W;
  const state = {
    contexts: [],
    cart: [],
    quotes: [],
    journal: null,
    ready: false,
    receipt: false,
  };
  const scope =
    "omp:batch:v1:" + location.host + ":" + document.body.dataset.user;
  function read() {
    const raw = localStorage.getItem(scope);
    return raw ? JSON.parse(raw) : null;
  }
  function save(record) {
    localStorage.setItem(scope, JSON.stringify(record));
    state.journal = record;
  }
  async function locked(action) {
    if (!navigator.locks || !crypto.randomUUID)
      throw new Error(
        "Esta venta requiere Chrome o Edge actualizado, con almacenamiento local habilitado.",
      );
    return navigator.locks.request(scope, async () => {
      state.journal = read();
      return action();
    });
  }
  function controls() {
    const pending = !!state.journal;
    document.querySelectorAll("#shift-strip button").forEach((button) => {
      button.disabled = W.state.busy || pending;
    });
    $("sale-controls").disabled = W.state.busy || pending;
    $("calculate").disabled = W.state.busy || pending || !state.cart.length;
    $("save-sale").disabled = W.state.busy || pending || !state.quotes.length;
    $("sale-recovery").hidden = !pending || state.journal.status !== "pending";
    $("sale-operation").textContent = pending
      ? "Intento " + state.journal.payload.request_id
      : "";
    for (const id of ["sale-status", "sale-retry", "sale-abandon"])
      $(id).disabled = W.state.busy;
    $("next-sale").disabled =
      W.state.busy || !pending || state.journal.status === "pending";
    $("print-receipt").disabled = W.state.busy || !state.receipt;
    $("reload-receipt").disabled =
      W.state.busy || state.journal?.status !== "completed";
  }
  async function contexts() {
    state.contexts = [];
    for (const brand of W.state.boot.businesses) {
      try {
        const terminal = await api(
          "workspace.terminal_for",
          { brand: brand.brand },
          true,
        );
        const ctx = await api("cashier.context", {
          terminal: terminal.terminal,
        });
        ctx.brand_id = brand.brand;
        ctx.currency =
          brand.currency ||
          W.state.boot.companies.find((c) => c.name === brand.company)
            ?.default_currency;
        state.contexts.push(ctx);
      } catch (error) {
        notice(error.message, true);
      }
    }
    drawShifts();
  }
  function drawShifts() {
    $("shift-strip").replaceChildren();
    for (const ctx of state.contexts) {
      const row = el("div", undefined, "shift-entry"),
        open = ctx.opening?.status === "Open";
      row.append(
        el("strong", ctx.brand.display_name),
        el("span", open ? "Caja abierta" : "Caja cerrada"),
      );
      const btn = el(
        "button",
        open ? "Resumen y cierre" : "Abrir caja",
        "secondary",
      );
      btn.onclick = () => (open ? closeShift(ctx) : openShift(ctx));
      btn.disabled = !!state.journal || W.state.busy;
      row.append(btn);
      $("shift-strip").append(row);
    }
  }
  function modeLabel(mode) {
    return mode.type === "Cash" ? "Efectivo" : "Transferencia";
  }
  function openShift(ctx) {
    form(
      "Abrir caja",
      ctx.brand.display_name + ". Registra el saldo inicial de cada medio.",
      ctx.payment_modes.map((m, i) => ({
        id: "opening-" + i,
        label: modeLabel(m),
        value: "0.00",
        required: true,
        inputMode: "decimal",
        help: "Saldo inicial disponible para este negocio. Usa cero si no hay saldo. No registra una venta ni un ingreso de inventario.",
      })),
      async () => {
        await api(
          "checkout.open_shift",
          {
            data: {
              terminal: ctx.terminal,
              balances: ctx.payment_modes.map((m, i) => ({
                mode_of_payment: m.name,
                amount: decimal(value("opening-" + i)),
              })),
            },
          },
          true,
        );
        await contexts();
        notice("Caja abierta. Puedes escanear productos.");
      },
      "Abrir caja",
    );
  }
  async function closeShift(ctx) {
    await run(async () => {
      const summary = await api(
        "checkout.shift_summary",
        { terminal: ctx.terminal, opening_entry: ctx.opening.name },
        true,
      );
      form(
        "Cerrar caja",
        `${ctx.brand.display_name}. ${summary.invoice_count} ventas. Registra el conteo real. Las diferencias se conservarán.`,
        summary.payments.map((m, i) => ({
          id: "closing-" + i,
          label:
            (ctx.payment_modes.find((p) => p.name === m.mode_of_payment)
              ?.type === "Cash"
              ? "Efectivo"
              : "Transferencia") +
            ". Esperado " +
            money(cents(m.expected), ctx.currency),
          value: "",
          required: true,
          inputMode: "decimal",
          help: "Cuenta el importe real de este negocio. El sistema conserva cualquier diferencia con el valor esperado.",
        })),
        async () => {
          await api(
            "checkout.close_shift",
            {
              data: {
                terminal: ctx.terminal,
                opening_entry: ctx.opening.name,
                counts: summary.payments.map((m, i) => ({
                  mode_of_payment: m.mode_of_payment,
                  amount: decimal(value("closing-" + i)),
                })),
              },
            },
            true,
          );
          await contexts();
          notice("Cierre guardado.");
        },
        "Guardar cierre",
      );
    });
  }
  function invalidate() {
    state.quotes = [];
    $("pay-form").hidden = true;
    controls();
  }
  function drawCart() {
    invalidate();
    $("basket").replaceChildren();
    $("basket-count").textContent =
      state.cart.reduce((sum, r) => sum + r.qty, 0) + " productos";
    if (!state.cart.length) {
      W.empty(
        $("basket"),
        "Escanea o busca un producto para empezar. Cada línea mostrará su negocio.",
      );
      return;
    }
    for (const row of state.cart) {
      const line = el("div", undefined, "basket-row"),
        name = el("div", undefined, "row-name");
      name.append(
        el("strong", row.name),
        el("span", row.brand_name, "badge"),
        el("small", row.item_code),
      );
      const qty = el("input");
      qty.type = "number";
      qty.min = "1";
      qty.max = "10000";
      qty.step = "1";
      qty.value = row.qty;
      qty.setAttribute("aria-label", "Cantidad de " + row.item_code);
      qty.onchange = () => {
        if (
          !Number.isInteger(qty.valueAsNumber) ||
          qty.valueAsNumber < 1 ||
          qty.valueAsNumber > 10000
        ) {
          qty.value = row.qty;
          return;
        }
        row.qty = qty.valueAsNumber;
        invalidate();
      };
      const remove = el("button", "Quitar", "quiet");
      remove.type = "button";
      remove.onclick = () => {
        if (state.journal) return;
        state.cart = state.cart.filter((r) => r !== row);
        drawCart();
      };
      line.append(name, qty, remove);
      $("basket").append(line);
    }
  }
  function add(row) {
    if (state.journal || W.state.busy) return;
    const ctx = state.contexts.find((c) => c.terminal === row.terminal);
    if (ctx.opening?.status !== "Open") {
      openShift(ctx);
      notice(
        "Abre la caja de este negocio antes de agregar el producto.",
        true,
      );
      return;
    }
    const existing = state.cart.find(
      (r) => r.item_code === row.item_code && r.terminal === row.terminal,
    );
    if (existing) existing.qty = Math.min(10000, existing.qty + 1);
    else if (state.cart.length < 50) state.cart.push({ ...row, qty: 1 });
    else {
      notice("La cesta admite hasta 50 líneas.", true);
      return;
    }
    drawCart();
    $("scan").value = "";
    $("scan-results").replaceChildren();
    $("scan").focus();
  }
  async function search() {
    let exact = null;
    await run(async () => {
      if (state.journal) return;
      const text = $("scan").value.trim();
      if (!text) return;
      const results = [];
      for (const ctx of state.contexts) {
        const list = await api("cashier.search", {
          terminal: ctx.terminal,
          text,
        });
        results.push(
          ...list.map((r) => ({
            ...r,
            terminal: ctx.terminal,
            brand: ctx.brand_id,
            brand_name: ctx.brand.display_name,
          })),
        );
      }
      $("scan-results").replaceChildren();
      const matches = results.filter((r) => r.exact);
      if (matches.length === 1) {
        exact = matches[0];
        return;
      }
      if (!results.length) {
        W.empty(
          $("scan-results"),
          "No hay productos con ese código o nombre. Puedes crearlos en Inventario.",
        );
        return;
      }
      if (matches.length > 1)
        notice(
          "Este código coincide con más de un negocio. Elige dónde pertenece el producto.",
        );
      for (const row of results) {
        const line = el("div", undefined, "result-row"),
          name = el("div", undefined, "row-name");
        name.append(
          el("strong", row.name),
          el("span", row.brand_name, "badge"),
          el("small", row.item_code),
        );
        const button = el("button", "Agregar", "secondary");
        button.type = "button";
        button.onclick = () => add(row);
        line.append(name, button);
        $("scan-results").append(line);
      }
    });
    if (exact) add(exact);
  }
  $("scan-form").onsubmit = (event) => {
    event.preventDefault();
    search();
  };
  window.OMPScanner.attach(
    $("scan"),
    () => !!W.state.boot?.settings.scanner_us,
  );
  $("scan").addEventListener("keydown", (event) => {
    if (
      event.key === "Tab" &&
      W.state.boot?.settings.scanner_terminator === "Tab" &&
      $("scan").value
    ) {
      event.preventDefault();
      search();
    }
  });
  $("calculate").onclick = () =>
    run(async () => {
      if (state.journal) return;
      const groups = new Map();
      for (const row of state.cart) {
        if (!groups.has(row.terminal)) groups.set(row.terminal, []);
        groups
          .get(row.terminal)
          .push({ item_code: row.item_code, qty: row.qty });
      }
      state.quotes = [];
      for (const [terminal, items] of groups) {
        const ctx = state.contexts.find((c) => c.terminal === terminal);
        const quote = await api(
          "checkout.quote",
          { data: { terminal, customer: ctx.customer, items } },
          true,
        );
        state.quotes.push({ ctx, quote });
      }
      if (new Set(state.quotes.map((r) => r.quote.currency)).size > 1)
        throw new Error(
          "Los negocios deben usar la misma moneda para compartir una cesta. Guarda las ventas por separado.",
        );
      $("pay-groups").replaceChildren();
      for (const [index, row] of state.quotes.entries()) {
        const group = el("div", undefined, "payment-group");
        group.append(
          el("h3", row.ctx.brand.display_name),
          el("p", "Total " + money(cents(row.quote.total), row.quote.currency)),
        );
        const root = el("div", undefined, "field-grid");
        fields(
          root,
          row.ctx.payment_modes.map((mode, m) => ({
            id: `pay-${index}-${m}`,
            label: modeLabel(mode),
            value: mode.type === "Cash" ? row.quote.total : "0.00",
            required: true,
            inputMode: "decimal",
            help:
              mode.type === "Cash"
                ? "Efectivo recibido que asignas a este negocio. El cambio solo se devuelve del efectivo."
                : "Transferencia confirmada por ti y asignada a este negocio. El programa no consulta ni confirma movimientos del banco.",
          })),
        );
        group.append(root);
        $("pay-groups").append(group);
      }
      $("basket-total").textContent =
        "Total " +
        money(
          state.quotes.reduce((sum, r) => sum + cents(r.quote.total), 0n),
          state.quotes[0].quote.currency,
        );
      $("pay-form").hidden = false;
      notice("Total calculado. Confirma los pagos recibidos antes de guardar.");
    });
  async function preview() {
    state.receipt = false;
    $("receipt-preview").hidden = true;
    $("receipt-preview").removeAttribute("srcdoc");
    const result = await api(
      "batch.receipt",
      { request_id: state.journal.payload.request_id },
      true,
    );
    const frame = $("receipt-preview");
    await new Promise((resolve, reject) => {
      const timer = setTimeout(
        () =>
          reject(
            new Error(
              "La venta está guardada. Vuelve a cargar el recibo para preparar la impresión.",
            ),
          ),
        15000,
      );
      frame.onload = async () => {
        if (!frame.contentWindow.ompPrepareReceipt) return;
        try {
          await frame.contentWindow.ompPrepareReceipt();
          clearTimeout(timer);
          resolve();
        } catch {
          clearTimeout(timer);
          reject(
            new Error(
              "No se pudo preparar el recibo. La venta sigue guardada.",
            ),
          );
        }
      };
      frame.srcdoc = result.html;
      frame.hidden = false;
    });
    state.receipt = true;
  }
  async function outcome(result) {
    if (result.status === "completed") {
      save({ ...state.journal, status: "completed" });
      $("saved-receipt-label").textContent =
        "Venta guardada. Recibo interno sin validez fiscal.";
      notice("Venta guardada. Puedes imprimir el recibo sin volver a cobrar.");
      try {
        await preview();
      } catch (error) {
        notice("Venta guardada. " + error.message, true);
      }
    } else if (result.status === "abandoned") {
      save({ ...state.journal, status: "abandoned" });
      notice(
        "Intento bloqueado sin crear otra venta. Concilia cualquier pago externo antes de continuar.",
      );
    } else
      notice(
        "Todavía no se encontró la venta. Conserva el intento y reintenta con la misma clave o resuélvelo sin crear venta.",
      );
    drawShifts();
    controls();
  }
  async function recover() {
    if (state.journal)
      await outcome(
        await api("batch.get_status", {
          request_id: state.journal.payload.request_id,
        }),
      );
  }
  $("pay-form").onsubmit = (event) => {
    event.preventDefault();
    run(() =>
      locked(async () => {
        if (state.journal) {
          await recover();
          return;
        }
        const sales = state.quotes.map((row, index) => {
          const payments = row.ctx.payment_modes
            .map((mode, m) => ({
              mode_of_payment: mode.name,
              amount: decimal(value(`pay-${index}-${m}`)),
            }))
            .filter((p) => cents(p.amount) > 0n);
          if (
            payments.reduce((sum, p) => sum + cents(p.amount), 0n) <
            cents(row.quote.total)
          )
            throw new Error("El pago debe cubrir el total de cada negocio.");
          return {
            terminal: row.ctx.terminal,
            request_id: crypto.randomUUID(),
            quote: row.quote.quote,
            payments,
          };
        });
        const payload = { request_id: crypto.randomUUID(), sales };
        save({ payload, status: "pending" });
        controls();
        await outcome(await api("batch.checkout", { data: payload }, true));
      }),
    );
  };
  $("sale-status").onclick = () => run(() => locked(recover));
  $("sale-retry").onclick = () =>
    run(() =>
      locked(async () => {
        if (state.journal?.status !== "pending") {
          await recover();
          return;
        }
        await outcome(
          await api("batch.checkout", { data: state.journal.payload }, true),
        );
      }),
    );
  $("sale-abandon").onclick = () =>
    run(() =>
      locked(async () => {
        if (state.journal)
          await outcome(
            await api("batch.abandon", { data: state.journal.payload }, true),
          );
      }),
    );
  $("reload-receipt").onclick = () => run(preview);
  $("print-receipt").onclick = () =>
    run(async () => {
      await preview();
      $("receipt-preview").contentWindow.focus();
      $("receipt-preview").contentWindow.print();
      notice(
        "Se solicitó el diálogo de impresión. Revisa el papel. La venta ya está guardada.",
      );
    });
  $("next-sale").onclick = () =>
    run(() =>
      locked(async () => {
        if (!state.journal || state.journal.status === "pending") return;
        localStorage.removeItem(scope);
        state.journal = null;
        state.cart = [];
        state.receipt = false;
        $("receipt-preview").hidden = true;
        $("receipt-preview").removeAttribute("srcdoc");
        $("saved-receipt-label").textContent =
          "El recibo aparecerá después de guardar la venta.";
        drawCart();
        await contexts();
        notice("Lista para una nueva venta.");
        $("scan").focus();
      }),
    );
  window.addEventListener("storage", (event) => {
    if (event.key !== scope) return;
    state.journal = read();
    state.receipt = false;
    $("receipt-preview").hidden = true;
    controls();
    if (W.state.view === "sales")
      notice(
        "La venta cambió en otra pestaña. Consulta su estado antes de continuar.",
      );
  });
  async function enter() {
    state.journal = read();
    if (!state.ready) {
      await contexts();
      state.ready = true;
      drawCart();
    } else await contexts();
    if (state.journal) await locked(recover);
    else if (!state.cart.length) $("scan").focus();
    controls();
  }
  return { enter, controls, state };
})();
