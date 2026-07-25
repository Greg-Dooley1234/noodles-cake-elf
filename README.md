# Noodles, Cake & Elf — a festival-night fighting game

A self-contained browser fighting game. Everything (art, sound, code) lives in
one file: `index.html`. Just open it in a browser to play.

**Roster:** Noodle, Cake, Elf, and Chris the Fly Fisher.

## Play
- Local 2-player (same keyboard) and vs-CPU work anywhere, including opening the
  file directly.
- **Online 2-player** works when the game is served from a real `https://` link
  (e.g. Vercel / GitHub Pages) — title screen → **PLAY ONLINE** → one player
  Hosts and shares a code, the other Joins with it.

## Controls (rebindable in-game: title → CONTROLS, or press C)
- **P1:** A/D move · W jump · S crouch · J light · K heavy · L special · I super
- **P2:** ←/→ move · ↑ jump · ↓ crouch · , light · . heavy · / special · M super
- Hold **back** to block. Double-tap a direction to dash. **B** mutes.

### Gamepad
Any Standard-Mapping controller works. Plug it in and press a button to wake it
up (browsers hide pads until they see one press). The first pad is P1, the second
is P2 — a second pad is also how P2 joins character select.

- **Move:** d-pad or left stick · **X** light · **Y** heavy · **A** special · **B** super
- Shoulders double up: **LB** light · **RB** heavy · **LT** special · **RT** super
- **START** confirm / rematch · **BACK** character select

The pad layout is fixed and isn't rebindable, but it drives whatever keys each
player is bound to — so rebinding on the CONTROLS screen carries over to the pad.

### Mobile
The whole game is playable by touch, from the title screen on. The **left half of
the screen is a floating joystick**: touch anywhere and drag — right/left to walk,
flick up to jump (diagonals give jump-forward), down to crouch, hold back to
block, double-flick to dash. A quick tap passes through to whatever is under it
(menu items, fighter cards), so menus stay tappable. The fight buttons
(LIGHT/HEAVY/SPEC/SUPER) stay on the right; outside a fight the light button is
labelled **OK** and acts as confirm.

- **⛶** top-right toggles fullscreen; the first tap anywhere also requests it.
- Fullscreen removes the browser chrome on Android and desktop. **iOS Safari
  doesn't allow fullscreen for non-video elements** — there, use *Share → Add to
  Home Screen* and launch from the icon to get the same chrome-free result.
- Landscape only. Portrait shows a "rotate your device" prompt, since the stage
  is 16:9 and unplayable in portrait.

## Updating
Replace `index.html` with a newer build and re-deploy (Vercel/Pages auto-update
on push; or re-drag the file if you upload through the website).
