"use strict";
// Opt-in handling of a scanner that emits a US HID keyboard layout while the
// OS uses another layout. Read physical key codes; never rewrite decoded URLs.
window.OMPScanner = {
  usCharacter(event) {
    if (event.ctrlKey || event.altKey || event.metaKey || event.isComposing)
      return null;
    if (/^Key[A-Z]$/.test(event.code)) {
      const letter = event.code.slice(3);
      const uppercase =
        Boolean(event.shiftKey) !==
        Boolean(event.getModifierState?.("CapsLock"));
      return uppercase ? letter : letter.toLowerCase();
    }
    if (/^Digit[0-9]$/.test(event.code)) {
      const number = Number(event.code.slice(5));
      return event.shiftKey ? ")!@#$%^&*("[number] : String(number);
    }
    const keys = {
      Period: [".", ">"],
      Comma: [",", "<"],
      Space: [" ", " "],
      Semicolon: [";", ":"],
      Slash: ["/", "?"],
      Quote: ["'", '"'],
      Backslash: ["\\", "|"],
      Minus: ["-", "_"],
      Equal: ["=", "+"],
      BracketLeft: ["[", "{"],
      BracketRight: ["]", "}"],
      Backquote: ["`", "~"],
    };
    return keys[event.code]?.[event.shiftKey ? 1 : 0] ?? null;
  },
  attach(input, enabled) {
    input.addEventListener("keydown", (event) => {
      if (!enabled() || event.repeat) return;
      const character = window.OMPScanner.usCharacter(event);
      if (character === null) return;
      event.preventDefault();
      const start = input.selectionStart ?? input.value.length;
      const end = input.selectionEnd ?? start;
      // setSelectionRange is not available for type=search in some browsers.
      input.value =
        input.value.slice(0, start) + character + input.value.slice(end);
      input.setSelectionRange?.(
        start + character.length,
        start + character.length,
      );
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
  },
};
