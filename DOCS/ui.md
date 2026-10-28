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
| `LookupField` | A choice among what the system itself lists (the interface ntopng should read): a button asks it, with the address and sign-in as filled in so far and before anything is saved, and a select then names each choice with its ID and what it holds. A saved connection asks as the page opens; a failure is said in words and leaves the choice as it was; a saved choice that has gone from the list is flagged and kept, and a choice that has seen nothing says so. |
| `StatTile` | One number that matters with its name and a line of context, how it has changed (`delta`) and a small trend line (`trend`). It leads to where the number comes from when given `to`. |
| `FactList` | Facts as labelled values (the versions on the Status page): the label beside its value where there is room, and above it on a phone. |
| `UsageMeter` | How much of something is used: a bar that turns amber from 75% and red from 90%, with the figures in words so the meaning never rests on colour. |

## The dashboard

The first page is built from the parts above and the charts below, in this order, and a page
that grows beside it should keep the order: what needs attention (`StatusHero`, a `HeroSurface`, with the
numbers that back it up, the `StatTile`s, inside it), what needs a decision (`NeedsYouLane`), then
charts, then lists. The hero is never only a color: each of its four states has its own icon,
label and words, it announces a change politely (it is an `output`), and it never says all is
quiet while the collectors that would raise an alarm are not working. Its ring, glow and sweep
are decoration that stops for anyone who asks their system for less motion
([the look](design.md) has the rules). The time range and the refresh button sit in the page
header; a chart's own filter (the interface for the traffic) sits in one row above it. The page
asks again every 30 seconds with `usePolling`, which waits while the tab is in the background,
and a quiet refresh does not dim the charts, only one that somebody asked for.

The lane under the hero is the three open incidents that most need a decision, the most serious
and surest first (`GET /api/incidents?order=priority`), as the same `IncidentCard`s the Incidents
page has, so a verdict can be given where the question is asked. It is left out when nothing needs
a decision, and when the incidents can't be read the rest of the page still is shown. What it
says after a verdict is `JudgedNotice`, which the Incidents page uses too.

## Incidents

The Incidents pages are built from the same parts. The list is `IncidentCard`s in one column
(each a single link to its incident, with an accent bar in the color of its severity, and a
confidence meter that says *High confidence*, not only 100%); what it is narrowed to lives in the
route's query (`view`, `severity`, `confidence`, `q`), never in component state, so a link
reproduces it (an older link's `address=` is read as `q=address:…`). An incident's page reads in
the order a person asks: what is it and what can I do (the header and its buttons), what happened (a `HeroSurface`, the same surface as the
dashboard's hero: a ring drawn to the confidence, a sentence made from what the incident holds
by `storyOf`, and the numbers inside it), why is AresGate sure (`IncidentReasons`: the bar
and the list use the chart palette, in the same order, so a color is always the same reason),
what was done about it (`ResponseDetails`: a sentence, the bans, what else turned the address away, the steps in
order and what cannot be told; the chip on a card is `ResponseChip`, and like a status it is always an icon and a word,
with the wording and looks in `src/response.ts`), who is involved (`IncidentAddresses`), when (`BarChart`, a stacked bar by program), why the
signals are one incident (`IncidentGrouping`: a line to a fact, the waves and the ports a sweep
touched, with the well-known ones named) and then every signal (`IncidentTimeline`). A card says
what a bot was doing in the same way: a chip for scanning or brute force and, only when they
apply, facts for its waves, ports and neighbouring addresses. The status is always an icon and a word
(`IncidentStatusChip`), and the changes are named by what they do (*Resolve*, not *Done*). The
primary action is the one to reach for next, and the page confirms a change in an `output`.
Status looks, wording and the filters' choices are in `src/incidents.ts`.

The search is `SearchBox`: a labelled text field in a `role="search"` landmark, a panel
behind its help button (a disclosure, not a menu, so it is plain buttons that work with a screen
reader and a thumb) with the saved searches, the ways to search and the searches made before, and one button for each
term the API understood (`terms` in the answer, which is also where the wording of each comes
from, so none of the language is repeated in the web app). What is typed is applied after a
pause, or with Enter or on leaving the box; an error from the API is the field's message, and the
list stays, with a note that it is from the last search that worked (never dimmed: faded text
fails contrast), until the search is fixed. `SearchFacets` is the summary of the results: real
buttons with `aria-pressed`, a row that scrolls sideways on a phone (`contain: inline-size`, or
the width of the choices would widen the page). The slash key is handled by the list page, and
not while a field has the keyboard. A search that names a status or a verdict moves the view to
*All* or switches on the quieted ones, so what the buttons say is true. The Logs page uses the
same `SearchBox` and `SearchFacets` with the words of its own language (`LOG_SEARCH` in
`src/search.ts`). The saved searches are `SavedSearches`, in the panel (so they are read when it
is first opened, not on every visit): a button to use each, a bin to forget it, and a name field
with *Save* (it says *Replace* when the name is taken), shown only while the box holds something
the API understood. Each kind of search says which `scope` it keeps its searches under.

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

Changing many at once is `BulkBar`, the selection in `src/selection.ts`, and a look over in
`BulkDialog`. Each card has a native checkbox (a `<label>` around it makes the corner a target of
44 px; `IncidentCard` emits `select` with whether shift was held), and the bar above the list is
always there, so the way to change many is never found by accident: with none picked it is the
box that picks the page and a line that says so, and with some picked it holds *Status* (a menu)
and the three verdicts, with their icons over their names on a phone. It sticks under the top bar
(`--v-layout-top`) as the list is scrolled. `useSelection` keeps the ids picked, drops the ones
that leave the list, and treats *all that match* as a flag, never as a list, since it is more than
the page shows; the API is then given the list's own filters (`matching`), not ids. A change to
fewer than 10 incidents given a status is made at once, with `BulkNotice` and *Undo*; every other
change goes through `BulkDialog`, which asks the API for a `preview` and says what the answer
means in words (`wouldDo` in `src/bulk.ts`; none of the counting is in the web app). The button
that goes ahead is off while there is nothing to change.

The Logs page (`LogsView`) lists events in `LogTable` on a computer and in `LogCards` below the
`md` breakpoint (the column menu, `LogColumns`, only exists on a computer). The table is a real
`<table>` with a hidden caption and a heading that sticks under the top bar (`--v-layout-top`),
which needs its wrapper to be `overflow: clip`, since `hidden` would stop it sticking; a click
anywhere on a row opens the event unless text was just selected, and the summary in each row is
a button for the keyboard (the arrow keys, `Home` and `End` move between them). `LogVolume` is a
`BarChart` with `selectable`: a click, `Enter` or `Space` on a bar narrows the search to that
time, and a touch needs a second tap on the same bar since the first reads it. The sheet,
`LogDrawer`, is a `v-dialog` shaped by an unscoped style into a sheet at the right (the whole
screen on a phone); `j` and `k` are heard on the window while it is open, because the keyboard
starts in the dialog's own box and not in the card. `RawRecord` colors a record by tokens
(`jsonTokens`) and never with `v-html`, so nothing an integration sent is read as markup. New
events come from `tail()`, which asks for events after the newest on screen (a minute earlier,
and left out by id when already shown) and, while the page is scrolled down, holds them behind a
button rather than moving what is being read. `src/logs.ts` has the columns, the merging and the
formatting, and the tests for it.

Settings > AI (`AiSettingsView`) is one card, "AI provider". At the top is an `AiProviderPicker`:
the four providers as cards that are really a group of radio buttons (the arrow keys move
between them, one is heard as chosen, and the one AresGate asks says *In use*). Under it is an
`AiProviderForm` for the provider that is chosen and no other, with the same things in the same
order for all four: the address or the key as a `SecretField` (written, never shown), for Ollama
Cloud the account (*Free* or *Paid*), the model, what it costs, and *Save*, *Test connection*,
*Fetch models* (only for the ones whose models are whatever they have) and *Remove*; between the
model and the buttons is the `AiUseSwitch` for using AI with this provider, which cannot be
turned on until it is ready. A price is always words and numbers ("$0.10 in, $0.50 out per
million tokens") with how the model is cached and what that costs, what a long prompt costs, the
rough price of reading one incident (also once the cache is warm) and where the price was read; a
model the provider has deprecated says so with a warning icon and words, never colour alone. A
hosted provider's model, and the models an Ollama has, are chosen from a list: a hosted model
shows its price under its name, an Ollama model what it is. Testing or asking for the models
saves what was filled in first, so a person never has to remember to press *Save*; what the save
refused is under the field and moves the keyboard to the first one. How a test went is a status
chip and, when it failed, the reason in an alert that stays until the next try. Looks and wording
for prices and models are in `src/ai.ts`.

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
- **Flags.** A `TimeSeriesChart` takes `marks`, things that happened at a moment: each is a flag
  above the plot with a dashed line down to its time, a link to where it is explained, and a
  tooltip (for the pointer and for keyboard focus) that says what it is. The chart makes room for
  flags only when there are some. Flags less than 28 px apart become one flag at the place of the
  most serious, with a count, and its link goes to that one. A mark outside the chart's time
  stands at the nearest end, so one that began before it is not lost, and the table gains a
  column for them. The dashboard flags the incidents of its window (medium or worse, not
  dismissed, not judged unworthy of a look) on the traffic chart, so a spike can be read against
  what was going on.
- **Not yet.** A texture for each series (diagonal hatching) for print and forced-colors, which
  the legend and table stand in for until it lands.

## The command palette

Ctrl or ⌘ and K, or the *Search* button in the app bar (an icon alone on a phone, which has no such
keys), opens `CommandPalette` from any page: a field and a list of what it can do. It is for going
somewhere without finding the link: every page in the menu, every page of Settings, each group of
incidents, the theme, and, for a whole IP address typed in, *Find incidents about* it. The list
comes from `commands.ts`, which reads `navItems` and `settingsSections`, so **a page that adds
itself to the menu or to Settings is in the palette without anyone touching it**; add a command
there only for something that is not a page.

It is a dialog with a text field and plain links and buttons, not a custom widget: Enter takes the
first result, ArrowDown and ArrowUp walk the rows (up from the first goes back to the field), and
Escape closes it and gives the keyboard back to where it was. How many it found is read out as it
changes. It opens empty each time, keeps one height so the box does not jump while someone types,
and is put away when the sign-in ends. Chord shortcuts (such as `g` then `i`) and verdicts from
the keyboard are not in it yet.

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
  the bottom and `AppPage` already clears it. The bar holds four places and a *More* button that
  opens the rest in a sheet (`BOTTOM_BAR_LIMIT` and `bottomBar()` in `src/navigation.ts`); *More* is
  marked as current while the page is one of them. Tap targets are at least 44 px: on a touch screen
  (`pointer: coarse`) every Vuetify button is made that tall, small ones and icon buttons
  included, in `styles/main.scss`, so a page does not size its own. A list that would push the
  rest of the page far down (the Needs you lane) is swiped through instead, in a row that goes to
  the edges of the screen with the next card showing at the end, and a row of choices that goes
  past the edge (the views of the incident list) fades out there. Keep a page's intro to a line or
  two: a phone shows it above everything else.
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
