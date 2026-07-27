# Noodles, Cake & Elf — a festival-night fighting game

A browser fighting game. The core game, original art, sound, and code live in
`index.html`; expanded sprite frames live under `assets/`. Open `index.html`
from the repository folder or serve the folder with any static web server.

**Roster:** Noodle, Cake, Elf, Chris the Fly Fisher, Brick Master, Bal, Richie,
Eddie, and Pulse Warden.

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
- Jumps have short-hop control: release jump early to reduce height, and use a
  direction for limited air steering.
- Some heavy signature attacks have one hit of **armor**: they take reduced
  damage and keep moving, but the armor breaks after absorbing that hit.

## Physics and effects

- Fighter motion uses sub-stepped gravity and a strict floor-contact invariant
  to prevent tunnelling below the stage after frame stalls or heavy knockback.
- Sprite crops are calibrated to a shared body scale. Smoke, flame, steam,
  sparks, leaves, mist, and speed slashes are emitted by move events rather
  than render passes, keeping their density stable across display refresh rates.
- Pulse Warden includes 90 scale-calibrated animation frames, an energy-control
  moveset, a custom selection card, and his supplied animated Resonance Citadel
  home stage.
- Fight scenes use adaptive cinematic compositing: layered bloom, coloured
  fighter lights, horizon haze, soft contact shadows, bright motion trails,
  localized impact colour-splitting, filmic grading, and a subtle scan texture.
  Expensive passes automatically reduce when sustained frame rate drops.

## Updating
Replace `index.html` with a newer build and re-deploy (Vercel/Pages auto-update
on push; or re-drag the file if you upload through the website).
