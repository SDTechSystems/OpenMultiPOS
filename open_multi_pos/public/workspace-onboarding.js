"use strict";
window.OMPOnboarding = (() => {
  const W = window.OMPWorkspace,
    { $, el, api, run, notice } = W;
  const scope =
    "omp:setup:v1:" + location.host + ":" + document.body.dataset.user;
  const steps = [
    ["account", "Tu cuenta personal"],
    ["preferences", "Preferencias"],
    ["businesses", "Tus negocios"],
    ["inventory", "Primer producto y existencias"],
    ["receipt", "Recibo y equipo existente"],
    ["recovery", "Respaldo y recuperación"],
  ];
  let current = null;
  function controls() {
    for (const node of document.querySelectorAll(
      "#setup-wizard button,#setup-operation button,#setup-open",
    ))
      node.disabled = W.state.busy || node.dataset.blocked === "true";
  }
  const read = () => JSON.parse(localStorage.getItem(scope) || "null");
  const button = (text, action) => {
    const node = el("button", text, "secondary");
    node.type = "button";
    node.onclick = () => run(action);
    return node;
  };
  const link = (text, href) => {
    const node = el("a", text);
    node.href = href;
    node.target = "_blank";
    node.rel = "noopener";
    return node;
  };
  async function locked(action) {
    if (!navigator.locks || !crypto.randomUUID)
      throw new Error(
        "Usa Chrome o Edge actualizado con almacenamiento local habilitado.",
      );
    return navigator.locks.request(scope, action);
  }
  function pendingView() {
    const root = $("setup-operation");
    const request = read();
    root.replaceChildren();
    root.hidden = !request;
    if (!request) return;
    root.append(
      el("h2", "Hay una configuración pendiente"),
      el(
        "p",
        "Consulta o resuelve este intento antes de crear otra cuenta o negocio. La contraseña no se conserva en el navegador.",
      ),
    );
    root.append(
      button("Consultar configuración pendiente", () => recover(false)),
      button("Reintentar configuración pendiente", retry),
      button("Resolver sin crear otro registro", () => recover(true)),
    );
    controls();
  }
  function accept(value) {
    if (value.status === "not_found") {
      notice(
        "El intento todavía no aparece. Reintenta los mismos datos o resuélvelo en el servidor antes de empezar otro.",
      );
      return false;
    }
    localStorage.removeItem(scope);
    pendingView();
    notice(
      value.restricted
        ? "El registro se guardó, pero tu acceso cambió. Revisa los permisos con administración."
        : value.status === "abandoned"
          ? "Intento resuelto. Las solicitudes tardías con esta clave quedan bloqueadas."
          : "Configuración recuperada sin crear otro registro.",
    );
    return true;
  }
  async function create(action, data, first = false) {
    return locked(async () => {
      if (read())
        throw new Error(
          "Resuelve la configuración pendiente antes de empezar otra.",
        );
      const { password, ...saved } = data;
      const request = {
        request_id: crypto.randomUUID(),
        action,
        data: saved,
        first,
      };
      localStorage.setItem(scope, JSON.stringify(request));
      pendingView();
      const value = await api(
        "onboarding.apply",
        {
          ...request,
          data: { ...saved, ...(password !== undefined ? { password } : {}) },
        },
        true,
      );
      accept(value);
      if (value.restricted)
        throw new Error(
          "La configuración se guardó. Revisa sus permisos antes de continuar.",
        );
      return value.result;
    });
  }
  async function recover(abandon) {
    await locked(async () => {
      const request = read();
      if (!request) return;
      const value = await api(
        "onboarding." + (abandon ? "abandon" : "status"),
        { request_id: request.request_id },
        true,
      );
      if (accept(value)) {
        await W.refreshBoot();
        await W.route(W.state.view);
      }
    });
  }
  async function retry() {
    const request = read();
    if (!request) return;
    const send = async (password) =>
      locked(async () => {
        const latest = read();
        if (!latest || latest.request_id !== request.request_id)
          throw new Error(
            "El intento cambió en otra pestaña. Consulta su estado.",
          );
        const value = await api(
          "onboarding.apply",
          {
            ...latest,
            data: {
              ...latest.data,
              ...(latest.action === "user" ? { password } : {}),
            },
          },
          true,
        );
        if (accept(value)) {
          await W.refreshBoot();
          await W.route(W.state.view);
        }
      });
    if (request.action === "user") {
      W.form(
        "Reintentar el mismo perfil",
        "Se mantienen el correo, rol y negocios del intento. Si la cuenta ya se creó, esta contraseña no la cambia.",
        [
          {
            id: "setup-retry-password",
            label: "Contraseña inicial",
            type: "password",
            minLength: 12,
            required: true,
          },
        ],
        () => send($("setup-retry-password").value),
        "Reintentar perfil",
      );
    } else await send();
  }
  async function update(step, extra = {}) {
    current = await api("onboarding.update", { step, ...extra }, true);
    W.state.boot.setup_active = current.active;
    draw();
  }
  function draw() {
    const root = $("setup-step"),
      nav = $("setup-navigation");
    root.replaceChildren();
    nav.replaceChildren();
    $("setup-wizard").hidden = false;
    const index = Math.max(
      0,
      steps.findIndex(([id]) => id === current.step),
    );
    $("setup-title").textContent = steps[index][1];
    $("setup-count").textContent =
      `${index + 1} de ${steps.length}. ` +
      (current.checks[current.step]
        ? "Requisito registrado."
        : "Hay requisitos pendientes.");
    if (!current.native_ready) {
      root.append(
        el(
          "p",
          "Completa primero el asistente nativo de ERPNext. No se marca como terminado desde esta pantalla.",
        ),
        link("Abrir configuración nativa", "/desk"),
      );
      return;
    }
    if (current.step === "account") {
      root.append(
        el(
          "p",
          "Usa una cuenta personal. La cuenta de instalación se conserva para recuperación; no compartas sus credenciales.",
        ),
      );
      if (!current.checks.account) {
        if (!current.first_claimed && current.can_claim_current)
          root.append(
            button("Usar mi cuenta actual", async () => {
              await create("claim", {});
              await W.refreshBoot();
              await enter();
            }),
          );
        if (!current.first_claimed)
          root.append(
            button("Crear mi cuenta personal", () => W.setupActions.user(true)),
          );
        else
          root.append(
            button("Revisar perfiles en Equipo", () => W.route("team")),
          );
      } else
        root.append(
          el(
            "p",
            "Ya existe una cuenta administrativa personal. Inicia sesión con ella para configurar y operar.",
          ),
          button("Revisar cuentas", () => W.route("team")),
        );
    } else if (current.step === "preferences") {
      root.append(
        el(
          "p",
          `${current.preferences.interface_language} · ${current.preferences.locale} · ${current.preferences.default_currency} · ${current.preferences.time_zone}`,
        ),
        el(
          "p",
          "La moneda se propone para entidades nuevas; no convierte la contabilidad existente.",
        ),
        button("Cambiar preferencias", () => W.route("settings")),
        button("Confirmar estas preferencias", () =>
          update("preferences", { fingerprint: current.hashes.preferences }),
        ),
      );
    } else if (current.step === "businesses") {
      root.append(
        el(
          "p",
          "Configura los dos negocios. Elige la misma entidad legal si comparten contabilidad; usa entidades distintas cuando corresponda. El nombre comercial no determina esa relación.",
        ),
      );
      for (const brand of current.brands) root.append(el("p", brand.name));
      root.append(
        button("Agregar negocio", () => W.setupActions.business()),
        button("Revisar datos del negocio", () => W.route("businesses")),
      );
    } else if (current.step === "inventory") {
      root.append(
        el(
          "p",
          "Crea o importa un producto con precio de venta y registra existencias reales. La preparación detecta al menos un producto propio con stock positivo y precio vigente; no crea una venta de prueba.",
        ),
      );
      for (const brand of current.brands)
        root.append(
          el(
            "p",
            brand.name +
              (brand.inventory_present
                ? ": hay un producto con precio y existencias."
                : ": inventario por preparar."),
          ),
        );
      root.append(
        button("Preparar inventario", () => W.route("inventory")),
        button("Importar catálogo y existencias", () => W.route("imports")),
      );
    } else if (current.step === "receipt") {
      root.append(
        el(
          "p",
          "Revisa una muestra de cada negocio y confirma el contenido. Se conserva el preset de la impresora y el lector existentes. La muestra no registra una venta ni exige otro ensayo físico.",
        ),
      );
      for (const brand of current.brands) {
        const box = el("div", undefined, "field");
        box.append(
          el("h3", brand.name),
          link(
            "Abrir muestra del recibo",
            "/omp_receipt_preview?brand=" + encodeURIComponent(brand.brand),
          ),
        );
        if (brand.receipt_reviewed)
          box.append(el("p", "Muestra confirmada con estos ajustes."));
        else
          box.append(
            button("He revisado esta muestra y el equipo", () =>
              update("receipt", {
                brand: brand.brand,
                fingerprint: brand.receipt_hash,
              }),
            ),
          );
        root.append(box);
      }
      root.append(
        button("Cambiar equipo y opciones de recibo", () =>
          W.route("settings"),
        ),
      );
    } else {
      root.append(
        el(
          "p",
          "En el computador servidor, crea una copia verificada y realiza un ensayo aislado de restauración. Después actualiza esta pantalla. No compartas respaldos ni claves con el programa.",
        ),
        el(
          "p",
          "Copia reciente: " +
            (current.recovery.backup_recent ? "sí" : "pendiente") +
            ". Ensayo de restauración: " +
            (current.recovery.restore_at || "pendiente") +
            ".",
        ),
        button("Ver instrucciones de recuperación", () => W.route("help")),
      );
      const missing = steps
        .filter(([id]) => !current.checks[id])
        .map(([, label]) => label);
      if (missing.length)
        root.append(el("p", "Pendientes: " + missing.join(", ") + "."));
      const finish = button("Terminar preparación", async () => {
        await update("recovery", { finish: true });
        $("setup-wizard").hidden = true;
        $("setup-open").focus();
        notice(
          "Preparación guardada. Conserva el respaldo y abre caja cuando vayas a operar.",
        );
      });
      finish.disabled = missing.length > 0;
      finish.dataset.blocked = String(missing.length > 0);
      root.append(finish);
    }
    if (index > 0)
      nav.append(button("Atrás", () => update(steps[index - 1][0])));
    nav.append(
      button("Actualizar requisitos", async () => {
        current = await api("onboarding.state", {}, true);
        draw();
      }),
    );
    if (index < steps.length - 1)
      nav.append(button("Siguiente", () => update(steps[index + 1][0])));
    nav.append(
      button("Continuar después", () => {
        $("setup-wizard").hidden = true;
        notice(
          "El progreso está guardado en el servidor. Retómalo desde Inicio.",
        );
        $("setup-open").focus();
      }),
    );
    controls();
    $("setup-title").focus();
  }
  async function enter(force = false) {
    pendingView();
    const needs = W.state.boot.first_setup || !W.state.boot.businesses.length;
    $("setup-wizard").hidden = true;
    if (!force && !needs && !W.state.boot.setup_active) return;
    current = await api("onboarding.state", {}, true);
    if (!current.active) await update(current.step || "account");
    else draw();
  }
  $("setup-open").onclick = () => run(() => enter(true));
  return { create, enter, pendingView, controls };
})();
