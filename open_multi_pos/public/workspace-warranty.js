"use strict";
window.OMPWarranty = (() => {
  const W = window.OMPWorkspace;
  const { $, el, api, run, notice, table, t } = W;
  const scope =
    "omp:warranty:v1:" + location.host + ":" + document.body.dataset.user;
  const labels = {
    Open: "Abierta",
    "Work In Progress": "En revisión",
    Closed: "Cerrada",
    Cancelled: "Anulada",
  };
  let journal = null,
    source = null,
    current = null;
  const read = () => JSON.parse(localStorage.getItem(scope) || "null");
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
    for (const id of ["warranty-load", "warranty-form"])
      $(id)
        .querySelectorAll("button, input, select, textarea")
        .forEach((node) => (node.disabled = blocked));
    $("warranty-new").disabled = blocked;
    $("warranty-save").disabled = W.state.busy;
    $("warranty-recovery").hidden = !journal;
    for (const id of ["warranty-status", "warranty-retry", "warranty-abandon"])
      $(id).disabled = W.state.busy;
    $("warranty-operation").textContent = journal
      ? t("Intento") + " " + journal.data.request_id
      : "";
  }
  function hide() {
    for (const id of ["warranty-load", "warranty-form", "warranty-detail"])
      $(id).hidden = true;
  }
  async function list() {
    const rows = await api("warranty.claims", {
      brand: W.state.brand.brand,
      status: $("warranty-filter").value,
    });
    table($("warranty-list"), [
      {
        label: "Reclamación",
        render: (row) => {
          const button = el("button", row.name, "link-button");
          button.type = "button";
          button.onclick = () => run(() => open(row.name));
          return button;
        },
      },
      { label: "Estado", render: (row) => t(labels[row.status] || row.status) },
      { label: "Fecha", render: (row) => row.complaint_date },
      { label: "Producto", render: (row) => row.item_name || row.item_code },
      { label: "Venta", render: (row) => row.omp_sales_invoice || "" },
    ]);
  }
  function show(claim) {
    current = claim;
    hide();
    $("warranty-detail").hidden = false;
    $("warranty-title").textContent = claim.claim;
    $("warranty-summary").textContent =
      t("Venta") +
      " " +
      claim.invoice +
      " · " +
      (claim.item_name || claim.item_code) +
      " · " +
      t("Reclamo del") +
      " " +
      claim.complaint_date +
      (claim.resolution_date
        ? " · " + t("Cerrada el") + " " + claim.resolution_date
        : "");
    $("warranty-complaint-text").textContent = claim.complaint;
    $("warranty-state").value = claim.claim_status;
    $("warranty-resolution").value = claim.resolution_details;
    $("warranty-note").value = "";
    $("warranty-native").href =
      "/desk/warranty-claim/" + encodeURIComponent(claim.claim);
    $("warranty-notes").replaceChildren(
      ...(claim.notes.length
        ? claim.notes.map((n) => {
            const item = el("li");
            const meta = el("span", n.at + " · " + n.by, "native-label");
            const text = el("p", undefined, "preserve");
            text.textContent = n.text;
            item.append(meta, text);
            return item;
          })
        : [el("li", "Todavía no hay notas de seguimiento.")]),
    );
    $("warranty-detail").scrollIntoView({ block: "nearest" });
  }
  async function open(name) {
    show(
      await api(
        "warranty.detail",
        { brand: W.state.brand.brand, claim_name: name },
        true,
      ),
    );
  }
  async function accept(result) {
    if (result.status === "saved") {
      localStorage.removeItem(scope);
      journal = null;
      notice(
        result.duplicate
          ? "La reclamación ya estaba registrada; no se creó otra."
          : "Reclamación registrada. No se generaron cobros ni movimientos de existencias.",
      );
      show(result);
      await list();
    } else if (result.status === "abandoned") {
      localStorage.removeItem(scope);
      journal = null;
      hide();
      notice("Intento resuelto sin registrar otra reclamación.");
    } else
      notice(
        "Todavía no hay una reclamación registrada. Conserva el intento; puedes consultar, reintentar o resolverlo.",
      );
    controls();
  }
  const reference = () => ({
    brand: journal.data.brand,
    request_id: journal.data.request_id,
  });
  async function submit() {
    let result;
    try {
      result = await api("warranty.create", { data: journal.data }, true);
    } catch (error) {
      controls();
      throw error;
    }
    await accept(result);
  }
  async function loadRecent() {
    const rows = (
      await api("receipt_preview.documents", { brand: W.state.brand.brand })
    ).filter((row) => row.kind === "invoice");
    $("warranty-recent").replaceChildren(
      ...rows.map((row) => new Option(row.label, row.document)),
    );
    if (!rows.length)
      $("warranty-recent").add(
        new Option(t("No hay facturas recientes disponibles"), ""),
      );
  }
  async function enter() {
    journal = read();
    hide();
    if (journal && journal.data.brand !== W.state.brand.brand)
      notice(
        "Hay una reclamación pendiente en otro negocio. Selecciónalo para resolverla.",
        true,
      );
    else if (journal)
      await locked(async () => {
        await accept(await api("warranty.status", reference(), true));
      });
    await list();
    controls();
  }
  $("warranty-filter").onchange = () => run(list);
  $("warranty-new").onclick = () =>
    run(async () => {
      if (read()) throw new Error("Resuelve primero la reclamación pendiente.");
      hide();
      source = null;
      $("warranty-invoice").value = "";
      await loadRecent();
      $("warranty-load").hidden = false;
      $("warranty-recent").focus();
    });
  $("warranty-load").onsubmit = (event) => {
    event.preventDefault();
    run(async () => {
      const brand = W.state.brand.brand;
      const invoice =
        $("warranty-invoice").value.trim() || $("warranty-recent").value;
      if (!invoice)
        throw new Error("Selecciona una factura o escribe su número completo.");
      source = await api("warranty.inspect", { brand, invoice }, true);
      $("warranty-source").textContent =
        t("Venta") +
        " " +
        source.invoice +
        " · " +
        source.posting_date +
        ". " +
        (source.claims.length
          ? t("Reclamaciones previas de esta venta") +
            ": " +
            source.claims.map((c) => c.name).join(", ")
          : t("Sin reclamaciones previas."));
      $("warranty-item").replaceChildren(
        ...source.items.map(
          (row) =>
            new Option(
              row.name + " · " + row.item_code + " · " + row.qty,
              row.row,
            ),
        ),
      );
      const today = new Date().toLocaleDateString("en-CA", {
        timeZone: W.state.boot.settings.time_zone || "America/Bogota",
      });
      $("warranty-date").min = source.posting_date;
      $("warranty-date").max = today;
      $("warranty-date").value = today;
      $("warranty-complaint").value = "";
      $("warranty-form").hidden = false;
      $("warranty-item").focus();
    });
  };
  $("warranty-cancel").onclick = () => {
    source = null;
    hide();
  };
  $("warranty-form").onsubmit = (event) => {
    event.preventDefault();
    run(() =>
      locked(async () => {
        if (journal)
          throw new Error("Resuelve primero la reclamación pendiente.");
        if (!source) throw new Error("Carga primero la factura.");
        const record = {
          data: {
            brand: W.state.brand.brand,
            invoice: source.invoice,
            row: $("warranty-item").value,
            request_id: crypto.randomUUID(),
            complaint: $("warranty-complaint").value.trim(),
            complaint_date: $("warranty-date").value,
          },
        };
        // Persist the attempt before sending; a lost response keeps its key.
        localStorage.setItem(scope, JSON.stringify(record));
        journal = record;
        controls();
        await submit();
      }),
    );
  };
  $("warranty-status").onclick = () =>
    run(() =>
      locked(async () => {
        if (journal)
          await accept(await api("warranty.status", reference(), true));
      }),
    );
  $("warranty-retry").onclick = () =>
    run(() =>
      locked(async () => {
        if (journal) await submit();
      }),
    );
  $("warranty-abandon").onclick = () =>
    run(() =>
      locked(async () => {
        if (journal)
          await accept(await api("warranty.abandon", reference(), true));
      }),
    );
  $("warranty-detail").onsubmit = (event) => {
    event.preventDefault();
    run(async () => {
      try {
        show(
          await api(
            "warranty.update",
            {
              data: {
                brand: W.state.brand.brand,
                claim: current.claim,
                modified: current.modified,
                status: $("warranty-state").value,
                resolution_details: $("warranty-resolution").value.trim(),
                note: $("warranty-note").value.trim(),
              },
            },
            true,
          ),
        );
      } catch (error) {
        if (error.status === 409) {
          const note = $("warranty-note").value;
          await open(current.claim);
          $("warranty-note").value = note;
        }
        throw error;
      }
      notice("Seguimiento guardado.");
      await list();
    });
  };
  return { enter, controls };
})();
