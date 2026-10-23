"use strict";
window.OMPWarranties = (() => {
  const W = window.OMPWorkspace,
    { $, el, api, run, form, value, table, notice } = W;
  const scope =
    "omp:warranty:v1:" + location.host + ":" + document.body.dataset.user;
  const statuses = [
    ["Open", "Abierta"],
    ["Work In Progress", "En revisión"],
    ["Closed", "Cerrada"],
    ["Cancelled", "Cancelada"],
  ];
  let journal = null,
    resolved = false;
  const read = () => JSON.parse(localStorage.getItem(scope) || "null");
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
    for (const node of $("view-warranties").querySelectorAll("button,input"))
      node.disabled = W.state.busy;
    if (journal && W.state.view === "warranties")
      $("business-picker").disabled = true;
  }
  const button = (text, action) => {
    const node = el("button", text, "secondary");
    node.type = "button";
    node.onclick = () => run(action);
    return node;
  };
  function details(record) {
    const root = $("warranty-detail");
    root.replaceChildren(
      el("h2", record.claim),
      el("p", `${record.invoice} · ${record.item_code} · ${record.item_name}`),
      el(
        "p",
        `Recibida: ${record.date}. Estado: ${statuses.find(([key]) => key === record.status)?.[1] || record.status}.`,
      ),
      el("p", record.complaint),
      el("p", record.notes || "Sin notas de seguimiento."),
    );
    if (record.resolved_at)
      root.append(el("p", "Cierre: " + record.resolved_at));
    root.append(
      button("Actualizar seguimiento", async () => {
        form(
          "Seguimiento de garantía",
          "Cambiar el estado no cobra, reembolsa ni mueve existencias. Si otra persona la editó, vuelve a consultarla antes de guardar.",
          [
            {
              id: "warranty-status",
              label: "Estado",
              type: "select",
              options: statuses,
              value: record.status,
              required: true,
            },
            {
              id: "warranty-notes",
              label: "Notas de seguimiento",
              type: "textarea",
              value: record.notes,
            },
          ],
          async () => {
            const updated = await api(
              "warranties.update",
              {
                brand: W.state.brand.brand,
                claim: record.claim,
                modified: record.modified,
                status: value("warranty-status"),
                notes: value("warranty-notes"),
              },
              true,
            );
            details(updated);
            await listing();
            notice("Seguimiento guardado.");
          },
        );
      }),
    );
  }
  async function listing() {
    const records = await api(
      "warranties.listing",
      { brand: W.state.brand.brand },
      true,
    );
    table(
      $("warranty-list"),
      [
        {
          label: "Reclamación",
          render: (r) =>
            button(r.claim, async () =>
              details(
                (
                  await api(
                    "warranties.listing",
                    { brand: W.state.brand.brand, claim: r.claim },
                    true,
                  )
                )[0],
              ),
            ),
        },
        { label: "Venta", render: (r) => r.invoice },
        { label: "Artículo", render: (r) => r.item_name },
        { label: "Fecha", render: (r) => r.date },
        {
          label: "Estado",
          render: (r) =>
            statuses.find(([key]) => key === r.status)?.[1] || r.status,
        },
      ],
      records,
    );
    const wrap = $("warranty-list").querySelector(".table-wrap");
    if (wrap) {
      wrap.tabIndex = 0;
      wrap.setAttribute("role", "region");
      wrap.setAttribute("aria-label", "Reclamaciones recientes");
    }
  }
  async function accept(result) {
    resolved = result.status === "completed" || result.status === "abandoned";
    $("warranty-recovery-text").textContent =
      result.status === "completed"
        ? "Reclamación registrada. Este intento no creará otra."
        : result.status === "abandoned"
          ? "Intento abandonado en el servidor. Las solicitudes tardías quedan bloqueadas."
          : "Intento pendiente. Consulta, reintenta o abandona en el servidor antes de comenzar otro.";
    $("warranty-next").hidden = !resolved;
    $("warranty-retry").hidden = $("warranty-abandon").hidden = resolved;
    if (result.record) details(result.record);
    await listing();
  }
  async function check() {
    await accept(
      await api(
        "warranties.status",
        { brand: journal.brand, request_id: journal.request_id },
        true,
      ),
    );
  }
  async function send() {
    await accept(await api("warranties.create", { data: journal }, true));
    notice("Reclamación registrada sin cobros ni movimientos de stock.");
  }
  async function inspect() {
    const sale = await api(
      "warranties.inspect",
      { brand: W.state.brand.brand, invoice: value("warranty-invoice") },
      true,
    );
    form(
      "Nueva reclamación",
      "Registra el motivo. La cobertura se revisa según las condiciones acordadas; esta pantalla no inventa periodos ni plazos de garantía.",
      [
        {
          id: "warranty-row",
          label: "Artículo de la venta",
          type: "select",
          options: sale.items.map((r) => [r.row, r.item_code + " · " + r.name]),
          required: true,
        },
        {
          id: "warranty-date",
          label: "Fecha de recepción",
          type: "date",
          value: sale.date,
          max: sale.date,
          required: true,
        },
        {
          id: "warranty-complaint",
          label: "Motivo de la reclamación",
          type: "textarea",
          required: true,
        },
      ],
      () =>
        locked(async () => {
          if (journal)
            throw new Error(
              "Resuelve el intento existente antes de continuar.",
            );
          journal = {
            brand: W.state.brand.brand,
            invoice: sale.invoice,
            row: value("warranty-row"),
            date: value("warranty-date"),
            complaint: value("warranty-complaint"),
            request_id: crypto.randomUUID(),
          };
          localStorage.setItem(scope, JSON.stringify(journal));
          $("warranty-create").hidden = true;
          $("warranty-recovery").hidden = false;
          await send();
        }),
      "Registrar reclamación",
    );
  }
  async function enter() {
    journal = read();
    resolved = false;
    const root = $("view-warranties");
    root.replaceChildren(
      el(
        "p",
        "Seguimiento de reclamaciones vinculadas a ventas. No registra reparaciones pagadas, reembolsos ni movimientos de inventario.",
      ),
    );
    const create = el("div");
    create.id = "warranty-create";
    const label = el("label", "Número de venta original"),
      input = el("input");
    input.id = "warranty-invoice";
    label.htmlFor = input.id;
    create.append(label, input, button("Consultar venta", inspect));
    const recovery = el("div");
    recovery.id = "warranty-recovery";
    const text = el("p");
    text.id = "warranty-recovery-text";
    text.setAttribute("role", "status");
    recovery.append(text);
    for (const [id, title, action] of [
      ["warranty-check", "Consultar intento", () => locked(check)],
      ["warranty-retry", "Reintentar misma reclamación", () => locked(send)],
      [
        "warranty-abandon",
        "Abandonar intento pendiente",
        () =>
          locked(async () =>
            accept(
              await api(
                "warranties.abandon",
                { brand: journal.brand, request_id: journal.request_id },
                true,
              ),
            ),
          ),
      ],
      [
        "warranty-next",
        "Nueva reclamación",
        () =>
          locked(async () => {
            await check();
            if (!resolved) return;
            localStorage.removeItem(scope);
            journal = null;
            await enter();
          }),
      ],
    ]) {
      const node = button(title, action);
      node.id = id;
      recovery.append(node);
    }
    const detail = el("div");
    detail.id = "warranty-detail";
    const list = el("div");
    list.id = "warranty-list";
    const exactLabel = el("label", "Buscar una reclamación por número"),
      exact = el("input");
    exact.id = "warranty-search";
    exactLabel.htmlFor = exact.id;
    root.append(
      create,
      recovery,
      detail,
      el("h2", "Reclamaciones recientes"),
      exactLabel,
      exact,
      button("Buscar reclamación", async () =>
        details(
          (
            await api(
              "warranties.listing",
              { brand: W.state.brand.brand, claim: value("warranty-search") },
              true,
            )
          )[0],
        ),
      ),
      list,
    );
    create.hidden = !!journal;
    recovery.hidden = !journal;
    if (journal) {
      W.active(journal.brand);
      await check();
    } else await listing();
    controls();
  }
  return { enter, controls };
})();
