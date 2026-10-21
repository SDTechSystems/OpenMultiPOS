"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const scope = `omp:checkout:v1:${location.host}:${document.body.dataset.user}`;
  const state = {
    context: null,
    cart: [],
    quote: null,
    journal: null,
    busy: false,
    receipt: false,
    closing: false,
  };
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  let durable = false;

  function message(text, error = false) {
    $("message").textContent = text;
    $("message").dataset.error = String(error);
  }
  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function decimal(value) {
    const text = String(value).trim().replace(",", ".");
    if (!/^\d{1,9}(\.\d{1,2})?$/.test(text))
      throw new Error(
        "Ingrese un importe con hasta dos decimales, sin separadores de miles.",
      );
    const [whole, fraction = ""] = text.split(".");
    return `${BigInt(whole)}.${fraction.padEnd(2, "0")}`;
  }
  function cents(value) {
    return BigInt(String(value).replace(".", ""));
  }
  function money(value) {
    const amount = BigInt(value);
    const sign = amount < 0n ? "−" : "";
    const absolute = amount < 0n ? -amount : amount;
    return `${sign}$ ${(absolute / 100n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".")},${(absolute % 100n).toString().padStart(2, "0")}`;
  }
  async function api(method, args = {}, post = false) {
    const address = `/api/method/open_multi_pos.${method}`;
    const response = await fetch(
      post ? address : `${address}?${new URLSearchParams(args)}`,
      {
        method: post ? "POST" : "GET",
        credentials: "same-origin",
        cache: "no-store",
        headers: post
          ? { "Content-Type": "application/json", "X-Frappe-CSRF-Token": csrf }
          : {},
        body: post ? JSON.stringify(args) : undefined,
        signal: AbortSignal.timeout(20000),
      },
    );
    const result = await response.json();
    if (!response.ok) {
      let detail =
        "La solicitud no se pudo completar. Revise la sesión y consulte el estado antes de repetir un cobro.";
      try {
        const entry = JSON.parse(JSON.parse(result._server_messages)[0]);
        detail = new DOMParser().parseFromString(entry.message, "text/html")
          .body.textContent;
      } catch {
        /* Never expose tracebacks or response payloads. */
      }
      throw new Error(detail);
    }
    return result.message;
  }
  function readJournal() {
    const raw = localStorage.getItem(scope);
    return raw ? JSON.parse(raw) : null;
  }
  function saveJournal(journal) {
    localStorage.setItem(scope, JSON.stringify(journal));
    state.journal = journal;
  }
  function controls() {
    const pending = Boolean(state.journal);
    const open = state.context?.opening?.status === "Open";
    $("terminal").disabled = state.busy || pending;
    $("basket-controls").disabled =
      state.busy || pending || !open || state.closing || !durable;
    $("quote").disabled = !state.cart.length;
    $("payment-controls").disabled =
      state.busy || pending || !state.quote || !durable;
    $("recovery").hidden = !pending || state.journal.status !== "pending";
    $("operation").textContent = pending
      ? `Intento ${state.journal.payload.request_id}`
      : "";
    for (const id of ["recover", "retry", "abandon"])
      $(id).disabled = state.busy;
    $("new-sale").disabled =
      state.busy || !pending || state.journal.status === "pending";
    $("preview").disabled = state.busy || state.journal?.status !== "completed";
    $("printer").disabled = state.busy || state.journal?.status !== "completed";
    $("print").disabled = state.busy || !state.receipt;
    $("summary").hidden = !state.context?.opening;
    $("summary").disabled = state.busy || pending;
    $("opening-panel").hidden = !state.context || open || pending;
    for (const button of $("opening-form").querySelectorAll("button, input"))
      button.disabled = state.busy;
    for (const button of $("closing-form").querySelectorAll("button, input"))
      button.disabled = state.busy;
  }
  async function run(action) {
    if (state.busy) return;
    state.busy = true;
    controls();
    try {
      await action();
    } catch (error) {
      message(
        error.message ||
          "Conexión interrumpida. Consulte el estado del intento.",
        true,
      );
    } finally {
      state.busy = false;
      controls();
    }
  }
  async function locked(action) {
    if (!durable)
      throw new Error(
        "Esta caja requiere almacenamiento local y bloqueo entre pestañas. Use Chrome o Edge actualizado.",
      );
    return navigator.locks.request(scope, async () => {
      state.journal = readJournal();
      return action();
    });
  }
  function amounts(container, modes, prefix, values = {}) {
    container.replaceChildren();
    for (const [index, mode] of modes.entries()) {
      const box = element("div");
      const label = element("label", mode.name);
      const input = element("input");
      input.id = `${prefix}-${index}`;
      label.htmlFor = input.id;
      input.type = "text";
      input.inputMode = "decimal";
      input.autocomplete = "off";
      input.value = values[mode.name] || "0.00";
      input.required = true;
      input.dataset.mode = mode.name;
      input.addEventListener("input", change);
      box.append(label, input);
      container.append(box);
    }
  }
  function rows(container, zero = false) {
    return [...container.querySelectorAll("input")]
      .map((input) => ({
        mode_of_payment: input.dataset.mode,
        amount: decimal(input.value),
      }))
      .filter((row) => zero || cents(row.amount) > 0n);
  }
  function change() {
    if (!state.quote) return;
    try {
      const paid = rows($("payments")).reduce(
        (sum, row) => sum + cents(row.amount),
        0n,
      );
      const difference = paid - cents(state.quote.total);
      $("change").textContent =
        difference >= 0n
          ? `Cambio estimado: ${money(difference)}`
          : `Falta: ${money(-difference)}`;
    } catch {
      $("change").textContent = "Revise los importes de pago.";
    }
  }
  function invalidate() {
    state.quote = null;
    $("quoted").hidden = true;
    $("payment-form").hidden = true;
  }
  function drawCart() {
    invalidate();
    $("cart").replaceChildren();
    $("cart-empty").hidden = state.cart.length > 0;
    for (const item of state.cart) {
      const li = element("li", undefined, "cart-row");
      const label = element(
        "span",
        `${item.name} · ${item.item_code} · ${item.uom}`,
      );
      const qty = element("input");
      qty.type = "number";
      qty.min = "1";
      qty.max = "10000";
      qty.step = "1";
      qty.value = item.qty;
      qty.setAttribute("aria-label", `Cantidad de ${item.item_code}`);
      qty.addEventListener("change", () => {
        if (
          !Number.isInteger(qty.valueAsNumber) ||
          qty.valueAsNumber < 1 ||
          qty.valueAsNumber > 10000
        ) {
          qty.value = item.qty;
          return;
        }
        item.qty = qty.valueAsNumber;
        invalidate();
        controls();
      });
      const remove = element("button", "Quitar");
      remove.type = "button";
      remove.setAttribute("aria-label", `Quitar ${item.item_code}`);
      remove.onclick = () => {
        state.cart = state.cart.filter((row) => row !== item);
        drawCart();
      };
      li.append(label, qty, remove);
      $("cart").append(li);
    }
    controls();
  }
  function add(item) {
    if (state.journal || state.busy) return;
    const old = state.cart.find((row) => row.item_code === item.item_code);
    if (old && old.qty < 10000) old.qty += 1;
    else if (!old && state.cart.length < 50)
      state.cart.push({ ...item, qty: 1 });
    drawCart();
    $("search").value = "";
    $("search").focus();
  }
  async function loadContext() {
    state.context = null;
    state.closing = false;
    $("closing-form").hidden = true;
    const terminal = $("terminal").value;
    if (!terminal)
      throw new Error(
        "No hay terminales habilitadas y autorizadas para este usuario. Configure una en Administración.",
      );
    state.context = await api("cashier.context", { terminal });
    const ctx = state.context;
    $("cashier-currency").textContent = ctx.currency;
    $("context").textContent =
      `${ctx.brand.display_name} · ${ctx.brand.company} · ${ctx.brand.warehouse} · Cliente: ${ctx.customer} · ${ctx.opening?.status === "Open" ? `Caja abierta ${ctx.opening.name}` : "Caja cerrada"}`;
    amounts($("balances"), ctx.payment_modes, "balance");
    $("printer").replaceChildren(
      ...ctx.printers.map((p) => new Option(p.name, p.id)),
    );
    $("printer").value = ctx.brand.printer_profile;
  }
  async function preview() {
    state.receipt = false;
    $("receipt").hidden = true;
    $("receipt").removeAttribute("srcdoc");
    const { payload } = state.journal;
    const result = await api(
      "cashier.receipt",
      {
        terminal: payload.terminal,
        request_id: payload.request_id,
        printer: $("printer").value,
      },
      true,
    );
    const frame = $("receipt");
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(
        () =>
          reject(
            new Error(
              "La venta está guardada. No se pudo preparar la vista previa; vuelva a cargar el recibo.",
            ),
          ),
        15000,
      );
      frame.onload = async () => {
        try {
          if (!frame.contentWindow.ompPrepareReceipt) return;
          await frame.contentWindow.ompPrepareReceipt();
          clearTimeout(timeout);
          resolve();
        } catch {
          clearTimeout(timeout);
          reject(new Error("No se pudo preparar el recibo."));
        }
      };
      frame.srcdoc = result.html;
      frame.hidden = false;
    });
    state.receipt = true;
    $("receipt-state").textContent =
      `${result.invoice} · Vista previa lista. Sin confirmación de papel.`;
  }
  async function outcome(result) {
    if (result.status === "completed") {
      saveJournal({ ...state.journal, status: "completed" });
      message(
        `Venta guardada: ${result.invoice}. Puede cargar o imprimir el recibo sin volver a cobrar.`,
      );
      $("receipt-state").textContent = `${result.invoice} · Venta guardada.`;
      try {
        await preview();
      } catch (error) {
        message(`Venta guardada: ${result.invoice}. ${error.message}`, true);
      }
    } else if (result.status === "abandoned") {
      saveJournal({ ...state.journal, status: "abandoned" });
      message(
        "Intento bloqueado sin factura. Concilie cualquier pago externo antes de iniciar otra venta.",
      );
    } else {
      message(
        "No se encontró una venta guardada. Conserve este intento: puede reintentarlo con la misma clave o resolverlo sin crear venta.",
      );
    }
  }
  async function recover() {
    const { payload } = state.journal;
    await outcome(
      await api("checkout.get_status", {
        terminal: payload.terminal,
        request_id: payload.request_id,
      }),
    );
  }

  $("terminal").onchange = () =>
    run(async () => {
      state.cart = [];
      drawCart();
      await loadContext();
      message("Terminal lista.");
    });
  $("opening-form").onsubmit = (event) => {
    event.preventDefault();
    run(async () => {
      await api(
        "checkout.open_shift",
        {
          data: {
            terminal: $("terminal").value,
            balances: rows($("balances"), true),
          },
        },
        true,
      );
      await loadContext();
      message("Caja abierta. Busque o escanee un artículo.");
      $("search").focus();
    });
  };
  $("search-form").onsubmit = (event) => {
    event.preventDefault();
    let exact = null;
    run(async () => {
      if (state.journal) return;
      const results = await api("cashier.search", {
        terminal: $("terminal").value,
        text: $("search").value,
      });
      $("results").replaceChildren();
      const matches = results.filter((item) => item.exact);
      if (matches.length === 1) {
        exact = matches[0];
        return;
      }
      for (const item of results) {
        const li = element("li", undefined, "result");
        const button = element("button", "Agregar");
        button.type = "button";
        button.setAttribute("aria-label", `Agregar ${item.item_code}`);
        button.onclick = () => add(item);
        li.append(
          element("span", `${item.name} · ${item.item_code} · ${item.uom}`),
          button,
        );
        $("results").append(li);
      }
      message(
        results.length
          ? "Seleccione el artículo. El precio se calculará al cotizar."
          : "No hay artículos autorizados con ese nombre o código.",
      );
    }).then(() => {
      if (exact) add(exact);
    });
  };
  window.OMPScanner.attach($("search"), () => $("scanner-us").checked);
  $("quote").onclick = () =>
    run(async () => {
      state.quote = await api(
        "checkout.quote",
        {
          data: {
            terminal: $("terminal").value,
            customer: state.context.customer,
            items: state.cart.map(({ item_code, qty }) => ({ item_code, qty })),
          },
        },
        true,
      );
      const quote = state.quote;
      $("quote-lines").replaceChildren(
        ...quote.items.map((item) =>
          element(
            "li",
            `${item.qty} × ${item.item_name} · ${money(cents(item.amount))}`,
          ),
        ),
      );
      $("taxes").textContent = `Impuestos: ${money(cents(quote.taxes))}`;
      $("total").textContent = `Total ${money(cents(quote.total))}`;
      amounts($("payments"), state.context.payment_modes, "payment");
      $("quoted").hidden = false;
      $("payment-form").hidden = false;
      change();
      message(
        "Cotización calculada. Confirme el pago recibido antes de guardar.",
      );
    });
  $("payment-form").onsubmit = (event) => {
    event.preventDefault();
    run(() =>
      locked(async () => {
        if (state.journal) {
          await recover();
          return;
        }
        const payments = rows($("payments"));
        if (
          !payments.length ||
          payments.reduce((sum, row) => sum + cents(row.amount), 0n) <
            cents(state.quote.total)
        )
          throw new Error("El pago debe cubrir el total.");
        const payload = {
          terminal: $("terminal").value,
          request_id: crypto.randomUUID(),
          quote: state.quote.quote,
          payments,
        };
        saveJournal({ payload, status: "pending" });
        controls();
        message(
          "Guardando venta. Conserve esta pestaña hasta conocer el estado.",
        );
        await outcome(await api("checkout.checkout", { data: payload }, true));
      }),
    );
  };
  $("recover").onclick = () => run(() => locked(recover));
  $("retry").onclick = () =>
    run(() =>
      locked(async () => {
        if (state.journal.status !== "pending") {
          await recover();
          return;
        }
        await outcome(
          await api("checkout.checkout", { data: state.journal.payload }, true),
        );
      }),
    );
  $("abandon").onclick = () =>
    run(() =>
      locked(async () => {
        await outcome(
          await api(
            "checkout.abandon_checkout",
            { data: state.journal.payload },
            true,
          ),
        );
      }),
    );
  $("new-sale").onclick = () =>
    run(() =>
      locked(async () => {
        if (!state.journal || state.journal.status === "pending") return;
        localStorage.removeItem(scope);
        state.journal = null;
        state.cart = [];
        state.receipt = false;
        $("receipt").hidden = true;
        $("receipt").removeAttribute("srcdoc");
        $("receipt-state").textContent =
          "Aparecerá después de guardar o recuperar la venta.";
        $("results").replaceChildren();
        drawCart();
        await loadContext();
        message("Lista para una nueva venta.");
      }),
    );
  $("preview").onclick = () => run(preview);
  $("printer").onchange = () => run(preview);
  $("print").onclick = () =>
    run(async () => {
      // Recheck current server permission even if a preview is already in memory.
      await preview();
      $("receipt").contentWindow.focus();
      $("receipt").contentWindow.print();
      message(
        "Diálogo de impresión solicitado. Verifique el papel; la venta permanece guardada.",
      );
    });
  $("summary").onclick = () =>
    run(async () => {
      const summary = await api(
        "checkout.shift_summary",
        {
          terminal: $("terminal").value,
          opening_entry: state.context.opening.name,
        },
        true,
      );
      $("closing-summary").textContent =
        `${summary.invoice_count} ventas · Total ${money(cents(summary.total))}. Registre el conteo real; las diferencias se conservarán.`;
      amounts(
        $("counts"),
        summary.payments.map((row) => ({
          name: `${row.mode_of_payment}`,
          type: "",
        })),
        "count",
      );
      for (const row of summary.payments) {
        const input = [...$("counts").querySelectorAll("input")].find(
          (node) => node.dataset.mode === row.mode_of_payment,
        );
        input.before(element("p", `Esperado: ${money(cents(row.expected))}`));
      }
      $("closing-form").hidden = false;
      state.closing = true;
      invalidate();
      if (summary.status === "Submitted")
        message("Este cierre ya fue guardado. Puede abrir una nueva caja.");
    });
  $("cancel-close").onclick = () => {
    state.closing = false;
    $("closing-form").hidden = true;
    controls();
  };
  $("closing-form").onsubmit = (event) => {
    event.preventDefault();
    run(async () => {
      const summary = await api(
        "checkout.close_shift",
        {
          data: {
            terminal: $("terminal").value,
            opening_entry: state.context.opening.name,
            counts: rows($("counts"), true),
          },
        },
        true,
      );
      await loadContext();
      message(`Cierre guardado: ${summary.closing_entry}.`);
    });
  };
  window.addEventListener("storage", (event) => {
    if (event.key !== scope) return;
    state.journal = readJournal();
    state.receipt = false;
    $("receipt").hidden = true;
    controls();
    message(
      "El intento cambió en otra pestaña. Consulte su estado antes de continuar.",
    );
    if (state.journal && state.journal.payload.terminal !== $("terminal").value)
      location.reload();
  });
  run(async () => {
    try {
      localStorage.setItem(`${scope}:probe`, "1");
      localStorage.removeItem(`${scope}:probe`);
      state.journal = readJournal();
      durable = Boolean(navigator.locks && crypto.randomUUID);
    } catch {
      durable = false;
    }
    const terminals = await api("cashier.terminals");
    $("terminal").replaceChildren(
      ...terminals.map(
        (row) => new Option(`${row.label} · ${row.brand}`, row.name),
      ),
    );
    if (state.journal) $("terminal").value = state.journal.payload.terminal;
    await loadContext();
    if (!durable)
      throw new Error(
        "No se puede guardar con seguridad el intento entre pestañas. Habilite almacenamiento local y use Chrome o Edge actualizado.",
      );
    if (state.journal) await locked(recover);
    else message("Seleccione la terminal y abra la caja para empezar.");
  });
})();
