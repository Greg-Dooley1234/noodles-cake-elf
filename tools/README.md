# Adding a fighter

This turns a folder of green-screen art + voice notes into a playable fighter.
Follow the five steps in order. **Every rule below exists because breaking it
shipped a visible bug once** — the reasons are given so you can tell when a rule
genuinely does not apply.

```bash
python3 -m pip install --user pillow numpy scipy soundfile lameenc av faster-whisper
```

---

## Step 0 — assets

Drop the art in `assets/<Name>/`:

```
assets/Max/
  Image Sprites/    one or more 6x3-ish green-screen sheets   (required)
  Card/             portrait for the select screen             (optional)
  Background/       their home stage                           (optional)
  Finishing Scene/  6x3 sheet of an 18-frame pile animation    (optional)
  Voice Call Outs/  .ogg / .m4a / .mp3 voice takes             (optional)
```

## Step 1 — copy the config

```bash
cp tools/fighters/max.json tools/fighters/yourfighter.json
```

`max.json` is a complete worked example. Change `id`, `sheets`, and the art
paths first; you will fill in `poses` in step 3.

## Step 2 — probe (LOOK AT THE ART)

```bash
python3 tools/add_fighter.py probe tools/fighters/yourfighter.json
```

Writes `tools/fighters/_probe_<id>/sheet_*.png` — every cut pose, labelled
`A r0 c2`. **Open them.** You cannot map poses you have not seen, and you must
check the cut quality here: look for holes in the character and green fringing.

It also prints the head width per sheet. That is the scale check (see
*Scale* below).

## Step 3 — map the poses

Fill in `"poses"` using the labels from the montages: `"idle0": ["A", 0, 0]`
means sheet A, row 0, column 0. Add `true` as a fourth item to mirror a cell:
`["B", 1, 3, true]`.

Required: `idle0`, `walk0…`, `crouch`, `block`, `blockLow`, `jumpUp`, `jumpDn`,
`atkL`, `atkH`, `clow`, `atkA`, `hit`, `launch`, `down`, `ko`, `win`,
`spWind`, `spActive`.

Then the specials — `sp1f0…`, `sp2f0…`, `sp3f0…`, `sp4f0…`, `superf0…` —
numbered from 0 with no gaps.

**Everyone gets four specials and a super.** `sp4` is the rising anti-air; a
fighter without one feels broken against jump-ins. Max shipped without it once
and it was immediately noticeable.

Keep `anim` and `sp_phase` consistent with the frames you mapped:

- `anim.sp.sp1 = 4` means `sp1f0`…`sp1f3` must exist.
- `sp_phase.sp1 = [2,1,1]` splits those 4 frames into windup/active/recover and
  **must sum to the frame count**, or playback skips frames. `verify` checks this.

**Use plenty of frames.** A sheet holds ~18 poses; using 6 of them wastes the
art and makes the fighter look stiff. Max uses 49 cells across 7 sheets.

## Step 4 — voices

```bash
python3 tools/add_fighter.py voices tools/fighters/yourfighter.json
```

Prints every take with timings. Pick the clean ones into `voice_clips` as
`{key: [filename, start, end, "expected words"]}`, then map them to moves in
`clipfor`. Clips are loudness-matched to the clips already in the game.

Always re-listen (or re-transcribe) after building: a window that is 0.2 s out
catches the wrong word, and "Perfect take" becoming "But, uh, Alfie" is not
obvious from the config.

## Step 5 — build, verify, play

```bash
python3 tools/add_fighter.py build  tools/fighters/yourfighter.json
python3 tools/add_fighter.py scale  tools/fighters/yourfighter.json   # size check
python3 tools/add_fighter.py verify yourfighter
```

`build` is **idempotent** — running it twice produces a byte-identical file, so
iterate freely. It edits `index.html` in place, so commit before you start and
`git checkout index.html` to undo.

`verify` catches missing poses, frame-count mismatches, an unregistered
fighter, a silent theme and impossible anchors. It cannot see whether the
result *looks* right, so always play-test:

```bash
python3 -m http.server 8000    # then open http://localhost:8000
```

---

## The four rules that cost the most time

### 1. Anchors must track the body, not the silhouette

`anchorX` is where the fighter stands inside the sprite. Using the alpha
centroid makes specials **shudder**: when a film reel, boom mic or beam enters
frame the centroid jumps 100px+ and the character appears to teleport sideways.

`anchor_mode` picks the strategy:

| mode | use when |
|---|---|
| `dark` *(default)* | costume is darker than the effects (black/navy/grey) |
| `feet` | bright costume, poses stay grounded |
| `centre` | sheets with no props or beams |

Verify by eye: in the probe montages the fighter should sit at a consistent
point across the frames of one special.

### 2a. Cells where the generator shrank the character (`cell_scale`)

**This is the most common visual bug and it needs your eyes.** When a cell has to
fit a tower, a building or an explosion into the same square frame, the image
generator draws the *character* smaller to make room. Nothing downstream can
tell that apart from the character simply being further away, so the fighter
appears to shrink and grow mid-move.

```bash
python3 tools/add_fighter.py scale tools/fighters/yourfighter.json
```

That renders every pose at engine scale over a translucent ghost of the idle
pose. Compare heads: if the pose's head is smaller than the ghost's, it needs a
correction. Two-thirds size → about `1.5`.

```json
"cell_scale": { "superf1": 1.60, "superf2": 2.00, "sp2f0": 1.22 }
```

Re-run `scale` afterwards to confirm the heads line up.

Why it is not automatic: I tried. Head-width detection is thrown by raised arms,
beards and hands; body-area and body-height both call a crouch, a tuck or a
mid-air pose "small" when it is perfectly correct, and auto-correcting those
would inflate the fighter absurdly. A wrong automatic correction is worse than
none, so the tool shows you the problem and takes your number.

### 2b. Scale: measure head width, never bbox height

Bbox height varies 15%+ with stance — a fighting crouch is genuinely shorter
than a straight stand. Twice I "corrected" a scale difference that did not
exist and made a fighter grow mid-combo.

The tool measures the **median head width across every cell** of a sheet, which
ignores props, and refuses ratios outside 0.75–1.34 as measurement errors.
Sheets usually all come back `1.0` — that is the expected answer.

### 3. Green costumes need `"green_costume": true`

Otherwise the despill greys out the character's own green (the elf's leaf
armour). The keyer already protects costume green from being cut out — this
flag only controls colour correction.

### 4. Sheets are NOT an even grid

Poses are found as connected shapes, not sliced on a grid, because rows differ
in length (the elf's base sheet has 7 poses in one row and 6 in the others) and
figures drift outside their nominal cell. If `probe` reports a row count you did
not expect, look at the montage before assuming it is wrong.

---

## Writing the unique parts

The pipeline standardises the mechanical work. The character is yours:

- **`chars`** — colours, reach, speed, hp, weight. `glow`/`glow2` tint their
  aura and effects.
- **`moves`** — normals and specials as raw engine JS. Copy the shape from
  `max.json` and change the numbers, names and `onActive` hooks. Projectiles are
  usually drawn in code (see `p.type==='flash'` / `'reel'` in `index.html`)
  rather than being sprites.
- **`theme`** — the stage music. It **must** carry `bpm`, `drums`, `pad`,
  `lead`, `roots`, `chords`, `melA`, `melB`. A theme missing these, or using an
  unlisted instrument, plays **silently** rather than erroring:
  `drums` ∈ four/boombap/soft/bounce · `pad` ∈ warm/airy/saw/square ·
  `lead` ∈ pluck/harp/saw/square.
- **`callouts`** — the shouted lines (used when no voice clip is mapped).
- **`extra_js`** — optional raw JS for a bespoke super cinematic.

### Custom super scenes

If your super drives a screen effect, tick its timer with the **real** `dt`, not
the hitstop-scaled `sdt`. `sdt` is zero during super-freeze, so a scene ticked
with it never expires — that is how Max's FINAL CUT left a white screen stuck on
the display. Clamp gradient stops to 0–1 as well.

Scale particle counts with `gfx.quality` (1 = struggling, 2 = fine); the engine
already sheds load on slower devices and your effect should join in.
