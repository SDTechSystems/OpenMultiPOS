"""Small Latin American Spanish corrections on Frappe's supported boot hook."""

import json
from pathlib import Path

import frappe


def extend_boot(bootinfo):
    if not str(frappe.local.lang or "").startswith("es"):
        return
    messages = dict(bootinfo.get("__messages") or {})
    messages.update(json.loads((Path(__file__).parent / "public/native-es.json").read_text()))
    bootinfo["__messages"] = messages
