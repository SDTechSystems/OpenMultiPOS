const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync(
  `${__dirname}/../open_multi_pos/public/setup-wizard-language.js`,
  "utf8",
);

function wizard(code, selection, initial, extra = {}) {
  let callback;
  const field = { fieldname: "language", default: initial, reqd: 1 };
  const frappe = {
    boot: { lang: code },
    wizard: selection ? { values: { language: selection } } : undefined,
    setup: {
      on(event, fn) {
        assert.equal(event, "before_load");
        callback = fn;
      },
      slides_settings: [{ name: "welcome", fields: [field] }],
      slides: [],
      add_slide(slide) {
        this.slides.push(slide);
      },
      utils: extra.utils,
      data: {
        lang: {
          codes_to_names: { es: "Español", en: "English", fr: "Français" },
        },
        regional_data: extra.regional,
      },
    },
  };
  vm.runInNewContext(source, { frappe });
  return { field, frappe, load: () => callback() };
}

function check(code, selection, initial, expected) {
  const { field, frappe, load } = wizard(code, selection, initial);
  load();
  assert.equal(field.default, expected);
  assert.equal(field.reqd, 1);
  if (!selection) {
    frappe.wizard = { values: { language: "Français" } };
    field.default = "Français";
    load();
    assert.equal(field.default, "Français");
  }
}

check("es", undefined, "English", "Español");
check("es-CO", undefined, "English", "Español");
check("es", "Français", "Français", "Français");
check("unsupported", undefined, "English", "English");
check(undefined, undefined, "English", "English");

const persona = {
  name: "persona",
  fields: [
    { fieldname: "persona_industry", reqd: 1 },
    { fieldname: "persona_company_size", reqd: 1 },
    { fieldname: "module_manufacturing" },
  ],
};
const organization = {
  name: "organization",
  fields: [
    { fieldname: "company_name" },
    { fieldtype: "Section Break" },
    { fieldname: "setup_demo", fieldtype: "Check" },
  ],
};
let regionCalls = 0;
const regional = { country_info: { Colombia: {}, Mexico: {} } };
const shop = wizard("es", undefined, "English", {
  regional,
  utils: {
    setup_region_fields() {
      regionCalls += 1;
      return regional.default_country;
    },
  },
});
shop.load();
shop.load();
// ERPNext's before_load handler runs after this script's and maps add_slide.
[persona, organization].map(shop.frappe.setup.add_slide);
assert.equal(shop.frappe.setup.slides.length, 2);
assert.equal(persona.fields[0].default, "Retail");
assert.equal(persona.fields[1].default, "1–10");
assert.equal(persona.fields[0].reqd, 1);
assert.equal(persona.fields[2].default, undefined);
assert.deepEqual(
  organization.fields.map((field) => field.fieldname),
  ["company_name"],
);
assert.equal(shop.frappe.setup.utils.setup_region_fields({}), "Colombia");
assert.equal(regionCalls, 1);

function charts(message) {
  let options;
  const input = {
    empty: () => input,
    add_options(values) {
      options = values;
    },
  };
  shop.frappe.wizard = { values: { country: "Colombia" } };
  shop.frappe.call = ({ callback }) => callback({ message });
  organization.load_chart_of_accounts({ get_input: () => input });
  return Array.from(options);
}
assert.deepEqual(charts(["Colombia PUC Simple", "Colombia PUC", "Standard"]), [
  "Colombia PUC",
  "Standard",
]);
assert.deepEqual(charts(["Standard", "Otro"]), ["Standard", "Otro"]);

console.log("Setup wizard defaults: logic checks passed.");
