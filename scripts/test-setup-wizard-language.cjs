const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync(
  `${__dirname}/../open_multi_pos/public/setup-wizard-language.js`,
  "utf8",
);

function check(code, selection, initial, expected) {
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
      data: {
        lang: {
          codes_to_names: { es: "Español", en: "English", fr: "Français" },
        },
      },
    },
  };
  vm.runInNewContext(source, { frappe });
  callback();
  assert.equal(field.default, expected);
  assert.equal(field.reqd, 1);
  if (!selection) {
    frappe.wizard = { values: { language: "Français" } };
    field.default = "Français";
    callback();
    assert.equal(field.default, "Français");
  }
}

check("es", undefined, "English", "Español");
check("es-CO", undefined, "English", "Español");
check("es", "Français", "Français", "Français");
check("unsupported", undefined, "English", "English");
check(undefined, undefined, "English", "English");
console.log("Setup wizard language defaults: logic checks passed.");
