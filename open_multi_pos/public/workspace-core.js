"use strict";
window.OMPWorkspace = (() => {
  const $ = (id) => document.getElementById(id);
  const state = {
    boot: null,
    brand: null,
    view: "home",
    busy: false,
    manual: [],
  };
  let helpIndex = 0;
  const t = (text) =>
    state.boot?.settings.interface_language === "en"
      ? window.OMPWorkspaceEnglish?.[text] || text
      : text;
  function el(tag, text, cls) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = t(String(text));
    if (cls) node.className = cls;
    return node;
  }
  function notice(text, error = false) {
    $("notice").textContent = t(text);
    $("notice").dataset.error = String(error);
    $("notice").hidden = !text;
  }
  async function api(method, args = {}, post = false) {
    const url = "/api/method/open_multi_pos." + method;
    let response;
    try {
      response = await fetch(
        post ? url : url + "?" + new URLSearchParams(args),
        {
          method: post ? "POST" : "GET",
          credentials: "same-origin",
          cache: "no-store",
          headers: post
            ? {
                "Content-Type": "application/json",
                "X-Frappe-CSRF-Token": document.querySelector(
                  'meta[name="csrf-token"]',
                ).content,
              }
            : {},
          body: post ? JSON.stringify(args) : undefined,
          signal: AbortSignal.timeout(20000),
        },
      );
    } catch {
      throw new Error(
        "La conexión se interrumpió. Conserva el intento y consulta su estado antes de repetir la operación.",
      );
    }
    let data;
    try {
      data = await response.json();
    } catch {
      throw new Error(
        "El servidor no pudo responder. Consulta el estado antes de repetir la operación.",
      );
    }
    if (!response.ok) {
      let text =
        "No se pudo completar la operación. Revisa la sesión y los permisos.";
      try {
        const message = JSON.parse(JSON.parse(data._server_messages)[0]);
        text = new DOMParser().parseFromString(message.message, "text/html")
          .body.textContent;
      } catch {}
      const error = new Error(text);
      error.status = response.status;
      throw error;
    }
    return data.message;
  }
  async function run(action) {
    if (state.busy) return;
    state.busy = true;
    $("main").setAttribute("aria-busy", "true");
    $("business-picker").disabled = true;
    window.OMPSales?.controls();
    window.OMPReturns?.controls();
    window.OMPImports?.controls();
    window.OMPLandedCosts?.controls();
    try {
      return await action();
    } catch (error) {
      notice(error.message, true);
    } finally {
      state.busy = false;
      $("main").removeAttribute("aria-busy");
      $("business-picker").disabled = false;
      window.OMPSales?.controls();
      window.OMPReturns?.controls();
      window.OMPImports?.controls();
      window.OMPLandedCosts?.controls();
    }
  }
  function decimal(value) {
    const str = String(value).trim().replace(",", ".");
    if (!/^\d{1,9}(\.\d{1,2})?$/.test(str))
      throw new Error(
        "Escribe un importe con hasta dos decimales, sin separadores de miles.",
      );
    const [whole, fraction = ""] = str.split(".");
    return `${BigInt(whole)}.${fraction.padEnd(2, "0")}`;
  }
  function cents(value) {
    const text = String(value);
    if (!/^-?\d+(\.\d{1,2})?$/.test(text))
      throw new Error("Importe del servidor inválido");
    const negative = text.startsWith("-");
    const [whole, fraction = ""] = text.replace(/^-/, "").split(".");
    const n = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"));
    return negative ? -n : n;
  }
  function money(value, currency) {
    let n = BigInt(value),
      sign = n < 0n ? "-" : "";
    if (n < 0n) n = -n;
    const locale = state.boot?.settings.locale || "es-CO";
    currency = currency || state.brand?.currency || "COP";
    const fmt = new Intl.NumberFormat(locale, {
      style: "currency",
      currency,
      minimumFractionDigits: 2,
    });
    const pieces = fmt.formatToParts(1.1);
    const symbol = pieces.find((p) => p.type === "currency")?.value || currency;
    const separator = pieces.find((p) => p.type === "decimal")?.value || ",";
    const whole = new Intl.NumberFormat(locale, {
      maximumFractionDigits: 0,
    }).format(n / 100n);
    return `${sign}${symbol} ${whole}${separator}${String(n % 100n).padStart(2, "0")}`;
  }
  function help(text, label) {
    const details = el("details", undefined, "help");
    const summary = el("summary", "?");
    summary.setAttribute("aria-label", t("Ayuda sobre") + " " + label);
    const description = el("p", text);
    description.id = "field-help-" + ++helpIndex;
    details.append(summary, description);
    return details;
  }
  function fields(root, definitions) {
    root.replaceChildren();
    for (const f of definitions) {
      const box = el(
        "div",
        undefined,
        "field" +
          (f.type === "checkbox" ? " check-field" : "") +
          (f.wide ? " wide" : ""),
      );
      const label = el("label", f.label);
      label.htmlFor = f.id;
      let input;
      if (f.type === "select") {
        input = el("select");
        for (const option of f.options || [])
          input.add(new Option(t(option[1]), option[0]));
      } else if (f.type === "textarea") input = el("textarea");
      else {
        input = el("input");
        input.type = f.type || "text";
        if (input.type === "password") input.autocomplete = "new-password";
        else input.autocomplete = f.autocomplete || "off";
      }
      input.id = f.id;
      input.name = f.id;
      input.required = !!f.required;
      input.readOnly = !!f.readOnly;
      if (f.min !== undefined) input.min = f.min;
      if (f.max !== undefined) input.max = f.max;
      if (f.minLength) input.minLength = f.minLength;
      if (f.inputMode) input.inputMode = f.inputMode;
      if (f.type === "checkbox") input.checked = !!f.value;
      else input.value = f.value ?? "";
      if (f.type === "checkbox") label.prepend(input);
      box.append(label);
      if (f.type !== "checkbox") box.append(input);
      if (f.help) {
        const tooltip = help(f.help, f.label);
        const heading = el("div", undefined, "field-heading");
        heading.append(label, tooltip);
        box.prepend(heading);
        input.setAttribute("aria-describedby", tooltip.querySelector("p").id);
      }
      root.append(box);
    }
  }
  const value = (id) =>
    $(id).type === "checkbox" ? Number($(id).checked) : $(id).value.trim();
  let dialogSubmit = null;
  function form(title, description, definitions, submit, button = "Guardar") {
    $("dialog-title").textContent = t(title);
    $("dialog-description").textContent = t(description);
    $("dialog-error").hidden = true;
    fields($("dialog-fields"), definitions);
    $("dialog-save").textContent = t(button);
    dialogSubmit = submit;
    $("form-dialog").showModal();
  }
  $("dialog-form").onsubmit = (event) => {
    event.preventDefault();
    if (state.busy) return;
    run(async () => {
      $("dialog-save").disabled = true;
      try {
        await dialogSubmit();
        $("form-dialog").close();
      } catch (error) {
        $("dialog-error").textContent = t(error.message);
        $("dialog-error").hidden = false;
      } finally {
        $("dialog-save").disabled = false;
      }
    });
  };
  $("form-dialog").addEventListener("cancel", (event) => {
    if (state.busy) event.preventDefault();
  });
  for (const id of ["close-dialog", "dialog-cancel"])
    $(id).onclick = () => {
      if (!state.busy) $("form-dialog").close();
    };
  function empty(root, text) {
    root.replaceChildren(el("p", text, "empty"));
  }
  function table(root, columns, rows) {
    if (!rows.length) {
      empty(root, "Todavía no hay registros en este negocio.");
      return;
    }
    const wrap = el("div", undefined, "table-wrap"),
      tab = el("table"),
      head = el("thead"),
      tr = el("tr"),
      body = el("tbody");
    for (const c of columns) {
      const th = el("th", c.label, c.number ? "number" : undefined);
      th.scope = "col";
      tr.append(th);
    }
    head.append(tr);
    tab.append(head, body);
    for (const row of rows) {
      const line = el("tr");
      for (const col of columns) {
        const td = el("td", undefined, col.number ? "number" : undefined);
        const content = col.render(row);
        if (content instanceof Node) td.append(content);
        else td.textContent = content ?? "";
        line.append(td);
      }
      body.append(line);
    }
    wrap.append(tab);
    root.replaceChildren(wrap);
  }
  function needBrand() {
    if (!state.brand)
      throw new Error("Agrega o selecciona un negocio para continuar.");
    return state.brand;
  }
  function active(brand) {
    state.brand =
      state.boot.businesses.find((b) => b.brand === brand) ||
      state.boot.businesses[0] ||
      null;
    if (state.brand) {
      const company = state.boot.companies.find(
        (c) => c.name === state.brand.company,
      );
      state.brand.currency = company?.default_currency || "COP";
      $("business-picker").value = state.brand.brand;
      localStorage.setItem(
        "omp:active-business:" + state.boot.user,
        state.brand.brand,
      );
    }
  }
  function native(root, route, label) {
    const brand = state.brand;
    if (!brand && !route.startsWith("user")) needBrand();
    root.replaceChildren(
      el(
        "p",
        brand
          ? t(label) + ". " + t("Entidad legal") + ": " + brand.company
          : t(label),
        "native-label",
      ),
    );
    const frame = el("iframe");
    frame.title = t(label);
    const options = new URLSearchParams({
      _lang: state.boot.settings.interface_language || "es",
      ...(brand &&
      !["customer", "supplier"].includes(route) &&
      !route.startsWith("user")
        ? { company: brand.company }
        : {}),
    });
    if (brand && route.includes("sales-invoice"))
      options.set("pos_profile", brand.pos_profile);
    frame.src = "/desk/" + route + (route.includes("?") ? "&" : "?") + options;
    frame.onload = () => {
      try {
        const doc = frame.contentDocument;
        let style = doc.getElementById("omp-native-layout");
        if (!style) {
          style = doc.createElement("style");
          style.id = "omp-native-layout";
          style.textContent =
            ".navbar,.desk-sidebar,.standard-sidebar,.body-sidebar-container,.body-sidebar,.desk-dock,.dock-container,.dock{display:none!important}body{--sidebar-width:0px!important;--sidebar-collapsed-width:0px!important}.main-section{margin-left:0!important;padding-left:0!important}.layout-main-section-wrapper{margin-left:0!important}.container{max-width:100%!important}.page-container{padding-top:0!important}";
          doc.head.append(style);
        }
        const app = frame.contentWindow.frappe;
        if (app?.set_route && route.startsWith("query-report/")) {
          app.route_options = { company: brand.company };
        }
      } catch {
        notice(
          "Abre esta herramienta en una sesión del mismo sitio para conservar los permisos.",
          true,
        );
      }
    };
    root.append(frame);
  }
  function translatePage() {
    if (state.boot.settings.interface_language !== "en") return;
    const translate = () => {
      const walker = document.createTreeWalker(
        document.body,
        NodeFilter.SHOW_TEXT,
      );
      while (walker.nextNode()) {
        const node = walker.currentNode;
        if (
          node.parentElement.closest(
            "script,style,textarea,#manual-content,#tour",
          )
        )
          continue;
        const source = node.nodeValue.trim(),
          target = t(source);
        if (target !== source)
          node.nodeValue = node.nodeValue.replace(source, target);
      }
      for (const node of document.querySelectorAll(
        "[placeholder],[aria-label],iframe[title]",
      ))
        for (const attr of ["placeholder", "aria-label", "title"]) {
          const source = node.getAttribute(attr);
          if (source && t(source) !== source)
            node.setAttribute(attr, t(source));
        }
    };
    translate();
    new MutationObserver(translate).observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
    });
  }
  return {
    $,
    state,
    t,
    el,
    notice,
    api,
    run,
    decimal,
    cents,
    money,
    help,
    fields,
    value,
    form,
    empty,
    table,
    needBrand,
    active,
    native,
    translatePage,
  };
})();
