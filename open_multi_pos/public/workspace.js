"use strict";
(async () => {
  const W = window.OMPWorkspace,
    {
      $,
      state,
      el,
      api,
      run,
      notice,
      fields,
      value,
      form,
      table,
      empty,
      cents,
      money,
      t,
    } = W;
  const views = {
    home: ["Inicio", "Consulta la operación del negocio activo."],
    sales: [
      "Ventas",
      "Escanea productos, identifica su negocio y guarda la venta.",
    ],
    returns: [
      "Devoluciones",
      "Consulta la venta original y registra productos devueltos y reembolsos.",
    ],
    inventory: [
      "Inventario",
      "Crea productos y registra existencias en el almacén correcto.",
    ],
    purchases: [
      "Compras",
      "Gestiona proveedores, pedidos y facturas de compra.",
    ],
    finances: [
      "Finanzas",
      "Registra y consulta movimientos de la entidad legal seleccionada.",
    ],
    customers: [
      "Clientes y pedidos",
      "Consulta clientes y gestiona pedidos y entregas.",
    ],
    businesses: ["Negocios", "Edita los datos que identifican a cada negocio."],
    team: ["Equipo", "Crea perfiles y asigna sus permisos."],
    settings: [
      "Ajustes",
      "Configura idioma, moneda, lector y opciones del recibo.",
    ],
    help: ["Ayuda", "Encuentra instrucciones y tutoriales por sección."],
  };
  const paths = {
    home: "M3 10l9-7 9 7M5 9v11h5v-6h4v6h5V9",
    sales: "M3 4h3l2 12h10l2-8H7M10 21h.01M18 21h.01",
    returns: "M9 4L3 10l6 6M3 10h11a7 7 0 0 1 7 7v3",
    inventory: "M3 7l9-4 9 4-9 4-9-4v10l9 4 9-4V7M12 11v10M8 5l9 4",
    purchases: "M5 3h14v18l-3-2-4 2-4-2-3 2V3M8 8h8M8 12h8M8 16h4",
    finances: "M3 21h18M5 21V10h4v11M11 21V6h4v15M17 21V3h4v18",
    customers:
      "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M22 21v-2a4 4 0 0 0-3-4M16 3a4 4 0 0 1 0 8",
    businesses:
      "M3 21h18M5 21V6l7-3 7 3v15M9 8h1M14 8h1M9 12h1M14 12h1M10 21v-5h4v5",
    team: "M8 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M2 21v-2a6 6 0 0 1 12 0v2M19 8v8M15 12h8",
    settings:
      "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8M10 2h4l1 4 4 1 3 3v4l-4 1-1 4-3 3h-4l-1-4-4-1-3-3v-4l4-1 1-4z",
    help: "M9 8a3 3 0 0 1 6 0c0 3-3 2-3 5M12 17h.01M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20",
  };
  const brandFields = [
    [
      "display_name",
      "Nombre comercial",
      "Nombre que verás en el selector y en el recibo.",
    ],
    [
      "legal_name",
      "Razón social en el recibo",
      "Texto de identificación que puedes mostrar en el recibo interno. La entidad contable se edita por separado.",
    ],
    [
      "tax_id",
      "NIT en el recibo",
      "Identificación que se mostrará si activas Mostrar NIT. No emite un documento fiscal.",
    ],
    [
      "phone",
      "Teléfono",
      "Número de contacto del negocio. Su impresión se controla en Ajustes.",
    ],
    [
      "email",
      "Correo electrónico",
      "Correo de contacto. No se enviarán mensajes desde este formulario.",
    ],
    [
      "address",
      "Dirección",
      "Dirección de contacto que puedes incluir en el recibo.",
    ],
    [
      "receipt_footer",
      "Mensaje final",
      "Mensaje breve al final del recibo. Déjalo vacío si no necesitas imprimirlo.",
    ],
    [
      "qr_url",
      "Enlace del QR",
      "Dirección HTTPS del negocio. El QR solo se imprime si lo activas en Ajustes.",
    ],
  ];
  brandFields.splice(1, 0, [
    "sku_prefix",
    "Prefijo de SKU",
    "Iniciales del negocio, de 1 a 8 letras o números en mayúsculas. Se usa con el nombre del producto y un consecutivo. Cambiarlo solo afecta productos nuevos.",
  ]);
  const productKey =
    "omp:product:v1:" + location.host + ":" + document.body.dataset.user;
  let productPending = null;
  function readProduct() {
    productPending = JSON.parse(localStorage.getItem(productKey) || "null");
    $("product-recovery").hidden = productPending?.status !== "pending";
  }
  async function productLocked(action) {
    if (!navigator.locks)
      throw new Error("Usa Chrome o Edge actualizado para crear productos.");
    return navigator.locks.request(productKey, async () => {
      readProduct();
      try {
        return await action();
      } finally {
        readProduct();
      }
    });
  }
  async function submitProduct() {
    if (!productPending) return;
    try {
      const result = await api(
        "workspace.create_product",
        { data: productPending.payload },
        true,
      );
      productPending.status = "completed";
      productPending.item_code = result.item_code;
      localStorage.setItem(productKey, JSON.stringify(productPending));
      await inventory();
      notice(
        "Producto creado. SKU: " +
          result.item_code +
          ". Usa Ingresar existencias para registrar unidades.",
      );
      return result;
    } catch (error) {
      if (error.status === 417) {
        localStorage.removeItem(productKey);
        productPending = null;
      }
      throw error;
    }
  }
  $("retry-product").onclick = () => run(() => productLocked(submitProduct));
  window.addEventListener("storage", (event) => {
    if (event.key === productKey) readProduct();
  });
  const receiptOptions = [
    ["legal_name", "Mostrar razón social"],
    ["tax_id", "Mostrar NIT"],
    ["phone", "Mostrar teléfono"],
    ["email", "Mostrar correo electrónico"],
    ["address", "Mostrar dirección"],
    ["footer", "Mostrar mensaje final"],
    ["qr", "Mostrar QR"],
  ];
  let currentBusiness = null,
    currentInventory = [],
    stockPending = null;
  const stockKey =
    "omp:inventory:v1:" + location.host + ":" + document.body.dataset.user;
  function icon(name) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", paths[name]);
    svg.append(path);
    return svg;
  }
  function button(text, action, cls = "secondary") {
    const btn = el("button", text, cls);
    btn.type = "button";
    btn.onclick = action;
    return btn;
  }
  function options() {
    return state.boot.currencies.map((c) => [
      c,
      c === "COP" ? "COP, peso colombiano" : c,
    ]);
  }
  async function refreshBoot() {
    state.boot = await api("workspace.boot");
    let saved;
    try {
      saved = localStorage.getItem("omp:active-business:" + state.boot.user);
    } catch {}
    state.boot.businesses.forEach((b) => {
      b.currency =
        state.boot.companies.find((c) => c.name === b.company)
          ?.default_currency || "COP";
    });
    $("business-picker").replaceChildren(
      ...state.boot.businesses.map((b) => new Option(b.display_name, b.brand)),
    );
    if (!state.boot.businesses.length)
      $("business-picker").add(new Option(t("Agrega tu primer negocio"), ""));
    W.active(saved || state.brand?.brand);
    $("user-name").textContent = state.boot.full_name || state.boot.user;
    document.documentElement.lang =
      state.boot.settings.interface_language === "en"
        ? "en"
        : state.boot.settings.locale.startsWith("es")
          ? state.boot.settings.locale
          : "es-CO";
  }
  function suggestions() {
    try {
      return JSON.parse(state.boot.suggestions || "{}");
    } catch {
      return {};
    }
  }
  function setup() {
    const needs = state.boot.first_setup || !state.boot.businesses.length;
    $("setup").hidden = !needs;
    $("home-content").hidden = !state.brand;
    $("setup-actions").replaceChildren();
    $("setup-suggestions").replaceChildren();
    if (state.boot.first_setup)
      $("setup-actions").append(
        button(
          "Crear mi perfil de administrador",
          () => newUser(true),
          "primary",
        ),
      );
    if (!state.boot.businesses.length)
      $("setup-actions").append(
        button("Agregar negocio", () => newBusiness(), "secondary"),
      );
    for (const name of suggestions().businesses || []) {
      if (!state.boot.businesses.some((b) => b.display_name === name))
        $("setup-suggestions").append(
          button("Configurar " + name, () => newBusiness(name), "quiet"),
        );
    }
  }
  async function home() {
    setup();
    if (!state.brand) return;
    const result = await api("workspace.overview", {
      brand: state.brand.brand,
    });
    $("today-count").textContent = result.count;
    $("today-total").textContent = money(cents(result.total), result.currency);
    $("today-currency").textContent = result.currency;
    table(
      $("recent-sales"),
      [
        { label: "Documento", render: (r) => r.name },
        {
          label: "Tipo",
          render: (r) => (r.is_return ? t("Nota crédito") : t("Venta")),
        },
        { label: "Fecha", render: (r) => r.posting_date },
        { label: "Cliente", render: (r) => r.customer },
        {
          label: "Importe",
          number: true,
          render: (r) => money(cents(r.grand_total), r.currency),
        },
      ],
      result.recent,
    );
  }
  async function inventory() {
    const brand = W.needBrand();
    const result = await api("workspace.inventory", {
      brand: brand.brand,
      text: $("inventory-search").value,
    });
    currentInventory = result.items;
    readProduct();
    $("inventory-warehouse").textContent = "Almacén: " + result.warehouse;
    table(
      $("inventory-table"),
      [
        { label: "Código", render: (r) => r.name },
        { label: "Producto", render: (r) => r.item_name },
        {
          label: "Código de barras",
          render: (r) => r.barcodes.join(", ") || "Sin código",
        },
        { label: "Disponible", number: true, render: (r) => r.qty },
        {
          label: "Precio",
          number: true,
          render: (r) => money(cents(r.price), brand.currency),
        },
        {
          label: "Acciones",
          render: (r) => button("Ingresar", () => receiveStock(r.name)),
        },
      ],
      result.items,
    );
    refreshStock();
  }
  async function business() {
    W.needBrand();
    currentBusiness = await api("workspace.business", {
      brand: state.brand.brand,
    });
    $("business-fields").className = "field-grid";
    fields(
      $("business-fields"),
      brandFields.map(([key, label, help]) => ({
        id: "business-" + key,
        label,
        help,
        value: currentBusiness[key],
        required: key === "display_name",
        type:
          key === "email"
            ? "email"
            : ["address", "receipt_footer"].includes(key)
              ? "textarea"
              : "text",
        wide: ["address", "receipt_footer"].includes(key),
      })),
    );
  }
  function getBusinessData() {
    return {
      brand: currentBusiness.brand,
      ...Object.fromEntries(
        brandFields.map(([key]) => [key, value("business-" + key)]),
      ),
      ...Object.fromEntries(
        receiptOptions.map(([key]) => [
          "receipt_show_" + key,
          Number(!!currentBusiness["receipt_show_" + key]),
        ]),
      ),
    };
  }
  $("business-form").onsubmit = (event) => {
    event.preventDefault();
    run(async () => {
      await api("workspace.save_business", { data: getBusinessData() }, true);
      await refreshBoot();
      await business();
      notice(
        "Perfil del negocio guardado. Los recibos anteriores conservan sus datos.",
      );
    });
  };
  function newBusiness(display = "") {
    form(
      "Agregar negocio",
      "Elige una entidad existente si comparte NIT y contabilidad con otro negocio. Si es distinta, crea una entidad nueva.",
      [
        {
          id: "new-business-name",
          label: "Nombre comercial",
          value: display,
          required: true,
          help: "Nombre que usarás para identificar este negocio en ventas, inventario y recibos.",
        },
        {
          id: "new-business-company",
          label: "Entidad legal",
          type: "select",
          value: "",
          options: [
            ["", "Crear una entidad nueva"],
            ...state.boot.companies.map((c) => [c.name, c.name]),
          ],
          help: "Dos negocios pueden usar la misma entidad legal. Sus cajas, almacenes y recibos se mantienen separados.",
        },
        {
          id: "new-legal-name",
          label: "Nombre de la entidad nueva",
          help: "Completa este campo solo si elegiste crear una entidad. Usa el nombre que corresponde a esa entidad.",
        },
        {
          id: "new-abbr",
          label: "Abreviatura de la entidad nueva",
          help: "Código breve de hasta cinco caracteres para las cuentas y almacenes de esa entidad.",
        },
        {
          id: "new-currency",
          label: "Moneda de la entidad nueva",
          type: "select",
          value: state.boot.settings.default_currency,
          options: options(),
          help: "La moneda se define para esta entidad al crearla. Si eliges una entidad existente, se usa su moneda contable.",
        },
      ],
      async () => {
        const company = value("new-business-company");
        if (!company && (!value("new-legal-name") || !value("new-abbr")))
          throw new Error(
            "Completa el nombre y la abreviatura de la entidad nueva.",
          );
        const result = await api(
          "workspace.create_business",
          {
            data: {
              display_name: value("new-business-name"),
              company,
              legal_name: value("new-legal-name"),
              abbr: value("new-abbr"),
              currency: value("new-currency"),
            },
          },
          true,
        );
        await refreshBoot();
        W.active(result.brand);
        await route("businesses");
        notice("Negocio creado. Revisa sus datos y crea los productos.");
      },
      "Crear negocio",
    );
  }
  $("new-business").onclick = () => newBusiness();
  $("add-product").onclick = () => {
    W.needBrand();
    readProduct();
    if (productPending?.status === "pending") {
      run(() => productLocked(submitProduct));
      return;
    }
    const openedAfter = productPending?.payload.request_id || "";
    form(
      "Nuevo producto",
      state.brand.display_name +
        ". Crea el producto y su precio. Las existencias se registran después.",
      [
        {
          id: "product-code",
          label: "SKU automático",
          readOnly: true,
          value: state.brand.sku_prefix + "-PRODUCTO-…",
          help: "Se genera al guardar con el prefijo del negocio, el nombre sin tildes y un consecutivo. No necesitas escribirlo. El número final lo asigna el servidor.",
        },
        {
          id: "product-name",
          label: "Nombre del producto",
          required: true,
          help: "Nombre que verás al vender y en el recibo.",
        },
        {
          id: "product-barcode",
          label: "Código de barras",
          help: "Escanea el código del empaque o escríbelo. No abre enlaces ni modifica el idioma del teclado.",
        },
        {
          id: "product-price",
          label: "Precio de venta",
          required: true,
          inputMode: "decimal",
          help: "Precio de la lista de este negocio. Usa la moneda del negocio y hasta dos decimales, sin separadores de miles.",
        },
        {
          id: "product-group",
          label: "Grupo de productos",
          type: "select",
          options: state.boot.item_groups.map((g) => [
            g,
            {
              Products: "Productos",
              Services: "Servicios",
              Consumable: "Consumibles",
              "Raw Material": "Materia prima",
              "Sub Assemblies": "Subensambles",
            }[g] || g,
          ]),
          value:
            state.boot.item_groups.find((g) => g === "Products") ||
            state.boot.item_groups[0],
          required: true,
          help: "Agrupa productos similares para organizarlos y aplicar reglas nativas.",
        },
      ],
      async () => {
        const payload = {
          brand: state.brand.brand,
          code: "",
          name: value("product-name"),
          barcode: value("product-barcode"),
          price: W.decimal(value("product-price")),
          item_group: value("product-group"),
          request_id: crypto.randomUUID(),
        };
        return productLocked(async () => {
          if (
            !productPending ||
            (productPending.status !== "pending" &&
              productPending.payload.request_id === openedAfter)
          ) {
            productPending = { payload, status: "pending" };
            localStorage.setItem(productKey, JSON.stringify(productPending));
          }
          return submitProduct();
        });
      },
      "Crear producto",
    );
    const skuPreview = () => {
      const segment =
        $("product-name")
          .value.normalize("NFKD")
          .replace(/[\u0300-\u036f]/g, "")
          .match(/[A-Za-z0-9]+/g)
          ?.join("-")
          .toUpperCase()
          .slice(0, 24)
          .replace(/-+$/, "") || "PRODUCTO";
      $("product-code").value = state.brand.sku_prefix + "-" + segment + "-…";
    };
    $("product-name").addEventListener("input", skuPreview);
    $("product-name").focus();
    window.OMPScanner.attach(
      $("product-barcode"),
      () => !!state.boot.settings.scanner_us,
    );
  };
  function receiveStock(code) {
    W.needBrand();
    refreshStock();
    if (stockPending?.status === "pending") {
      notice("Primero revisa la entrada pendiente.", true);
      return;
    }
    const openedAfter = stockPending?.payload.request_id || "";
    form(
      "Ingresar existencias",
      state.brand.display_name +
        ". Usa este formulario para una entrada directa. Si recibiste una factura de proveedor, usa Compras para conservar esa relación.",
      [
        {
          id: "stock-code",
          label: "Producto",
          type: "select",
          options: currentInventory.map((i) => [
            i.name,
            i.item_name + " / " + i.name,
          ]),
          value: code || currentInventory[0]?.name,
          required: true,
          help: "Producto del negocio activo que vas a ingresar al almacén.",
        },
        {
          id: "stock-qty",
          label: "Unidades recibidas",
          type: "number",
          value: "1",
          min: 1,
          max: 10000,
          required: true,
          help: "Cantidad entera recibida. Esta entrada aumenta existencias y registra su valoración.",
        },
        {
          id: "stock-cost",
          label: "Costo por unidad",
          required: true,
          inputMode: "decimal",
          help: "Costo de cada unidad en la moneda de la entidad. No es el precio de venta.",
        },
      ],
      async () => {
        const qty = Number(value("stock-qty"));
        if (!Number.isInteger(qty) || qty < 1 || qty > 10000)
          throw new Error("Usa una cantidad entera entre 1 y 10000.");
        const payload = {
          brand: state.brand.brand,
          item_code: value("stock-code"),
          qty,
          cost: W.decimal(value("stock-cost")),
          request_id: crypto.randomUUID(),
        };
        await stockLocked(async () => {
          // A form opened before another tab completed cannot create a second receipt.
          if (
            !stockPending ||
            (stockPending.status !== "pending" &&
              stockPending.payload.request_id === openedAfter)
          ) {
            stockPending = { payload, status: "pending" };
            localStorage.setItem(stockKey, JSON.stringify(stockPending));
          }
          await submitStock();
        });
      },
      "Registrar entrada",
    );
  }
  function refreshStock() {
    stockPending = JSON.parse(localStorage.getItem(stockKey) || "null");
    if (stockPending && !stockPending.payload)
      stockPending = { payload: stockPending, status: "pending" };
    $("stock-recovery").hidden = stockPending?.status !== "pending";
  }
  async function stockLocked(action) {
    if (!navigator.locks)
      throw new Error(
        "Usa Chrome o Edge actualizado para registrar inventario.",
      );
    return navigator.locks.request(stockKey, async () => {
      refreshStock();
      try {
        return await action();
      } finally {
        refreshStock();
      }
    });
  }
  async function submitStock() {
    if (!stockPending) return;
    if (stockPending.status === "abandoned") {
      notice("Este intento fue bloqueado. Abre una entrada nueva.");
      return;
    }
    const result = await api(
      "workspace.receive_stock",
      { data: stockPending.payload },
      true,
    );
    stockPending.status = "completed";
    localStorage.setItem(stockKey, JSON.stringify(stockPending));
    await inventory();
    notice("Entrada registrada: " + result.stock_entry + ".");
  }
  $("add-stock").onclick = () => receiveStock();
  $("retry-stock").onclick = () => run(() => stockLocked(submitStock));
  $("resolve-stock").onclick = () =>
    run(() =>
      stockLocked(async () => {
        if (!stockPending || stockPending.status !== "pending") return;
        const result = await api(
          "workspace.resolve_stock",
          { data: stockPending.payload },
          true,
        );
        stockPending.status = result.status;
        localStorage.setItem(stockKey, JSON.stringify(stockPending));
        await inventory();
        notice(
          result.status === "completed"
            ? "La entrada ya estaba registrada: " + result.stock_entry
            : "Intento bloqueado sin registrar otra entrada. Puedes corregir los datos.",
        );
      }),
    );
  window.addEventListener("storage", (event) => {
    if (event.key === stockKey) refreshStock();
  });
  $("inventory-search-form").onsubmit = (event) => {
    event.preventDefault();
    run(inventory);
  };
  async function team() {
    const rows = await api("workspace.team");
    table(
      $("team-table"),
      [
        {
          label: "Nombre",
          render: (r) =>
            button(
              r.full_name,
              () => {
                let root = $("team-native");
                if (!root) {
                  root = el("div", undefined, "native-container");
                  root.id = "team-native";
                  $("view-team").append(root);
                }
                W.native(
                  root,
                  "user/" + encodeURIComponent(r.name),
                  "Editar perfil",
                );
              },
              "quiet",
            ),
        },
        { label: "Correo", render: (r) => r.name },
        {
          label: "Estado",
          render: (r) => (r.enabled ? "Habilitado" : "Deshabilitado"),
        },
      ],
      rows,
    );
  }
  function newUser(first = false) {
    const choices = suggestions().administrators || [];
    form(
      first ? "Crear mi perfil de administrador" : "Crear perfil",
      "La cuenta se guarda en este sitio. No se envían correos ni se publica información personal.",
      [
        {
          id: "user-full-name",
          label: "Nombre",
          value: first ? choices[0] || "" : "",
          required: true,
          help: "Nombre que aparecerá en la cuenta y en la lista del equipo.",
        },
        {
          id: "user-email",
          label: "Correo de acceso",
          type: "email",
          required: true,
          autocomplete: "email",
          help: "Correo único que la persona usará para iniciar sesión.",
        },
        {
          id: "user-password",
          label: "Contraseña inicial",
          type: "password",
          minLength: 12,
          required: true,
          help: "Usa de 12 a 128 caracteres. La persona puede cambiarla desde su perfil. No se guarda en el navegador.",
        },
        {
          id: "user-role",
          label: "Tipo de perfil",
          type: "select",
          options: first
            ? [["admin", "Administrador"]]
            : [
                ["cashier", "Cajero"],
                ["admin", "Administrador"],
              ],
          value: first ? "admin" : "cashier",
          help: "Administrador puede gestionar configuración y perfiles. Cajero solo puede operar las cajas de los negocios asignados.",
        },
        ...state.boot.businesses.map((b, i) => ({
          id: "user-brand-" + i,
          label: "Dar acceso a " + b.display_name,
          type: "checkbox",
          value: 1,
          help: "Crea una terminal para esta persona y asigna los permisos del negocio. El servidor vuelve a comprobarlos en cada operación.",
        })),
      ],
      async () => {
        const result = await api(
          "workspace.create_user",
          {
            data: {
              full_name: value("user-full-name"),
              email: value("user-email"),
              password: $("user-password").value,
              role: value("user-role"),
              brands: state.boot.businesses
                .filter((_, i) => value("user-brand-" + i))
                .map((b) => b.brand),
            },
          },
          true,
        );
        $("user-password").value = "";
        await refreshBoot();
        setup();
        await team();
        notice(
          "Perfil creado. Inicia sesión con esa cuenta para usar sus permisos.",
        );
        return result;
      },
      "Crear perfil",
    );
  }
  $("add-user").onclick = () => newUser(false);
  async function settings() {
    const s = state.boot.settings;
    const recovery = await api("workspace.recovery_status");
    const date = (value) =>
      new Intl.DateTimeFormat(s.locale, {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: s.time_zone,
      }).format(new Date(value));
    $("recovery-backup").textContent = recovery.backup_at
      ? t(
          recovery.backup_recent
            ? "Último respaldo verificado:"
            : "Respaldo pendiente de actualizar:",
        ) +
        " " +
        date(recovery.backup_at)
      : t(
          "No hay un respaldo verificado registrado. Consulta el manual de recuperación.",
        );
    $("recovery-restore").textContent = recovery.restore_at
      ? t("Último ensayo de restauración correcto:") +
        " " +
        date(recovery.restore_at)
      : t("Todavía no hay un ensayo de restauración registrado.");
    fields($("settings-fields"), [
      {
        id: "setting-language",
        label: "Idioma del programa",
        type: "select",
        options: [
          ["es", "Español latinoamericano"],
          ["en", "English"],
        ],
        value: s.interface_language,
        help: "Cambia el idioma de la interfaz. El desarrollo y el manual se mantienen en español latinoamericano.",
      },
      {
        id: "setting-locale",
        label: "Formato regional",
        type: "select",
        options: [
          ["es-CO", "Español, Colombia"],
          ["es-MX", "Español, México"],
          ["es-PE", "Español, Perú"],
          ["es-CL", "Español, Chile"],
          ["en-US", "English, United States"],
        ],
        value: s.locale,
        help: "Controla la presentación de números. No cambia los importes ni convierte monedas.",
      },
      {
        id: "setting-currency",
        label: "Moneda de nuevos negocios",
        type: "select",
        options: options(),
        value: s.default_currency,
        help: "Se usa al crear una entidad nueva. Una entidad con movimientos conserva su moneda contable y sus recibos históricos.",
      },
      {
        id: "setting-zone",
        label: "Zona horaria",
        value: s.time_zone,
        required: true,
        help: "Zona de las nuevas fechas operativas. El valor inicial es America/Bogota. Revisa los cierres abiertos antes de cambiarla.",
      },
      {
        id: "setting-scanner-us",
        label: "Lector con teclado US",
        type: "checkbox",
        value: s.scanner_us,
        help: "Usa los códigos físicos del teclado del lector para evitar que signos o letras se interpreten con otra distribución. Solo afecta los campos de escaneo.",
      },
      {
        id: "setting-terminator",
        label: "Terminador del lector",
        type: "select",
        options: [
          ["Enter", "Enter"],
          ["Tab", "Tab"],
        ],
        value: s.scanner_terminator,
        help: "Tecla que envía tu lector al terminar un código. Inicia la búsqueda y devuelve el foco al campo después de agregar.",
      },
    ]);
    if (!state.brand) {
      empty(
        $("receipt-fields"),
        "Agrega un negocio para configurar su recibo.",
      );
      $("receipt-settings-form").querySelector("button").disabled = true;
      return;
    }
    $("receipt-settings-form").querySelector("button").disabled = false;
    currentBusiness = await api("workspace.business", {
      brand: state.brand.brand,
    });
    fields(
      $("receipt-fields"),
      receiptOptions.map(([key, label]) => ({
        id: "receipt-" + key,
        label,
        type: "checkbox",
        value: currentBusiness["receipt_show_" + key],
        help:
          "Controla este dato solo en los nuevos recibos de " +
          state.brand.display_name +
          ". No modifica los recibos guardados.",
      })),
    );
  }
  $("settings-form").onsubmit = (event) => {
    event.preventDefault();
    run(async () => {
      await api(
        "workspace.save_settings",
        {
          data: {
            interface_language: value("setting-language"),
            locale: value("setting-locale"),
            default_currency: value("setting-currency"),
            time_zone: value("setting-zone"),
            scanner_us: value("setting-scanner-us"),
            scanner_terminator: value("setting-terminator"),
            printer_profile: "jaltech-jal58m",
          },
        },
        true,
      );
      notice(
        "Ajustes guardados. La página se actualizará para aplicar el idioma.",
      );
      location.reload();
    });
  };
  $("open-receipt-preview").onclick = () => {
    window.open(
      "/omp_receipt_preview?brand=" +
        encodeURIComponent(state.brand?.brand || ""),
      "_blank",
      "noopener",
    );
  };
  $("receipt-settings-form").onsubmit = (event) => {
    event.preventDefault();
    run(async () => {
      const data = {
        brand: currentBusiness.brand,
        ...Object.fromEntries(
          brandFields.map(([key]) => [key, currentBusiness[key] || ""]),
        ),
        ...Object.fromEntries(
          receiptOptions.map(([key]) => [
            "receipt_show_" + key,
            value("receipt-" + key),
          ]),
        ),
      };
      await api("workspace.save_business", { data }, true);
      notice(
        "Opciones guardadas para este negocio. Los recibos anteriores conservan sus datos.",
      );
    });
  };
  const nativeModules = {
    purchases: [
      ["Facturas de compra", "purchase-invoice"],
      ["Órdenes de compra", "purchase-order"],
      ["Recepción de mercancía", "purchase-receipt"],
      ["Proveedores", "supplier"],
    ],
    finances: [
      ["Cobros y pagos", "payment-entry"],
      ["Gastos y facturas", "purchase-invoice"],
      ["Asientos contables", "journal-entry"],
      ["Libro mayor", "query-report/General Ledger"],
      ["Cuentas por cobrar", "query-report/Accounts Receivable"],
      ["Cuentas por pagar", "query-report/Accounts Payable"],
      ["Resultados", "query-report/Profit and Loss Statement"],
      ["Plan de cuentas", "account"],
    ],
    customers: [
      ["Clientes", "customer"],
      ["Pedidos de venta", "sales-order"],
      ["Entregas", "delivery-note"],
    ],
  };
  function module(view) {
    W.needBrand();
    const prefix = {
      purchases: "purchase",
      finances: "finance",
      customers: "customer",
    }[view];
    const tools = $(prefix + "-tools");
    tools.replaceChildren();
    for (const [label, route] of nativeModules[view]) {
      const btn = button(label, () => {
        for (const b of tools.children) b.classList.remove("active");
        btn.classList.add("active");
        W.native($(prefix + "-native"), route, label);
      });
      tools.append(btn);
    }
    tools.firstElementChild.classList.add("active");
    W.native(
      $(prefix + "-native"),
      nativeModules[view][0][1],
      nativeModules[view][0][0],
    );
  }
  $("business-access").onclick = () =>
    W.native(
      $("business-native"),
      "omp-business-brand/" + encodeURIComponent(state.brand.brand),
      "Accesos del negocio",
    );
  $("legal-entity").onclick = () =>
    W.native(
      $("business-native"),
      "company/" + encodeURIComponent(state.brand.company),
      "Entidad legal",
    );
  function manual() {
    const query = $("help-search").value.toLocaleLowerCase();
    $("manual-content").replaceChildren();
    for (const section of state.manual) {
      const haystack = JSON.stringify(section).toLocaleLowerCase();
      if (query && !haystack.includes(query)) continue;
      const article = el("article", undefined, "manual-section");
      article.id = "manual-" + section.id;
      article.append(el("h2", section.title), el("p", section.intro));
      const list = el("ol");
      for (const step of section.steps) {
        const li = el("li");
        li.append(
          el("strong", step.title + ". "),
          document.createTextNode(step.body),
        );
        list.append(li);
      }
      article.append(list);
      for (const tip of section.notes || [])
        article.append(el("p", tip, "hint"));
      const details = el("details"),
        summary = el("summary", "Ver captura de esta sección"),
        img = el("img");
      img.src =
        "/assets/open_multi_pos/manual/screenshots/" + section.id + ".png";
      img.alt = "Captura con datos ficticios de " + section.title;
      img.loading = "lazy";
      img.onerror = () => {
        img.hidden = true;
      };
      details.append(summary, img);
      article.append(
        button(
          "Abrir tutorial",
          () => run(() => startTour(section.id)),
          "secondary",
        ),
        details,
      );
      $("manual-content").append(article);
    }
  }
  $("help-search").oninput = manual;
  $("manual-link").onclick = () => run(() => route("help"));
  let tourView = "home",
    tourIndex = 0;
  function tourStep() {
    document
      .querySelectorAll(".tour-target")
      .forEach((n) => n.classList.remove("tour-target"));
    const guide = state.manual.find((g) => g.id === tourView);
    const step = guide.steps[tourIndex];
    $("tour").hidden = false;
    $("tour-count").textContent = tourIndex + 1 + " de " + guide.steps.length;
    $("tour-title").textContent = step.title;
    $("tour-text").textContent = step.body;
    $("tour-back").disabled = tourIndex === 0;
    $("tour-next").textContent = t(
      tourIndex === guide.steps.length - 1 ? "Terminar" : "Siguiente",
    );
    const target = document.querySelector(step.target || "#page-title");
    if (target && !target.closest("[hidden]")) {
      target.classList.add("tour-target");
      target.scrollIntoView({ block: "nearest" });
    }
  }
  async function startTour(view) {
    if (!state.manual.find((g) => g.id === view)) return;
    tourView = view;
    tourIndex = 0;
    if (state.view !== view) await route(view);
    tourStep();
  }
  function closeTour() {
    document
      .querySelectorAll(".tour-target")
      .forEach((n) => n.classList.remove("tour-target"));
    $("tour").hidden = true;
    localStorage.setItem(
      "omp:tutorial:" + (state.boot?.user || "") + ":" + tourView,
      "done",
    );
  }
  $("tour-close").onclick = closeTour;
  $("tour-skip").onclick = closeTour;
  $("tour-back").onclick = () => {
    tourIndex = Math.max(0, tourIndex - 1);
    tourStep();
  };
  $("tour-next").onclick = () => {
    const guide = state.manual.find((g) => g.id === tourView);
    if (++tourIndex >= guide.steps.length) closeTour();
    else tourStep();
  };
  $("tutorial").onclick = () => run(() => startTour(state.view));
  async function route(view) {
    if (!views[view]) view = "home";
    state.view = view;
    location.hash = view;
    for (const [key] of Object.entries(views)) {
      $("view-" + key).hidden = key !== view;
      const btn = document.querySelector(`[data-view="${key}"]`);
      if (btn) {
        if (key === view) btn.setAttribute("aria-current", "page");
        else btn.removeAttribute("aria-current");
      }
    }
    $("page-title").textContent = t(views[view][0]);
    $("page-description").textContent = t(views[view][1]);
    $("sidebar").classList.remove("open");
    $("menu-toggle").setAttribute("aria-expanded", "false");
    notice("");
    if (view === "home") await home();
    else if (view === "sales") {
      W.needBrand();
      await window.OMPSales.enter();
    } else if (view === "returns") {
      W.needBrand();
      await window.OMPReturns.enter();
    } else if (view === "inventory") await inventory();
    else if (view === "businesses") await business();
    else if (view === "team") await team();
    else if (view === "settings") await settings();
    else if (view === "help") manual();
    else module(view);
  }
  for (const [key, [name]] of Object.entries(views)) {
    const btn = el("button");
    btn.type = "button";
    btn.dataset.view = key;
    btn.append(icon(key), el("span", name));
    btn.onclick = () => run(() => route(key));
    $("navigation").append(btn);
    $("tool-options").append(new Option(name));
  }
  document
    .querySelectorAll("[data-go]")
    .forEach((btn) => (btn.onclick = () => run(() => route(btn.dataset.go))));
  $("tool-search").onchange = () => {
    const query = $("tool-search").value.toLocaleLowerCase();
    const key = Object.keys(views).find((k) =>
      t(views[k][0]).toLocaleLowerCase().includes(query),
    );
    if (key) {
      $("tool-search").value = "";
      run(() => route(key));
    }
  };
  $("business-picker").onchange = () =>
    run(async () => {
      W.active($("business-picker").value);
      await route(state.view);
    });
  $("menu-toggle").onclick = () => {
    const open = $("sidebar").classList.toggle("open");
    $("menu-toggle").setAttribute("aria-expanded", String(open));
  };
  $("profile").onclick = () => {
    run(async () => {
      await route("team");
      const root = el("div", undefined, "native-container");
      $("view-team").append(root);
      W.native(
        root,
        "user/" + encodeURIComponent(state.boot.user),
        "Mi perfil",
      );
    });
  };
  $("logout").onclick = () =>
    run(async () => {
      await fetch("/api/method/logout", {
        method: "POST",
        headers: {
          "X-Frappe-CSRF-Token": document.querySelector(
            'meta[name="csrf-token"]',
          ).content,
        },
        credentials: "same-origin",
      });
      location.href = "/login?redirect-to=/omp";
    });
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      $("tool-search").focus();
    }
    if (event.key === "Escape") {
      document
        .querySelectorAll(".help[open]")
        .forEach((n) => n.removeAttribute("open"));
      closeTour();
      $("sidebar").classList.remove("open");
    }
  });
  const actionHelp = {
    calculate:
      "Consulta precios, impuestos y existencias del servidor antes de cobrar.",
    "save-sale":
      "Guarda las facturas y descuenta existencias una sola vez con la clave de este intento.",
    "sale-status": "Busca el resultado guardado sin crear otra venta.",
    "sale-retry":
      "Reenvía exactamente la misma operación para recuperar su resultado.",
    "sale-abandon":
      "Recupera la venta existente o bloquea una solicitud tardía. No devuelve dinero.",
    "next-sale":
      "Empieza otra cesta después de confirmar el resultado de la anterior.",
    "print-receipt":
      "Abre el diálogo del navegador con el recibo histórico, sin repetir la venta.",
    "reload-receipt":
      "Vuelve a cargar el recibo guardado si falló su vista previa.",
    "add-product":
      "Crea un producto y su precio para el negocio activo. No agrega unidades.",
    "add-stock":
      "Registra una recepción directa y su costo en el almacén activo.",
    "retry-stock":
      "Consulta o reenvía la entrada pendiente con su misma clave.",
    "resolve-stock":
      "Recupera la entrada existente o impide que llegue después. No crea otra entrada.",
    "new-business":
      "Elige una entidad legal existente o crea una nueva para este negocio.",
    "legal-entity":
      "Abre la empresa contable en ERPNext para editar sus datos nativos.",
    "add-user":
      "Crea una cuenta con rol y negocios asignados. Solo está disponible para administradores.",
    tutorial: "Abre una guía que puedes omitir y repetir cuando quieras.",
    profile: "Abre tu cuenta para cambiar tus datos o contraseña.",
    logout:
      "Cierra esta sesión en el sitio. Conserva los intentos pendientes antes de salir.",
  };
  for (const [id, text] of Object.entries(actionHelp)) $(id).title = text;
  for (const input of document.querySelectorAll("[data-help]")) {
    const label = document.querySelector(`label[for="${input.id}"]`);
    const tooltip = W.help(
      input.dataset.help,
      label?.textContent || "este campo",
    );
    label?.after(tooltip);
    input.setAttribute("aria-describedby", tooltip.querySelector("p").id);
  }
  await run(async () => {
    await refreshBoot();
    W.translatePage();
    const guide = await fetch("/assets/open_multi_pos/workspace-guide.json", {
      cache: "no-store",
    });
    if (!guide.ok)
      throw new Error(
        "No se pudo cargar el manual. Vuelve a abrir esta página.",
      );
    state.manual = await guide.json();
    await route(location.hash.slice(1) || "home");
  });
  window.OMPWorkspace.route = route;
})().catch((error) => {
  document.getElementById("notice").hidden = false;
  document.getElementById("notice").textContent = error.message;
});
