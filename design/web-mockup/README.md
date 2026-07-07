# EDAutopilot — Web UI Mockup

Interactive prototype for a redesigned EDAutopilot GUI, styled after an
Airbus A320 MCDU (Multifunction Control Display Unit).

## Files

- `EDAutopilot.dc.html` — interactive prototype (`.dc` component format).
  Contains the layout, styling, and demo logic (mode toggles, keypad,
  scrolling log, Sun Pitch counter).
- `support.js` — runtime library required to render the `.dc` component.
- `uploads/autopilot-interface.png` — final mockup of the full interface.
- `uploads/pasted-*.png` — reference photos of a real A320 MCDU that
  inspired the visual language.

## Design notes

- Palette: near-black background (`#0a0a0a`) with amber accent (`#E8973E`,
  classic phosphor-display color) and blue (`#5f96d6`) for status text.
- Fonts: `IBM Plex Mono` for UI chrome, `VT323` (pixel CRT) for the screens.
- MCDU screens use inner shadow + radial-gradient scanlines + text glow to
  read as CRT displays, with Line Select Keys (LSK) down each side.

This is a visual/interaction reference only; it is not wired into the
Python (Tkinter) application.
