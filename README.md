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

## Updating
Replace `index.html` with a newer build and re-deploy (Vercel/Pages auto-update
on push; or re-drag the file if you upload through the website).
