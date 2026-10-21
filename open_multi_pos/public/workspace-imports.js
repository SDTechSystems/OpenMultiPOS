"use strict";
window.OMPImports = (() => {
  const W = window.OMPWorkspace;
  const { $, el, api, run, notice, table, money, cents } = W;
  const scope =
    "omp:imports:v1:" + location.host + ":" + document.body.dataset.user;
  let journal = null,
    plan = null;
  const read = () => JSON.parse(localStorage.getItem(scope) || "null");
  const args = () => ({ brand: journal.brand, request_id: journal.request_id });
  function save(value) {
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
      return action();
    });
  }
  function controls() {
    for (const id of ["import-file", "import-choose", "import-prepare"])
      $(id).disabled = W.state.busy || !!journal;
    $("import-status").disabled = W.state.busy;
    $("import-status-title").textContent =
      journal?.phase === "prepared"
        ? "Vista previa guardada"
        : "Importación por confirmar";
    $("import-recovery").classList.toggle(
      "warning",
      journal?.phase !== "prepared",
    );
    $("import-recovery").classList.toggle(
      "print-preset",
      journal?.phase === "prepared",
    );
    $("import-retry").hidden = journal?.phase !== "pending";
    $("import-refresh").disabled =
      W.state.busy || journal?.phase !== "prepared";
    $("import-retry").disabled = W.state.busy || journal?.phase !== "pending";
    $("import-abandon").disabled =
      W.state.busy || journal?.phase === "completed";
    $("import-next").disabled = W.state.busy;
    $("import-apply").disabled = W.state.busy || journal?.phase !== "prepared";
    $("import-confirm").disabled =
      W.state.busy || journal?.phase !== "prepared";
    $("import-repeat").disabled = W.state.busy || journal?.phase !== "prepared";
    $("import-recovery").hidden = !journal || journal.phase === "completed";
    $("import-operation").textContent = journal
      ? "Intento " + journal.request_id
      : "";
    if (W.state.view === "imports" && journal)
      $("business-picker").disabled = true;
  }
  function reset() {
    plan = null;
    for (const id of ["import-review", "import-result", "import-errors"])
      $(id).hidden = true;
    $("import-confirm").checked = $("import-repeat").checked = false;
  }
  function drawTable(root, columns, rows, label) {
    table(root, columns, rows);
    const wrap = root.querySelector(".table-wrap");
    if (wrap) {
      wrap.tabIndex = 0;
      wrap.setAttribute("role", "region");
      wrap.setAttribute("aria-label", label);
    }
  }
  function errors(rows) {
    $("import-errors").hidden = false;
    drawTable(
      $("import-error-table"),
      [
        { label: "Fila", render: (row) => row.line },
        { label: "Qué corregir", render: (row) => row.message },
      ],
      rows,
      "Errores del archivo",
    );
    notice(
      "El archivo tiene errores. Corrígelos antes de preparar una nueva vista previa.",
      true,
    );
  }
  async function accept(result) {
    reset();
    if (result.status === "prepared") {
      plan = result.plan;
      $("import-file-name").textContent =
        $("import-file").files[0]?.name ||
        "Vista previa recuperada del servidor; no necesitas cargar el archivo de nuevo.";
      save({ ...journal, phase: "prepared", plan_hash: result.plan_hash });
      $("import-review").hidden = false;
      $("import-summary").textContent =
        plan.business +
        ": " +
        plan.create_count +
        (plan.create_count === 1
          ? " producto nuevo, "
          : " productos nuevos, ") +
        plan.update_count +
        (plan.update_count === 1
          ? " actualización y "
          : " actualizaciones y ") +
        plan.units +
        (plan.units === 1
          ? " unidad a ingresar. Costo total del ingreso: "
          : " unidades a ingresar. Costo total del ingreso: ") +
        money(cents(plan.stock_value), plan.currency) +
        ".";
      $("import-warehouse").textContent =
        "Almacén de destino: " +
        plan.warehouse +
        ". Moneda: " +
        plan.currency +
        ".";
      const labels = {
        crear: "Crear",
        actualizar: "Actualizar",
        ingresar: "Ingresar unidades",
      };
      drawTable(
        $("import-preview-table"),
        [
          { label: "Fila", render: (row) => row.line },
          { label: "Acción", render: (row) => labels[row.accion] },
          {
            label: "Producto / SKU",
            render: (row) => {
              const cell = el("div");
              cell.append(
                el("strong", row.nombre),
                el("p", row.sku_label, "hint"),
              );
              if (row.before.name && row.before.name !== row.nombre)
                cell.append(el("p", "Antes: " + row.before.name, "hint"));
              return cell;
            },
          },
          {
            label: "Código de barras / Grupo",
            render: (row) => {
              const cell = el("div");
              cell.append(
                el("span", row.codigo_barras || "Conservar / sin código nuevo"),
                el("p", row.grupo, "hint"),
              );
              return cell;
            },
          },
          {
            label: "Precio",
            render: (row) => {
              const cell = el(
                "div",
                row.precio
                  ? money(cents(row.precio), plan.currency)
                  : "Sin precio",
              );
              if (row.before.price && row.before.price !== row.precio)
                cell.append(
                  el(
                    "p",
                    "Antes: " + money(cents(row.before.price), plan.currency),
                    "hint",
                  ),
                );
              return cell;
            },
            number: true,
          },
          {
            label: "Ingreso",
            render: (row) =>
              row.cantidad +
              " unidades" +
              (row.costo
                ? ". Costo unitario: " + money(cents(row.costo), plan.currency)
                : ""),
          },
          {
            label: "Existencias",
            render: (row) =>
              "Antes: " + row.stock_before + ". Después: " + row.stock_after,
          },
        ],
        plan.rows,
        "Cambios previstos en el catálogo y las existencias",
      );
      $("import-repeat-warning").hidden = !plan.previous_count;
      $("import-repeat-text").textContent =
        "Este contenido ya se aplicó " +
        plan.previous_count +
        (plan.previous_count === 1
          ? " vez. Última aplicación: "
          : " veces. Última aplicación: ") +
        plan.last_applied_at +
        ". Revisa si corresponde a otra recepción real.";
      notice(
        "Vista previa lista. Revisa todos los cambios antes de aplicarlos.",
      );
    } else if (result.status === "completed") {
      save({ ...journal, phase: "completed" });
      $("import-result").hidden = false;
      $("import-result-summary").textContent =
        result.result.items.length +
        (result.result.items.length === 1
          ? " producto procesado. "
          : " productos procesados. ") +
        (result.result.stock_entry
          ? "Entrada de existencias: " + result.result.stock_entry
          : "No se registraron entradas de existencias.");
      drawTable(
        $("import-result-table"),
        [
          { label: "Fila", render: (row) => row.line },
          { label: "SKU", render: (row) => row.item_code },
          { label: "Acción", render: (row) => row.action },
          { label: "Unidades recibidas", render: (row) => row.qty },
        ],
        result.result.items,
        "Resultado de la importación",
      );
      $("import-native").hidden = !result.result.stock_entry;
      if (result.result.stock_entry)
        $("import-native").href =
          "/desk/stock-entry/" + encodeURIComponent(result.result.stock_entry);
      notice(
        "Importación aplicada. No vuelvas a importar el archivo para recuperar este resultado.",
      );
    } else if (result.status === "abandoned") {
      localStorage.removeItem(scope);
      journal = null;
      notice(
        "Intento resuelto sin aplicar otra importación. Puedes seleccionar un archivo nuevo.",
      );
    } else {
      notice(
        "La preparación no se confirmó. Consulta otra vez o resuelve este intento y vuelve a seleccionar el archivo.",
      );
    }
    controls();
  }
  async function enter() {
    reset();
    await locked(async () => {
      if (journal) {
        if (
          W.state.boot.businesses.some((brand) => brand.brand === journal.brand)
        )
          W.active(journal.brand);
        await accept(await api("imports.status", args(), true));
      }
    });
    controls();
  }
  $("import-choose").onclick = () => $("import-file").click();
  $("import-file").onchange = () => {
    $("import-file-name").textContent =
      $("import-file").files[0]?.name || "Sin archivo seleccionado";
  };
  $("import-template").onclick = () => {
    const blob = new Blob(
      ["\ufeffaccion;sku;nombre;codigo_barras;grupo;precio;cantidad;costo\r\n"],
      { type: "text/csv;charset=utf-8" },
    );
    const url = URL.createObjectURL(blob),
      link = document.createElement("a");
    link.href = url;
    link.download = "plantilla-catalogo.csv";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  $("import-file-form").onsubmit = (event) => {
    event.preventDefault();
    run(() =>
      locked(async () => {
        if (journal)
          throw new Error("Resuelve primero la importación en curso.");
        reset();
        const file = $("import-file").files[0];
        if (
          !file ||
          file.size > 256 * 1024 ||
          !file.name.toLowerCase().endsWith(".csv")
        )
          throw new Error("Selecciona un archivo CSV UTF-8 de hasta 256 KiB.");
        let csv;
        try {
          csv = new TextDecoder("utf-8", { fatal: true }).decode(
            await file.arrayBuffer(),
          );
        } catch {
          throw new Error(
            "El archivo no está en UTF-8. Vuelve a guardarlo como CSV UTF-8 en Excel.",
          );
        }
        save({
          brand: W.state.brand.brand,
          request_id: crypto.randomUUID(),
          phase: "preparing",
        });
        controls();
        const result = await api(
          "imports.preview",
          { data: { ...args(), csv_text: csv } },
          true,
        );
        if (result.status === "invalid") {
          await accept(await api("imports.abandon", args(), true));
          errors(result.errors);
        } else await accept(result);
      }),
    );
  };
  $("import-review").onsubmit = (event) => {
    event.preventDefault();
    run(() =>
      locked(async () => {
        if (
          journal?.phase !== "prepared" ||
          !plan ||
          !$("import-confirm").checked
        )
          throw new Error(
            "Revisa y confirma la vista previa antes de aplicar.",
          );
        if (plan.previous_count && !$("import-repeat").checked)
          throw new Error(
            "Este contenido ya se aplicó. Confirma que corresponde a una recepción o cambios nuevos.",
          );
        save({
          ...journal,
          phase: "pending",
          confirm_repeat: Number($("import-repeat").checked),
        });
        controls();
        await accept(
          await api(
            "imports.apply",
            {
              data: {
                ...args(),
                plan_hash: journal.plan_hash,
                confirm_repeat: journal.confirm_repeat,
              },
            },
            true,
          ),
        );
      }),
    );
  };
  $("import-status").onclick = () =>
    run(() =>
      locked(async () => {
        if (journal) await accept(await api("imports.status", args(), true));
      }),
    );
  $("import-refresh").onclick = () =>
    run(() =>
      locked(async () => {
        if (!journal) return;
        const result = await api("imports.refresh", args(), true);
        if (result.status === "invalid") {
          $("import-review").hidden = true;
          errors(result.errors);
        } else await accept(result);
      }),
    );
  $("import-retry").onclick = () =>
    run(() =>
      locked(async () => {
        if (journal?.phase !== "pending") return;
        await accept(
          await api(
            "imports.apply",
            {
              data: {
                ...args(),
                plan_hash: journal.plan_hash,
                confirm_repeat: journal.confirm_repeat,
              },
            },
            true,
          ),
        );
      }),
    );
  $("import-abandon").onclick = () =>
    run(() =>
      locked(async () => {
        if (journal) await accept(await api("imports.abandon", args(), true));
      }),
    );
  $("import-next").onclick = () =>
    run(() =>
      locked(async () => {
        if (journal?.phase !== "completed")
          throw new Error("Resuelve primero la importación en curso.");
        localStorage.removeItem(scope);
        journal = null;
        reset();
        $("import-file").value = "";
        $("import-file-name").textContent = "Sin archivo seleccionado";
        controls();
      }),
    );
  return { enter, controls };
})();
