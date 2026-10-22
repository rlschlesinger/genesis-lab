# Browser lab design

The visual system of the browser lab (`web/`). Every colour, size and radius lives in [`web/src/styles/tokens.css`](../web/src/styles/tokens.css); components use only those names. Decided in 5.5 (D-051); the user's design rules ([CLAUDE.md](../CLAUDE.md)) apply throughout.

## The idea: brightfield microscopy

The lab is for *watching a culture and examining specimens*. Biologists do that on a lit glass slide, with stains that make cells visible: crystal violet (the Gram stain) colours the organisms, safranin (its counter-stain) whatever needs attention, iodine marks starch. The lab borrows that world rather than a generic dashboard's.

**Rejected first draft:** carrying over the run reports' look (near-black background, amber accent, hairline rules, numbered sections, monospace labels). Checked against common generated-interface defaults, it matched three of them at once. Fine for a printed report; not a choice made for this subject.

## Tokens

| Token | Value | Used for |
|---|---|---|
| `--slide` | `#e3eae6` | the page: cool glass, lit from below |
| `--field` | `#f2f6f4` | panels, the plate's clear field |
| `--graticule` | `#c3cfc9` | the plate's grid, borders |
| `--violet` | `#56399a` | crystal violet: organisms, primary actions, the current view |
| `--safranin` | `#be3768` | counter-stain: predators (6.5), deaths, errors, keyboard focus |
| `--iodine` | `#a9741a` | food; "connecting" |
| `--stain-ink` | `#221c30` | text (violet-black, ink on a stained slide) |

Colour never carries meaning alone: the connection dot always has words beside it.

## Type

One variable family, **Recursive**, bundled so the lab works offline:

- **Interface:** Recursive's sans style (`MONO 0`, a touch of `CASL`).
- **Changing numbers** (ticks, counts, energies): the same letters with the monospace axis on (`.num`), plus tabular figures, so digits don't jitter as they change.
- **The wordmark** is the one playful piece: the casual axis at full, slightly slanted, like a label hand-written on a culture plate.
- **Scale:** ratio 1.25 from 16 px (12.8, 16, 20, 25, 31). Sentence case everywhere; no all-caps labels, no eyebrow labels above headings, no arrows on buttons.

## Layout

```
Genesis Lab   World  Analytics  Compare  Lineage            neural, seed 1   ● Live
┌──────────────────────────────────────────┐   ┌──────────────────┐
│  the plate: square, a graticule every    │   │ the specimen      │
│  20 world units (a founder's sight range)│   │ panel (19 rem)    │
└──────────────────────────────────────────┘   └──────────────────┘
Tick 1,501 of 100,000   106 alive                       running
```

- **The plate is the one bold element.** It is sized from the window's height and the world's own proportions, so a world unit is the same length across and down; it is never stretched to fill a column.
- **Asymmetric:** the bench (plate and stage bar) beside a fixed, narrow specimen panel; everything left-aligned to the plate. Below 56 rem wide, the panel moves under the plate.
- **Shape:** the plate has round corners, like a dish; every other surface is square, like cut glass. No other radius exists.
- **The four views are plain-text tabs,** not numbered: they aren't a sequence.

## Behaviour

- **Motion:** only what the user caused (a tab changing, a control responding), with one curve (`--ease`) at 140 ms, and none at all with reduced motion. The organisms are the only things that move on their own.
- **Feedback in place:** connection state in the masthead's status line; errors where they happen; no toasts.
- **Empty states say what to do next.** Errors say what happened and how to fix it, without apologising.

## The live plate (5.6)

- **Organisms:** crystal-violet discs with a pale notch pointing where they're heading; never smaller than 3.5 px on screen.
- **Food:** small iodine dots.
- **The selected organism:** a safranin ring (the counter-stain: the one thing to look at).
- **Trails (off by default):** faint violet lines of the last ~1.6 s, drawn under everything.
- **The grid** zooms and pans with the world, a hairline at every zoom.
- **Hint line** under the plate: how to move, zoom, fit and select, in one sentence.

## Controls and the specimen panel (5.7)

- **Stage controls** under the plate: the primary action (Run or Pause) filled in crystal violet; everything else outlined. Disabled controls fade; nothing the server would refuse is offered.
- **Feedback:** the pressed button names what it's doing ("Pausing", "Saving"); a refusal or a result appears as one line under the controls.
- **The run picker** takes the plate's place, in the same rounded frame: starting a run is putting a culture on the plate.
- **The specimen panel** reads top to bottom as a specimen card: status, body, family, brain, genome.
- **The brain diagram:** nodes shaded by value, connections by the signal they carried, violet for positive and safranin for negative, always with the decision in words and the inputs as numbers beside it.

## Two species (6.5)

- **Prey and predators, as in a Gram stain:** one kind of cell keeps the crystal violet, the other takes the safranin counter-stain. Prey (`--prey`) are violet ovals with a short tail behind them; predators (`--predator`) are larger, rounder safranin cells with a notch at the front, their mouth. Shape and size tell them apart without colour.
- **Energy as how full a cell is:** each cell is a membrane over an interior whose opacity follows its energy against its own reproduction threshold, from pale (starving, never clear) to solid (ready to divide).
- **The selection ring moves to ink** (`--selected`), since pink now means "predator". Keyboard focus stays safranin: it rings controls, not cells.
- **Capture marks:** a thin safranin ring where a predator caught a prey, widening slightly and fading over 1.2 s of real time. The one motion not caused by the user, kept because it marks a real event; with reduced motion it appears and disappears without changing.
- **Counts under the plate** in one item ("4 prey, 18 predators"), the predator count in its stain, so the line never wraps.
- **Analytics:** "Prey and predators" and "Strikes and captures" after the population chart (strikes dashed), and the phase plot last: prey across, predators up, joined in time order, an open circle at the start and a filled one now, drawn in SVG in the time charts' manner.

## Two foods (6.9)

- **Food A in iodine, food B in malachite green** (`--food-a`, `--food-b`): malachite is the spore stain, another stain from the same bench. Food A is a dot and food B a ring, so the two kinds differ in shape as well as colour, and the plate's screen-reader summary counts each kind.
- **Organisms the colour of what they digest:** each is tinted along the line from iodine to malachite by its diet, so a population splitting into specialists would show as two colours on the plate. (A config can't have both predators and two foods, so prey in predator worlds are always violet.)
- **Specimen panel:** "Diet 0.12 (eats A)" and meals of each kind.
- **Analytics:** "Specialists" (shares below 0.2 and above 0.8, the spread dashed) and "Food by kind", after the population chart.

## Analytics (5.8)

- **A column of small multiples** sharing one tick axis: captions on the left (title, unit, what a point covers), charts on the right; only the bottom chart numbers the axis.
- **Series colours** follow the stains: organisms and their behaviour in crystal violet, food and meals in iodine, deaths in safranin; meals dashed so three series stay distinguishable without colour alone.
- **Legends** show the latest values unless the pointer is over a chart.

## Compare and Lineage (5.9)

- **Compare:** two choosers, A edged in solid crystal violet and B in dashed iodine, the same pairing the chart lines use, so colour and dash both say which run is which. "What differs" is a plain table of settings; charts follow in the Analytics layout.
- **Lineage:** a pedigree, read top to bottom: the line of descent on a violet rule from the founder, then the organism (outlined in safranin, as on the plate) with its descendants indented beneath. The dead are drawn in softer ink. Every organism is a button.

## Checked

At 1360 × 860: the plate is square and the World view fits without scrolling. At 390 × 844 (phone): no sideways scrolling on any of the four views, panels stacked under the plate. Lighthouse accessibility 100 on the picker and on a live run with a selection (5.10).
