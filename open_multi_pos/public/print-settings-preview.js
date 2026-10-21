/* Native ERPNext extension; the destination enforces administrator permissions. */
frappe.ui.form.on("Print Settings", {
  refresh(frm) {
    if (frappe.user_roles.includes("System Manager")) {
      frm.add_custom_button("Vista previa del recibo", () => {
        window.open("/omp_receipt_preview", "_blank", "noopener");
      });
    }
  },
});
