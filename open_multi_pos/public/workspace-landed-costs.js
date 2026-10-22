"use strict";
window.OMPLandedCosts = (() => {
  const W = window.OMPWorkspace,
    { $, el, api, run, notice, table } = W;
  const scope =
    "omp:landed-costs:v1:" + location.host + ":" + document.body.dataset.user;
  let journal = null,
    preview = null,
    options = null,
    current = null;
  const read = () => JSON.parse(localStorage.getItem(scope) || "null");
  function persist(value) {
    localStorage.setItem(scope, JSON.stringify(value));
    journal = value;
  }
  async function locked(action) {
    if (!navigator.locks || !crypto.randomUUID)
      throw new Error(
        "Usa Chrome o Edge actualizado con almacenamiento local habilitado.",
      );
    return navigator.locks.request(scope, async () => {
      journal = read();
      await action();
    });
  }
  function controls() {
    $("cost-inputs").hidden = !!journal;
    $("cost-preview").hidden = !!journal;
    $("cost-draft").hidden = $("cost-send").hidden = !!journal;
    $("cost-confirm").closest("label").hidden = current?.status === "submitted";
    $("cost-review-title").textContent =
      current?.status === "submitted"
        ? "Distribución registrada"
        : "Revisa antes de guardar o enviar";
    for (const node of $("cost-inputs").querySelectorAll("input,select,button"))
      node.disabled = W.state.busy || !!journal;
    $("cost-preview").disabled = W.state.busy || !!journal;
    $("cost-draft").disabled = $("cost-send").disabled =
      W.state.busy || !preview || !!journal;
    $("cost-refresh").hidden = !journal || !!current;
    $("cost-refresh").disabled = W.state.busy;
    $("cost-retry").hidden = !journal || !!current;
    $("cost-abandon").hidden = !journal || !!current;
    $("cost-abandon").disabled = W.state.busy || !journal;
    $("cost-retry").disabled = $("cost-status").disabled =
      W.state.busy || !journal;
    $("cost-submit-draft").hidden = current?.status !== "draft";
    $("cost-submit-draft").disabled = W.state.busy;
    $("cost-new").disabled = W.state.busy || !current;
    if (W.state.view === "costs" && journal)
      $("business-picker").disabled = true;
  }
  function draw(value) {
    preview = value;
    const p = value.plan;
    $("cost-review").hidden = false;
    $("cost-summary").textContent =
      `${p.business} · ${p.company} · ${p.warehouse}. Total a distribuir: ${p.total} ${p.currency}.`;
    table(
      $("cost-charge-preview"),
      [
        { label: "Concepto", render: (r) => r.description },
        { label: "Moneda original", render: (r) => r.currency },
        { label: "Importe original", render: (r) => r.amount },
        { label: "Tasa", render: (r) => r.exchange_rate },
        {
          label: "Importe contable",
          render: (r) => r.base_amount + " " + p.currency,
        },
      ],
      p.charges,
    );
    const display = (value) =>
      Number(value).toLocaleString("es-CO", { maximumFractionDigits: 6 });
    table(
      $("cost-item-preview"),
      [
        { label: "Recepción", render: (r) => r.receipt },
        { label: "SKU", render: (r) => r.item_code },
        { label: "Cantidad", render: (r) => r.qty },
        { label: "Costo unitario antes", render: (r) => display(r.before) },
        { label: "Costo agregado", render: (r) => display(r.charge) },
        { label: "Costo unitario después", render: (r) => display(r.after) },
      ],
      p.items,
    );
    for (const node of $("cost-review").querySelectorAll(".table-wrap")) {
      node.tabIndex = 0;
      node.setAttribute("role", "region");
      node.setAttribute("aria-label", "Distribución de costos de compra");
    }
  }
  function accept(value) {
    if (value.status === "not_found") {
      current = null;
      preview = null;
      $("cost-review").hidden = true;
      $("cost-native").hidden = true;
      $("cost-state").textContent =
        "Intento pendiente de resolver en el servidor.";
      notice(
        "Aún no aparece el comprobante. Actualiza la vista previa y reintenta con la misma clave, o abandona el intento en el servidor antes de preparar otro.",
      );
      return;
    }
    current = value;
    if (value.status === "cancelled" || value.status === "abandoned") {
      preview = null;
      $("cost-review").hidden = true;
      $("cost-native").hidden = true;
      $("cost-state").textContent =
        value.status === "abandoned"
          ? "Intento abandonado en el servidor. Las solicitudes tardías con esta clave quedan bloqueadas. Puedes preparar otra distribución."
          : "El comprobante " +
            value.voucher +
            " fue cancelado en ERPNext. Este intento no se recreará. Puedes preparar otra distribución después de revisar la cancelación.";
      notice(
        value.status === "abandoned"
          ? "Abandono confirmado en el servidor."
          : "Cancelación confirmada en el servidor.",
      );
      return;
    }
    draw(value);
    $("cost-confirm").checked = false;
    $("cost-native").hidden = false;
    $("cost-native").href =
      "/desk/landed-cost-voucher/" + encodeURIComponent(value.voucher);
    $("cost-state").textContent =
      value.status === "draft"
        ? "Estimación en borrador: " +
          value.voucher +
          ". Sin efecto en valoración. Puedes ajustar los costos en ERPNext, guardar y consultar el estado aquí para revisarlos antes de enviar."
        : "Distribución enviada: " +
          value.voucher +
          ". ERPNext puede tener recálculos posteriores pendientes. No vuelvas a cargar estos costos.";
    notice(
      value.status === "draft" ? "Estimación guardada." : "Costos enviados.",
    );
  }
  function charge() {
    const row = el("fieldset"),
      legend = el("legend", "Costo de compra");
    const account = el("select"),
      amount = el("input"),
      rate = el("input"),
      description = el("input"),
      currency = el("output");
    account.append(el("option", "Selecciona una cuenta"));
    account.options[0].value = "";
    for (const a of options.accounts) {
      const opt = el("option", a.name);
      opt.value = a.name;
      account.append(opt);
    }
    amount.inputMode = "decimal";
    amount.placeholder = "0.00";
    amount.value = "";
    rate.inputMode = "decimal";
    rate.value = "1";
    description.maxLength = 140;
    const label = (text, node) => {
      const l = el("label", text);
      l.append(node);
      return l;
    };
    account.onchange = () => {
      const a = options.accounts.find((a) => a.name === account.value);
      currency.textContent = a?.account_currency || options.currency;
      rate.value = currency.textContent === options.currency ? "1" : "";
    };
    const remove = el("button", "Quitar costo");
    remove.type = "button";
    remove.className = "secondary";
    remove.onclick = () => {
      row.remove();
      invalidate();
    };
    row.append(
      legend,
      label("Cuenta de gastos incluidos en valoración", account),
      label("Moneda original de la cuenta", currency),
      label("Concepto (por ejemplo, flete)", description),
      label("Importe original", amount),
      label("Tasa: moneda contable por unidad original", rate),
      el(
        "p",
        "Si la cuenta usa la moneda contable, la tasa es 1. Para otra moneda escribe la tasa acordada.",
        "hint",
      ),
      remove,
    );
    row.read = () => ({
      account: account.value,
      currency: currency.textContent,
      description: description.value.trim(),
      amount: W.decimal(amount.value),
      exchange_rate: rate.value.trim().replace(",", "."),
    });
    $("cost-charges").append(row);
  }
  function invalidate() {
    preview = null;
    current = null;
    $("cost-review").hidden = true;
    controls();
  }
  function data() {
    return {
      brand: W.state.brand.brand,
      basis: $("cost-basis").value,
      receipts: [...$("cost-receipts").querySelectorAll("input:checked")]
        .map((n) => options.receipts[Number(n.value)])
        .map((r) => ({ doctype: r.doctype, name: r.name })),
      charges: [...$("cost-charges").children].map((r) => r.read()),
    };
  }
  async function checkStatus() {
    accept(
      await api(
        "landed_costs.status",
        { brand: journal.data.brand, request_id: journal.request_id },
        true,
      ),
    );
  }
  $("cost-refresh").onclick = () =>
    run(() =>
      locked(async () => {
        const value = await api(
          "landed_costs.preview",
          { data: journal.data },
          true,
        );
        persist({ ...journal, plan_hash: value.plan_hash });
        draw(value);
        $("cost-confirm").checked = false;
        notice(
          "Revisa el cálculo actualizado y confirma antes de reintentar la misma clave.",
        );
      }),
    );
  async function send() {
    if (!$("cost-confirm").checked)
      throw new Error("Confirma la revisión antes de reintentar.");
    accept(
      await api(
        "landed_costs.save",
        {
          data: journal.data,
          request_id: journal.request_id,
          plan_hash: journal.plan_hash,
          submit: journal.submit,
        },
        true,
      ),
    );
  }
  async function save(submit) {
    await locked(async () => {
      if (journal)
        throw new Error("Consulta el intento existente antes de continuar.");
      if (!$("cost-confirm").checked)
        throw new Error(
          "Confirma que revisaste los importes y los documentos.",
        );
      persist({
        data: data(),
        request_id: crypto.randomUUID(),
        plan_hash: preview.plan_hash,
        submit,
      });
      await send();
    });
  }
  $("cost-add").onclick = () => {
    charge();
    invalidate();
  };
  $("cost-inputs").oninput = invalidate;
  $("cost-preview").onclick = () =>
    run(async () => {
      const value = await api("landed_costs.preview", { data: data() }, true);
      draw(value);
      $("cost-confirm").checked = false;
    });
  $("cost-draft").onclick = () => run(() => save(0));
  $("cost-send").onclick = () => run(() => save(1));
  $("cost-status").onclick = () => run(() => locked(checkStatus));
  $("cost-retry").onclick = () => run(() => locked(send));
  $("cost-abandon").onclick = () =>
    run(() =>
      locked(async () => {
        accept(
          await api(
            "landed_costs.abandon",
            { brand: journal.data.brand, request_id: journal.request_id },
            true,
          ),
        );
      }),
    );
  $("cost-submit-draft").onclick = () =>
    run(() =>
      locked(async () => {
        if (!$("cost-confirm").checked)
          throw new Error(
            "Confirma que revisaste la estimación actual antes de enviar.",
          );
        accept(
          await api(
            "landed_costs.submit_draft",
            {
              brand: journal.data.brand,
              voucher: current.voucher,
              plan_hash: current.plan_hash,
            },
            true,
          ),
        );
      }),
    );
  $("cost-new").onclick = () =>
    run(() =>
      locked(async () => {
        // A terminal server result must be observed before releasing this browser's attempt.
        await checkStatus();
        if (!current) return;
        localStorage.removeItem(scope);
        journal = null;
        current = null;
        preview = null;
        await enter();
      }),
    );
  async function enter() {
    journal = read();
    preview = null;
    current = null;
    $("cost-review").hidden = true;
    $("cost-native").hidden = true;
    $("cost-state").textContent = "";
    if (journal) {
      W.active(journal.data.brand);
      await checkStatus();
      controls();
      return;
    }
    options = await api(
      "landed_costs.options",
      { brand: W.state.brand.brand },
      true,
    );
    $("cost-receipts").replaceChildren();
    $("cost-charges").replaceChildren();
    for (const [i, r] of options.receipts.entries()) {
      const label = el("label"),
        input = el("input");
      input.type = "checkbox";
      input.value = String(i);
      label.append(
        input,
        document.createTextNode(
          (r.doctype === "Purchase Receipt"
            ? "Recepción"
            : "Factura con stock") +
            " · " +
            r.name +
            " · " +
            r.date,
        ),
      );
      $("cost-receipts").append(label);
    }
    if (!options.receipts.length)
      $("cost-receipts").append(
        el(
          "p",
          "No hay compras enviadas elegibles entre las 50 más recientes de cada tipo. Registra la compra en ERPNext y vuelve a esta sección.",
        ),
      );
    charge();
    controls();
  }
  return { enter, controls };
})();
