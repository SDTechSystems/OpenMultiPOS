"use strict";
window.OMPReturns = (() => {
  const W = window.OMPWorkspace;
  const { $, el, api, run, notice, fields, value, cents, money, decimal } = W;
  const scope =
    "omp:returns:v1:" + location.host + ":" + document.body.dataset.user;
  let journal = null,
    source = null,
    estimate = null,
    terminal = null,
    selection = null;
  const read = () => JSON.parse(localStorage.getItem(scope) || "null");
  function save(record) {
    localStorage.setItem(scope, JSON.stringify(record));
    journal = record;
  }
  async function locked(action) {
    if (!navigator.locks || !crypto.randomUUID)
      throw new Error(
        "Usa Chrome o Edge actualizado con almacenamiento local habilitado.",
      );
    return navigator.locks.request(scope, async () => {
      journal = read();
      return action();
    });
  }
  function controls() {
    const blocked = W.state.busy || !!journal;
    for (const id of ["return-load", "return-quantities", "return-confirm"]) {
      $(id)
        .querySelectorAll("button, input, select, textarea")
        .forEach((node) => (node.disabled = blocked));
    }
    $("return-recovery").hidden = !journal || journal.status !== "pending";
    for (const id of [
      "return-status",
      "return-retry",
      "return-abandon",
      "return-next",
      "return-print",
    ])
      $(id).disabled = W.state.busy;
    $("return-operation").textContent = journal
      ? "Intento " + journal.data.request_id
      : "";
  }
  function reset() {
    source = estimate = selection = null;
    $("return-quantities").hidden =
      $("return-confirm").hidden =
      $("return-result").hidden =
        true;
    $("return-receipt").srcdoc = "";
    $("return-invoice").value = "";
    $("return-reason").value = "";
    $("return-checked").checked = false;
  }
  async function receipt() {
    const result = await api("returns.receipt", { data: journal.data }, true);
    const frame = $("return-receipt");
    await new Promise((resolve, reject) => {
      const timer = setTimeout(
        () =>
          reject(
            new Error(
              "No se pudo preparar el comprobante. Consulta el estado para recuperarlo.",
            ),
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
      frame.srcdoc = result.html;
    });
  }
  async function accept(result) {
    if (result.status === "completed") {
      save({
        ...journal,
        status: "completed",
        credit_note: result.credit_note,
      });
      $("return-result").hidden = false;
      $("return-saved").textContent =
        "Nota crédito " +
        result.credit_note +
        ". Venta original " +
        journal.data.invoice +
        ". No repitas la entrega del reembolso.";
      $("return-native").href =
        "/desk/sales-invoice/" + encodeURIComponent(result.credit_note);
      notice(
        "Devolución registrada. Revisa el comprobante y conserva la referencia del reembolso.",
      );
      await receipt();
    } else if (result.status === "abandoned") {
      localStorage.removeItem(scope);
      journal = null;
      reset();
      notice(
        "Intento resuelto sin crear otra nota. Verifica cualquier reembolso externo antes de empezar otro.",
      );
    } else
      notice(
        "Todavía no hay una devolución confirmada. Conserva el intento; puedes consultar, reintentar o resolverlo.",
      );
    controls();
  }
  async function loadRecent() {
    const rows = (
      await api("receipt_preview.documents", { brand: W.state.brand.brand })
    ).filter((row) => row.kind === "invoice");
    $("return-recent").replaceChildren(
      ...rows.map((row) => new Option(row.label, row.document)),
    );
    if (!rows.length)
      $("return-recent").add(
        new Option("No hay facturas recientes disponibles", ""),
      );
  }
  async function enter() {
    journal = read();
    reset();
    if (journal)
      await locked(async () => {
        await accept(await api("returns.status", { data: journal.data }, true));
      });
    await loadRecent();
    controls();
  }
  $("return-load").onsubmit = (event) => {
    event.preventDefault();
    run(async () => {
      if (read()) throw new Error("Resuelve primero la devolución pendiente.");
      const brand = W.state.brand.brand;
      const invoice =
        $("return-invoice").value.trim() || $("return-recent").value;
      if (!invoice)
        throw new Error("Selecciona una factura o escribe su número completo.");
      source = await api("returns.inspect", { brand, invoice }, true);
      source.brand = brand;
      terminal = (await api("workspace.terminal_for", { brand }, true))
        .terminal;
      estimate = selection = null;
      $("return-confirm").hidden = true;
      $("return-quantities").hidden = false;
      $("return-source").textContent =
        source.business +
        " · " +
        source.invoice +
        ". Cantidades pendientes después de las devoluciones enviadas.";
      fields(
        $("return-items"),
        source.items.map((row, i) => ({
          id: "return-qty-" + i,
          label: row.name + " · " + row.item_code,
          type: "number",
          value: "0",
          help:
            "Vendidos: " +
            row.sold +
            ". Pendientes: " +
            row.remaining +
            ". Precio original: " +
            money(row.rate, source.currency) +
            ". Usa cero para conservar este producto.",
        })),
      );
      source.items.forEach((row, i) => {
        const input = $("return-qty-" + i);
        input.min = 0;
        input.max = row.remaining;
        input.step = 1;
        input.oninput = () => {
          estimate = selection = null;
          $("return-confirm").hidden = true;
        };
      });
      $("return-quantities").scrollIntoView({ block: "nearest" });
    });
  };
  function invalidateSelection() {
    source = estimate = selection = null;
    $("return-quantities").hidden = $("return-confirm").hidden = true;
    $("return-checked").checked = false;
  }
  $("return-invoice").oninput = invalidateSelection;
  $("return-recent").onchange = invalidateSelection;
  $("return-quantities").onsubmit = (event) => {
    event.preventDefault();
    run(async () => {
      const items = source.items
        .map((row, i) => ({
          row: row.row,
          qty: Number(value("return-qty-" + i)),
        }))
        .filter((row) => row.qty > 0);
      if (!items.length || items.some((row) => !Number.isInteger(row.qty)))
        throw new Error(
          "Selecciona al menos una cantidad entera para devolver.",
        );
      selection = { brand: source.brand, invoice: source.invoice, items };
      estimate = await api("returns.quote", { data: selection }, true);
      $("return-total").textContent =
        "Total a reembolsar: " +
        money(estimate.total, estimate.currency) +
        ". Se usan los precios e impuestos de la venta original.";
      fields(
        $("return-payment-fields"),
        estimate.payment_modes.flatMap((mode, i) => [
          {
            id: "return-pay-" + i,
            label:
              (mode.kind === "Cash" ? "Efectivo" : "Transferencia") +
              " · " +
              mode.name,
            value:
              i === 0
                ? (BigInt(estimate.total) / 100n).toString() +
                  "." +
                  (BigInt(estimate.total) % 100n).toString().padStart(2, "0")
                : "0.00",
            inputMode: "decimal",
            required: true,
            help: "Importe positivo a reembolsar por este medio. Entre todos deben sumar exactamente el total. Usa cero si no corresponde.",
          },
          ...(mode.kind === "Bank"
            ? [
                {
                  id: "return-ref-" + i,
                  label: "Referencia de transferencia · " + mode.name,
                  value: "",
                  help: "Referencia del reembolso realizado por fuera del programa. No envía dinero al banco.",
                },
              ]
            : []),
        ]),
      );
      $("return-checked").checked = false;
      $("return-confirm").hidden = false;
    });
  };
  $("return-confirm").onsubmit = (event) => {
    event.preventDefault();
    run(() =>
      locked(async () => {
        if (journal) throw new Error("Ya hay una devolución por resolver.");
        if (!estimate || !selection || !$("return-checked").checked)
          throw new Error(
            "Calcula y revisa el reembolso antes de registrarlo.",
          );
        const payments = estimate.payment_modes
          .map((mode, i) => ({
            mode_of_payment: mode.name,
            amount: decimal(value("return-pay-" + i)),
            ...(mode.kind === "Bank"
              ? { reference_no: value("return-ref-" + i) }
              : {}),
          }))
          .filter((row) => cents(row.amount) > 0n);
        if (
          payments.reduce((sum, row) => sum + cents(row.amount), 0n) !==
          BigInt(estimate.total)
        )
          throw new Error(
            "Los medios de reembolso deben sumar exactamente el total.",
          );
        const reason = $("return-reason").value.trim();
        if (!reason) throw new Error("Escribe el motivo de devolución.");
        save({
          status: "pending",
          data: {
            ...selection,
            terminal,
            request_id: crypto.randomUUID(),
            financial_hash: estimate.financial_hash,
            payments,
            reason,
          },
        });
        controls();
        await accept(await api("returns.submit", { data: journal.data }, true));
      }),
    );
  };
  for (const [id, method] of [
    ["return-status", "status"],
    ["return-retry", "submit"],
    ["return-abandon", "abandon"],
  ])
    $(id).onclick = () =>
      run(() =>
        locked(async () => {
          if (!journal) return;
          await accept(
            await api("returns." + method, { data: journal.data }, true),
          );
        }),
      );
  $("return-next").onclick = () =>
    run(() =>
      locked(async () => {
        if (journal?.status !== "completed")
          throw new Error("Resuelve primero la devolución pendiente.");
        localStorage.removeItem(scope);
        journal = null;
        reset();
        await loadRecent();
        controls();
      }),
    );
  $("return-print").onclick = () =>
    run(async () => {
      await receipt();
      $("return-receipt").contentWindow.focus();
      $("return-receipt").contentWindow.print();
    });
  $("return-original-native").onclick = () => {
    const invoice =
      $("return-invoice").value.trim() || $("return-recent").value;
    if (!invoice)
      return notice(
        "Selecciona una factura o escribe su número completo.",
        true,
      );
    W.native(
      $("return-native-tools"),
      "sales-invoice/" + encodeURIComponent(invoice),
      "Factura original",
    );
  };
  $("return-native-list").onclick = () =>
    W.native(
      $("return-native-tools"),
      "sales-invoice?is_return=1",
      "Notas crédito",
    );
  return { enter, controls };
})();
