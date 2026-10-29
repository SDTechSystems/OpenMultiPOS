frappe.setup.on("before_load", () => {
  if (frappe.wizard?.values?.language) return;
  const welcome = frappe.setup.slides_settings.find(
    (slide) => slide.name === "welcome",
  );
  const field = welcome?.fields.find((field) => field.fieldname === "language");
  const code = frappe.boot.lang || "";
  const names = frappe.setup.data.lang.codes_to_names;
  const language = names[code] || names[code.split("-")[0]];
  if (field && language) field.default = language;
});
