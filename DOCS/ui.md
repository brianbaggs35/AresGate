# The web app's design rules

Every page is built from the same few parts, so a new page looks like the ones before it without
anyone having to remember how. The parts are in `frontend/src/components`; if a page needs
something they don't do, change the part (or add a new one) rather than styling it on the page.

## A page is made of

| Part | Use it for |
| ---- | ---------- |
| `AppPage` | The frame of every page: how wide it may be (`narrow` for a form or a list, `regular` for a page of cards, `wide` for charts and tables), the space around it, and the same gap between everything inside. A page adds no margins of its own. |
| `PageHeader` | The one `h1` of the page, what it is for, and the actions that belong to the whole page. A page under another has a way back above its title (`back`). It can carry an icon and a badge (the integration pages show their status there). |
| `SectionCard` | Every group of settings, every list and every panel: a title, what it is for, actions beside the title, then the content. |
| `StatTile` | One number that matters with its name and a line of context, how it has changed (`delta`) and a small trend line (`trend`). It leads to where the number comes from when given `to`. |
| `FactList` | Facts as labelled values (the versions on the Status page): the label beside its value where there is room, and above it on a phone. |
| `UsageMeter` | How much of something is used: a bar that turns amber from 75% and red from 90%, with the figures in words so the meaning never rests on colour. |

## The dashboard

The first page is built from the parts above and the charts below, in this order, and a page
that grows beside it should keep the order: what needs attention (`SecurityBanner`), the numbers
(`StatTile`), then charts, then lists. The banner is never only a color: each of its four states
has its own icon and words, it announces a change politely (`role="status"`), and it never says
all is quiet while the collectors that would raise an alarm are not working. The time range and
the refresh button sit in the page header; a chart's own filter (the interface for the traffic)
sits in one row above it. The page asks again every 30 seconds with `usePolling`, which waits
while the tab is in the background, and a quiet refresh does not dim the charts, only one that
somebody asked for.

## Incidents

The Incidents pages are built from the same parts. The list is `IncidentCard`s in one column
(each a single link to its incident, with an accent bar in the color of its severity, and a
confidence meter that says *High confidence*, not only 100%); what it is narrowed to lives in the
route's query (`view`, `severity`, `confidence`, `address`), never in component state, so a link
reproduces it. An incident's page reads in the order a person asks: what is it and what can I
do (the header and its buttons), the numbers, why is AresGate sure (`IncidentReasons`: the bar
and the list use the chart palette, in the same order, so a color is always the same reason),
who is involved (`IncidentAddresses`), when (`BarChart`, a stacked bar by program) and then
every signal (`IncidentTimeline`). The status is always an icon and a word
(`IncidentStatusChip`), and the changes are named by what they do (*Resolve*, not *Done*). The
primary action is the one to reach for next, and the page confirms a change in an `output`.
Status looks, wording and the filters' choices are in `src/incidents.ts`.

Verdicts follow the same rule as severity: each is an icon and a name, never only a color
(`VerdictChip`, looks and wording in `src/verdicts.ts`). `VerdictPanel` sits between the reasons
and the chart because it is what you do after you have seen why AresGate is sure: it says what
your verdicts make of the incident, lists the ones that apply with *Take back*, and gives a new
one with three buttons that stack on a phone. A signal your verdicts keep from counting is a
hollow dot and a chip in the timeline, so it reads as less in words and in shape. The list
leaves out the incidents your verdicts quiet, because nothing in them needs you, and says so with
a switch that shows how many; `quieted` is in the route's query like the other choices. The
Settings page (`VerdictsView`) is where verdicts are reviewed, changed (`VerdictDialog`) and
taken back (`ConfirmDialog`, which says how many signals are judged again).

An incident card in the list is a link to the incident with the three verdict buttons under it,
not in it (a link can't hold buttons), in a `<fieldset>` with a hidden legend. A verdict from a
card is about the incident's address, or where it names none the first alert in it, which only
the incident can say, so the card asks for it then. The card says nothing itself: it emits
`judged`, and the list shows a notice with *Undo* (`IncidentsView`), which takes a new verdict
back and changes one that replaced another back to what it was. On a phone the buttons stack
their icon over the name so that all three fit in a row.

## States

A page or panel is always in one of four states, and each has one component:

| State | Part |
| ----- | ---- |
| Loading | `v-skeleton-loader` shaped like what will appear |
| Failed to load | `LoadError`: the reason in words and *Try again*. Leave the retry out only when asking again won't help (a page that doesn't exist). |
| Nothing there | `EmptyState`: what is missing and, in its slot, what to do about it |
| Done | A `v-alert` (`type="success"`) at the top of the page, for a change that was made |

## Asking before something can't be undone

Use `ConfirmDialog` for every confirmation. It says what will happen, names the action on its
button (*Disconnect*, not *OK*), colors the button red when the action removes something
(`destructive`), can't be closed while the action runs (`busy`), and gives the keyboard back to
what opened it. Don't build another. Use an inline panel instead only when the confirmation needs
a form of its own that people should see next to the thing they're changing (removing a passkey
asks for the password).

## Severity and status

`SeverityChip` (info, low, medium, high, critical) and `StatusChip` (integrations) give each level
its own icon and its name as well as a color, so nothing depends on telling colors apart. Take
severities from `src/severity.ts` and don't pick colors by hand.

## Charts

Charts are in `frontend/src/charts`, drawn as SVG with no charting library, so they follow the
rules below exactly and cost nothing to download. Pick the form from what the data is for:

| Part | Use it for |
| ---- | ---------- |
| `BarChart` | Comparing amounts across categories: horizontal for a ranking (the busiest hosts), vertical for amounts by hour or day. Several series go side by side or, with `stacked`, one on top of the other (alerts by severity per hour). |
| `TimeSeriesChart` | How amounts change over time, one line for each series on one scale from zero; `area` washes the area under it. A gap in the data is a gap in the line, never a zero. |
| `HeatmapChart` | How much happens at each place on a grid, such as alerts by hour and day. |
| `SparklineChart` | The shape of how something has been going, beside a number. `StatTile` takes `trend` for one and `delta` for how the number has changed. |

A chart gets its numbers as props and does its own layout, legend, tooltip and table. Say what the
data is for in `title` and `caption`; there is one chart to a card, in a `SectionCard` or on its
own, never two scales on one chart (two measures of different size are two charts).

```vue
<TimeSeriesChart
  title="Blocked connections"
  caption="Per 15 minutes, last 24 hours"
  :times="times"
  :series="[{ id: 'blocked', label: 'Blocked', values }]"
  :loading="refreshing"
/>
```

What every chart does, and a new one must:

- **Color.** A series takes the next of eight hues in a fixed order (`seriesColor` in
  `charts/palette.ts`), so the same thing is the same color on every chart, and one that is
  turned off doesn't repaint the others. There are eight and no more: fold the tail into one
  "Other" (`--chart-other`). How much of something is one hue in five steps (`stepColor`). A
  severity is `severityColor`, and always with its icon and name (`SEVERITY`). The colors are
  CSS variables in `styles/charts.scss`, with their own steps in each theme, checked with the
  data-visualization validator against the cards (`#ffffff` and `#0e1626`) for color blindness
  and contrast. Three light hues (green, yellow, pink) are under 3:1 against white, which is why
  every chart with several series has a legend and a table. Text is never in a series' color.
- **Marks.** Bars at most 24 px thick with a 4 px round end where the data reaches and a square
  one at the baseline, and 2 px of card between bars that touch; lines 2 px; dots 10 px across
  with a 2 px ring of card; an area a 10% wash; gridlines and axes 1 px solid and quiet. A value
  is written only at the end of a bar or a line, never on every point.
- **Legend.** One for two series or more, whose entries turn a series off (one always stays on);
  none for a single series, which the title names.
- **Table.** Every chart can show the same numbers as a table (the button above it), for anyone
  who reads that better, and it is where the exact figures are. Anything a tooltip says is there
  too: tooltips only add.
- **Reading it.** The pointer or a finger reads a category or moment, a line chart with a
  crosshair; the arrow keys, Home, End and Escape do the same from the keyboard, and a hidden live
  region tells a screen reader what the tooltip shows. Each place that answers a pointer is far
  bigger than its mark.
- **Loading and nothing to show.** While fresh data loads (`loading`) the chart stays, dimmed,
  instead of being replaced or jumping. With nothing to draw it says so (`emptyTitle`,
  `emptyDescription`) rather than draw an empty frame.
- **Phones.** A chart draws at the width it has, names only as many ticks and labels as fit and
  drops its end labels when they would crowd. A heatmap keeps its cells touchable and scrolls
  sideways instead of squeezing them.
- **Not yet.** A texture for each series (diagonal hatching) for print and forced-colors, which
  the legend and table stand in for until it lands.

## Rules for any page

- **Words.** Plain language for the person running a home network: say what happened and what to
  do, not how it failed inside. Errors never show a stack trace or a raw response.
- **Icons.** [Lucide](https://lucide.dev), through `@lucide/vue`, passed to Vuetify's `prepend-icon`
  and `icon` as components. Decorative icons are `aria-hidden`.
- **Type.** Vuetify's Material 3 classes: `text-headline-medium` for a page title,
  `text-title-large` for a card's, `text-body-large` and `text-body-medium` for text, with
  `text-medium-emphasis` for secondary text. Numbers that change use `tabular-nums`.
- **Color.** Only theme colors (`primary`, `error`, `success`, `warning`, `info` and the surface
  tokens), so both themes work. A color never says something on its own.
- **Phones.** Everything works at 360 px wide with no sideways scrolling; the menu becomes a bar at
  the bottom and `AppPage` already clears it. Tap targets are at least 44 px, which Vuetify's
  default buttons are.
- **Keyboard.** Every action is reachable and visibly focused; when a view replaces another, move
  the keyboard to where it begins (`SectionCard` has `focusTitle()`).
- **Untrusted text.** Anything another system wrote (a log line, an alert's signature, a host
  name) is shown as plain text, never as HTML.
- **Test ids.** `data-test="…"` on what tests look for. The shared parts have fixed ones
  (`page-heading`, `page-description`, `section-title`, `load-error-message`, `confirm-accept`,
  `confirm-cancel`) so the same page object code works for every page.

## Checking a new page

Add its page object to `frontend/e2e/support/pages`, a spec to `e2e/specs`, an axe check in
`accessibility.spec.ts` (it runs in both themes) and a fit check in `layout.mobile.spec.ts`.
