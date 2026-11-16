# The look of AresGate

[ui.md](ui.md) says which parts a page is built from. This page says what they should feel like,
and why, so a new part or page can be judged against something other than taste. The bar is a
monitor you want to open: it answers *is anything wrong?* before you have finished asking, it is
as good on a phone as on a desk, and it is calm unless there is a reason not to be.

## The direction: mission control, calm

A security tool can look like a wall of alarms or like something you trust at a glance. AresGate
takes the second: quiet surfaces, one loud thing at a time, and the loud thing is always the
answer to the question a person came with.

- **One answer first.** Each page opens with the sentence that matters in the biggest type on the
  page (`HeroSurface`: the `StatusHero` on the dashboard, what happened on an incident), then the numbers that back it up, then the detail. The
  order follows the decision a person makes, not the order the data arrived in.
- **Color is a signal, so it is rare.** The page is neutral; red, amber, green and blue mean
  something and only appear where something does. A state is never only a color: it is also an
  icon and a word, in light and dark.
- **Depth, not decoration.** Surfaces get a hairline edge and a faint sheen in dark mode, and the
  page has a faint ambient light behind it, so cards sit *on* something. Nothing glows without a
  reason: the hero glows in the color of its state, the active navigation item glows in the
  primary color, and that is all.
- **Numbers are set to be read.** Inter is loaded with its optical-size axis, and headline
  numbers use tabular figures, so a value that changes does not shift the line it is in.
- **Honest about freshness and about silence.** A page says when it last asked, and a state of
  *all clear* is never shown while the collectors that would raise an alarm are not working.
- **Equal on a phone.** Every page is designed at 390 px first and widened, not shrunk: the same
  answer comes first, vitals sit in a two-column grid with hairlines, and a touch target should be at
  least 44 px.

## Where it comes from

These are ideas borrowed, not looks copied. Each is a product people who watch networks or
systems all day rely on, and each shows something worth keeping.

| Reference | What we keep |
| --------- | ------------ |
| Firewalla | A home audience gets a plain-language answer and one action, not a console. Alarms are things to review and decide, with the decision remembered. |
| GlassWire | Traffic over time is the picture people understand; marks on that picture (an alert, a new device) tie the story to the chart. |
| Linear | Density without clutter: small, confident type, hairline separators, keyboard-first navigation (a command palette), motion that explains rather than entertains. |
| Vercel (Geist) | Neutral surfaces that let a status color carry meaning, tabular numerals, restrained use of gradient. |
| Security operations dashboards in general | Hierarchy by decision (what needs me, what is happening, what is background); severity never by color alone; freshness shown per module; suppressed and muted things stay visible so nobody wonders what is hidden; a confidence shown with what it is made of. |

## Reading for a long time

The incidents and the logs are where people stay. Wazuh's and Elastic Security's alert tables,
Splunk's search and Linear's and GitHub's lists agree on a few things, and these are the
principles taken from them (ideas, not looks):

- **The order of attention is fixed.** What is happening now comes first, then what needs a
  decision, then what is background. A list never buries the first under the others, and a
  quieted item stays one click away.
- **Density is the reader's choice.** A person who looks at forty incidents wants forty close
  together, and one who looks at three wants room. *Comfortable* and *compact* (`DensityToggle`, kept in this browser, applied as
  `data-density` on the page) change only the air around things: nothing is left out in compact, so the
  two never disagree about what is there.
- **Every list works from the keyboard.** `J` and `K` move from item to item, `Enter` opens,
  `X` picks, `/` searches, `Ctrl K` goes anywhere, and `?` lists them (`ShortcutsDialog`). A key
  is only an answer when it is not going into a field and nothing is over the page
  (`useShortcuts`); with Ctrl, ⌘ or Alt it is the browser's.
- **Selection is quiet until it is used.** Boxes are there, and a bar appears only once something
  is picked; a shift-click picks a range.
- **An empty list helps.** It says why it is empty, and offers the next step.
- **Motion explains and can be switched off.** See the rules below.

## Rules for motion

Motion is there to say what changed or what is alive, never to fill time.

- The hero's ring draws once when the page opens; it then breathes slowly (calmly for *All
  clear*, faster, with a ripple, for *Needs you*), and a sweep turns behind it. All of it is
  decoration over words that say the same thing.
- Anything that moves has its own `prefers-reduced-motion: reduce` rule next to it, in the same
  component, written so the specificity beats the animation it turns off. Nothing uses
  `!important`.
- Nothing moves faster than a heartbeat, and nothing loops that has no state to show.
- A loading state is a skeleton the shape of what is coming, not a spinner over a blank page.

## Tokens

The theme (`src/plugins/vuetify.ts`) is the only place a color is chosen; a component refers to
a theme color (`rgb(var(--v-theme-error))`, `rgba(var(--v-theme-primary), 0.16)`) so light and
dark both follow. The extra surface treatment (the ambient light, the card sheen, the active
item glow, tabular figures) is in one cascade layer, `aresgate-components`, in
`src/styles/main.scss`, so a component can override it and Vuetify cannot.

| Token | Use |
| ----- | --- |
| `error`, `warning`, `success`, `info` | The state of the thing: needs you, keep an eye on it, all clear, set up. Always with an icon and words. |
| `primary` | The brand and the one action to reach for. |
| `surface` | Cards; in dark mode with the sheen. |
| `background` | The page, with the ambient light. |

## Checking a change against this

1. Does the page start with its answer, and is that answer a sentence?
2. Take the color away (grayscale): does everything still say what it means?
3. Open it at 390 px wide and at 1280 px, in light and dark.
4. Turn on *reduce motion* in the system: does anything still move?
5. Is anything glowing, gradient or animated that carries no meaning? Remove it.
