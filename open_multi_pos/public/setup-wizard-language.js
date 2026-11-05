(() => {
  // Shop answers for the native persona slide; each one stays editable.
  const SHOP_DEFAULTS = {
    persona_implementing_for: "My own business",
    persona_company_size: "1–10",
    persona_industry: "Retail",
    persona_current_system: "Nothing yet - starting fresh",
    module_accounting: 1,
    module_stock: 1,
  };

  function setLanguage(slides) {
    if (frappe.wizard?.values?.language) return;
    const welcome = slides.find((slide) => slide.name === "welcome");
    const field = welcome?.fields.find(
      (field) => field.fieldname === "language",
    );
    const code = frappe.boot.lang || "";
    const names = frappe.setup.data.lang.codes_to_names;
    const language = names[code] || names[code.split("-")[0]];
    if (field && language) field.default = language;
  }

  function adjustSlide(slide) {
    if (slide?.name === "persona") {
      for (const field of slide.fields)
        if (field.fieldname in SHOP_DEFAULTS)
          field.default = SHOP_DEFAULTS[field.fieldname];
    }
    if (slide?.name === "organization") {
      // ERPNext's demo company fails on the Colombian chart of accounts, and
      // OpenMultiPOS businesses are created from the workspace afterwards.
      const fields = slide.fields;
      const index = fields.findIndex(
        (field) => field.fieldname === "setup_demo",
      );
      if (index >= 0) {
        const start =
          fields[index - 1]?.fieldtype === "Section Break" ? index - 1 : index;
        fields.splice(start, index - start + 1);
      }
      slide.load_chart_of_accounts = loadCharts;
    }
  }

  // ERPNext lists charts in disk order, so the preselected one varies by build.
  // Colombia PUC leaves stock adjustment and round-off accounts empty, and the
  // simple variant has no inventory at all, so a shop starts on the standard chart.
  function shopCharts(charts) {
    if (!charts.includes("Standard")) return charts;
    return [
      "Standard",
      ...charts.filter(
        (chart) => chart !== "Standard" && chart !== "Colombia PUC Simple",
      ),
    ];
  }

  function loadCharts(slide) {
    const country =
      frappe.wizard.values.country || frappe.defaults.get_default("country");
    if (!country) return;
    frappe.call({
      method:
        "erpnext.accounts.doctype.account.chart_of_accounts.chart_of_accounts.get_charts_for_country",
      args: { country, with_standard: true },
      callback(response) {
        if (response.message)
          slide
            .get_input("chart_of_accounts")
            .empty()
            .add_options(shopCharts(response.message));
      },
    });
  }

  // ERPNext registers its slides from its own before_load handler, which may
  // run after this one, so each slide is adjusted as it is added.
  const addSlide = frappe.setup.add_slide;
  if (addSlide)
    frappe.setup.add_slide = function (slide, ...rest) {
      adjustSlide(slide);
      return addSlide.call(frappe.setup, slide, ...rest);
    };

  function preferColombia() {
    const utils = frappe.setup.utils;
    if (!utils?.setup_region_fields || utils.ompPrefersColombia) return;
    const native = utils.setup_region_fields;
    utils.ompPrefersColombia = true;
    // Windows regional settings otherwise guess a neighbouring country.
    utils.setup_region_fields = function (slide) {
      const data = frappe.setup.data.regional_data;
      if (data?.country_info?.Colombia) data.default_country = "Colombia";
      return native.call(this, slide);
    };
  }

  frappe.setup.on("before_load", () => {
    setLanguage(frappe.setup.slides_settings);
    (frappe.setup.slides || []).forEach(adjustSlide);
    preferColombia();
  });
})();
