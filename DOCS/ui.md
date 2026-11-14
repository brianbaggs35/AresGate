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
| `SetupGuideDialog` | Step-by-step instructions in a window over a page (the integration pages use it): a short title for each step, the menus to go through, the exact values to enter, where the result goes, what is easy to get wrong and what was not from the documentation, and the pages it comes from. Fullscreen on a phone; focus moves in, Escape closes it and focus goes back to the button. |
| `StatTile` | One number that matters with its name and a line of context, how it has changed (`delta`) and a small trend line (`trend`). It leads to where the number comes from when given `to`. |
| `FactList` | Facts as labelled values (the versions on the Status page): the label beside its value where there is room, and above it on a phone. |
| `UsageMeter` | How much of something is used: a bar that turns amber from 75% and red from 90%, with the figures in words so the meaning never rests on colour. |
| `FilteredNote` | The incidents the dashboard left out, by reason (not sure enough, called quiet by a verdict, already handled), each a link to the Incidents page showing exactly those. |
| `NoiseCard` | Where the alerts come from and the ones reported most often, each with its share as a bar (decoration: the figures say the same), and *Quiet this*, which gives a low priority verdict through the same path as the incident cards so the page can offer *Undo*. |

## The dashboard

The first page is built from the parts above and the charts below, in this order, and a page
that grows beside it should keep the order: what needs attention (`StatusHero`, a `HeroSurface`, with the
numbers that back it up, the `StatTile`s, inside it), what was filtered out (`FilteredNote`: how many
incidents need you and how many were left out, each reason a link to the incidents it left out, so a
headline that counts only what survives the filters keeps the rest one click away), what needs a
decision (`NeedsYouLane`, which lists the incidents the sentence counted), then
charts, then what is making the noise (`NoiseCard`), then lists. The hero is never only a color: each of its four states has its own icon,
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
touched, with the well-known ones named) and then every signal (`IncidentTimeline`). What the intrusion
detection read of the connections is `IncidentWire`: what stands out as plain notes in a tonal alert, then
an accordion with a panel each for certificates, web requests, names looked up, ssh banners and the packet
(the first panel is open, and a panel with nothing in it is not drawn), where a header the API marks
`hidden` is a chip, never a value; the page leaves the whole card out when `wire` is null. A card says
what a bot was doing in the same way: a chip for scanning or brute force and, only when they
apply, facts for its waves, ports and neighbouring addresses. The status is always an icon and a word
(`IncidentStatusChip`), and the changes are named by what they do (*Resolve*, not *Done*). The
primary action is the one to reach for next, and the page confirms a change in an `output`.
Status looks, wording and the filters' choices are in `src/incidents.ts`.

Incident Response is a page of its own right under Incidents in the menu, and answers one
question first: does any incident still wait for a response? A `HeroSurface` says so in a
sentence (urgent while any waits, calm once all are answered, idle when nothing serious went on),
with a chip for each group that has anything in it, and under it the groups in the order they matter,
each a `SectionCard` of `ResponseRow`s: severity and status chips, the title (the link to the
incident), one line (why it needs a response, or what was done about it, from `answer` in
`src/incidentResponse.ts`) and when it was last seen. Ten are listed a group, the rest behind a
button. A program that is not connected is said in an alert with a link to Integrations, since
then "no response" may only mean that nobody can tell. On a phone the page is reached through
More: `behindMore` in `src/navigation.ts` leaves the bar to the places that are used most.

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
one with three buttons that stack on a phone. A verdict the AI gave carries `AiGaveChip` (*Given by
the AI, 91% sure*, the provider and model in its tooltip) and its reason, in the panel, on the
Verdicts page and, for the incident it cleared, on its card. A signal your verdicts keep from counting is a
hollow dot and a chip in the timeline, so it reads as less in words and in shape. The list
leaves out the incidents your verdicts quiet, because nothing in them needs you, and says so with
a switch that shows how many; `quieted` is in the route's query like the other choices. The
Settings page (`VerdictsView`) is where verdicts are reviewed, changed (`VerdictDialog`) and
taken back (`ConfirmDialog`, which says how many signals are judged again).

Settings > Noise filters (`NoiseFiltersView`) keeps a draft beside what is kept, so the page never
shows a half-saved state: six cards edit it (`NoiseFloorCard`, a slider that says its number and
its word, `NoiseSourcesCard`, a select for each program with what it reported this week beside
it, `NoiseThinCard`, a select for the fewest low alerts an incident needs, `NoiseInsideCard`, a
switch, `NoiseGapCard`, two selects for how long a scan or a brute force may pause, and a link to
the verdicts) and `NoiseEffect` shows what it would
do beside what is so now, with *Save* and *Discard changes*. The question is asked a moment after
the last change (a slider being dragged is one question, and an answer to an older one is
dropped), and `role="status"` makes a screen reader say the answer. The figures are the server's
(`POST /api/noise-filters/preview`), never worked out in the browser. A signal a filter set aside
is the same hollow dot as one a verdict leaves out, with a chip that says which filter did it
(`SET_ASIDE` in `src/noiseFilters.ts`), and the incident's *Your verdict* line says how many.

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

Settings > AI (`AiSettingsView`) is two cards. The second, "What the provider sees", is an
`AiPrivacy`: three cards that are really radio buttons (Strict, Balanced, Local), each with a line
that says what is replaced and the same event as a provider would read it at that level, so the
choice needs no explaining; Local is disabled, with the reason in words, while the provider that is
asked is hosted. The first is "AI provider". At the top is an `AiProviderPicker`:
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

The incident page puts `AiReading` straight after the hero: a card that says what the AI made
of the incident as chips (the kind of thing, *n of 100 sure*, and *The AI's opinion*, so it is
never mistaken for AresGate's own confidence), a headline, the story, *What to check* and, unless
the owner has already given a verdict, the verdict it would give with its reason and one button to
give it. Under it is who read it and when, and how many signals came in since. An incident it has
not read says so and offers *Ask the AI*; while it reads, a spinner says it can take up to a
minute; when it could not be asked (AI is off, no provider, the provider failed) the reason is in
an alert with a link to Settings > AI. The page owns the asking (`askTheAi`), so pressing *Start
investigating* can follow the status change with a reading of an incident the AI hasn't read in
full. The chip in the list and in the page header is `AiChip`; looks and wording are in
`src/triage.ts`.

The AI usage page is the reference for a page of numbers. It is a place in the menu of its own
(after Interfaces, so a phone has it behind *More*), not a page of Settings: Settings > AI is where
a provider is chosen and set up, and this page is where what it took, what it cost, how much of it
is allowed and how much is used without being asked are read and set. `/settings/ai-usage` still
leads here, so a bookmark from before keeps working. The title, the range (7, 30 or 90 days) and
*Refresh* are the page header's (the range, and the toggles of the charts, are `ChoiceToggle`: one
of a row of buttons is always chosen), and the title is not repeated by a card. It leads with four
`StatTile`s (the month so far with where it is heading, the cost of the range, the tokens, the
requests) that each compare themselves with the stretch before in words. The
level card under them is the one slider in the app: five stops with the level's name and what it
reads an hour above, the words for the stop it is on below it (in a live region, so moving it is
read out), and a *Save* that is enabled only when it has moved; it is shown before AI has ever been
asked, since it can be chosen first. A plain alert then says that the costs are estimates, from
where and when the prices were read. The spending limits card is meters with the amount typed
beside them; the meter's color and its words
both say when a limit is nearly or fully used (never the color alone). The charts are the chart kit's
`BarChart`: the days as stacked bars by use with a toggle between cost, tokens and calls, and a
ranking by provider, model or use that shares the toggle. The list of every request is a plain list
of rows (not a table) that stack on a phone, and each row opens `AiCallDialog`, which shows what the
provider was sent and what it answered. The page asks again when the range changes or *Refresh* is
pressed, and keeps what it showed, with a warning, if asking again fails.

The Assistant is a place in the menu of its own, third after Incidents (so it is in a phone's bottom
bar). On a wide screen the conversations are a card beside the chat; on a phone they are behind a
*Conversations* button that opens a sheet. The chat is a `role="log"` list of `ChatMessage`s: what the
owner asked sits to the right, tinted, and an answer sits on a surface of its own with who said it,
the text (paragraphs and lists, with `[incident 3]` and `[device 12]` turned into links by `ChatText`), a *Looked at*
row of chips, a *Based on* row of chips that link, and a button for each request that made it (it
opens `AiCallDialog`). An answer that could not be made is a warning with a link to Settings > AI and
*Ask again*. The box to type in sticks to the bottom of the screen, above a phone's bottom bar
(`--v-layout-bottom`); Enter sends and Shift+Enter breaks the line. While it answers, the question
is shown at once and then the answer as it is written (`ChatWriting`): a spinner says it can take a
minute until there is something to show, the lookups it has run appear as chips, and the text grows
as the provider writes it. It is not read out word by word (`aria-live="off"`); the answer that
replaces it when it has ended is. If the connection breaks first, the page says the answer was cut
off and keeps the question in the box (`askAndFollow` in `src/api/aiChat.ts` reads the stream, and
`useAnswerProgress` in `src/chatProgress.ts` holds what has come). Wording and the starting questions are in
`src/chat.ts`.

**The assistant panel** (`AssistantHost`, `AssistantPanel`, the `assistant` store) opens from the
sparkles button in the app bar, on any page but the Assistant page itself, which is the
conversation. On a screen wide enough for both it is a drawer at the side that pushes the page
aside; below that it covers the page, and on a phone it is a sheet that rises from the bottom, as
tall as the visible screen allows (`dvh`, so it shrinks when the keyboard is up and the box to
type in stays above it) with a *Close* button, so the bar of places is never lost. It shows what
it is looking at (`pageOf` in `src/pageContext.ts`: the incident or device on screen, the search of
the logs or incidents, or only the page), hands that to every question, and starts with questions
that fit the page. It is the same conversation the Assistant page lists (*Open the Assistant page*
carries it on there, and *New conversation* begins another). What an answer suggests you do comes
as buttons (`ChatActions`): *open* a page, or change an incident's status or give it a verdict. The
assistant changes nothing itself: pressing a button makes the same audited request the incident
pages make, and a change can be taken back with *Undo* at once. On a phone, opening a page puts the
sheet away.

## Threats

The Threats pages answer "is anything really going on?" before they answer anything else, and
every look and word lives in `src/threats.ts`.

- **The page** (`ThreatsView`) opens on the first lane with something in it and keeps the lane in
  the route's query (`lane`), as the Incidents list does, so a link opens on it (the range, 24 hours
  or 7 days, is not kept). At the top the
  funnel (`ThreatFunnel`) goes from what programs reported to the lanes, one bar for each step
  with its number and what was taken out on the way. The bars are drawn to the number of digits,
  not to scale, because seventy thousand and four on one linear bar leaves the four invisible; the
  numbers say the same, so the bars are decoration. Then a switch of the three lanes with their
  counts, a sentence for what the lane on screen means, and its incidents as ordinary
  `IncidentCard`s, so a card can be judged where it is. The background lane lists *kinds*
  (`FamilyCard`) rather than incidents, because hundreds of them say the same thing.
- **A lane is never just a color.** `LaneChip` is an icon and a word (*Threat*, *Suspect*,
  *Background*), `CallChip` says what the AI or you called an incident and how sure, and
  `StageTrail` draws how far an attack got (*Looking around*, *Trying to get in*, *Sign it worked*)
  as a row of steps with the ones it reached filled, and says it in words for a screen reader.
- **A kind** (`KindsView`, `FamilyView`) has its own list, with a search and the lane and who
  judged it as filters in the query, and its own page. `FamilyJudgement` is the one place that says
  what is thought of the kind (the AI's call and why, whether it is yours) and has the three
  things you can do: *Always background*, *Never set aside* (the one you gave is disabled, and
  *Take my word back* appears) and *Ask the AI*. Why they are where they are is a list in
  `FamilyView`, one fact a line, from the server so it cannot disagree with it.
- **An incident** says where it stands (`IncidentWhere`: its lane, why, how far it got, and its
  kind with a link) and, when an alert repeated or two programs reported it, what the programs saw
  (`IncidentInsights`: who reported how much and what each added, the ATT&CK techniques, machines,
  applications and what was named, as bars against the commonest) and what kept happening
  (`IncidentOccurrences`), as one line with a count, the programs that reported the same alert, and
  what each of them said of it (`EvidenceDetails`, opened and closed per line).
- **Settings > Threat detection** (`ThreatSettingsView`) is a draft beside what is kept, the way
  the noise filters are: `ThreatLevelCard` (a slider that says its number and what it means),
  `ThreatAiCard`, `ThreatNetworkCard` (what is open to the internet, the ports and a note) and
  `ThreatEffect`, which shows what saving would do to the lanes (`POST /api/threat-settings/preview`,
  never worked out in the browser). Ports are read as they are typed, and a word that is not a port
  is named under the field, not guessed at.
- **On a phone** Threats is in the bottom bar between the dashboard and Incidents, and Logs is in
  the sheet behind More. Nothing scrolls sideways.

## Review

The Review page (`ReviewView`) is where the owner agrees or disagrees with what the AI decided,
and `Settings > Review` (`ReviewSettingsView`) is how much of it waits.

- **The page** has a record of how often the owner has agreed (`standingLine`, a bar, and a button
  to Settings once the server says the AI has earned trust, `standing.trusted`), three lists
  (*Waiting*, *Decided for you*, *Answered*, each with its count) and a card for each decision
  (`ReviewCard`). A card is accented by the kind of call (red for an alarm, amber for a probe,
  green for harmless), says what the decision does in a line from the server, and has
  `ReviewAnswer`: **Agree**, **Disagree**, **Add a reason** (up to 300 characters) and, for a kind
  that was set aside, a box that keeps it so. An answered card shows what was said and **Take it
  back**. **Agree with all shown** (waiting list, after asking) agrees with what the page lists,
  at most a hundred.
- **After an answer** the card leaves its list and the page asks for the lists and counts again,
  keeping as many as were shown. The lists refresh every minute.
- **The menu** shows a number for what waits (`NavIcon`, in the side menu and the bottom bar,
  spoken as well), asked for every minute by `App.vue` while signed in (`useReviewStore`).
  On a phone Review is in the bar and the Assistant is behind **More** to make room. The
  dashboard has `ReviewNudge`.
- **Elsewhere** `ReviewStrip` (on an incident's AI card and on a kind's judgement) says where the
  review stands and has the same two buttons, so an answer can be given where the call is read.

## Assets

The Assets page lists every device the connected programs can see (`GET /api/assets`), built from
the parts above: a `PageHeader`, the search (`AssetSearch`), the choices, a list of `AssetCard`s,
and at the end `AssetSuppliers`, which says where the assets come from and why a device may be
missing. What the list is narrowed to lives in the route's query (`status`, `q`, repeated `source`,
`interface`, `new`, `unidentified`, `kind`, `sort`), never in component state, so a link or the back
button reproduces it; the words, modes and defaults are in `src/inventory.ts`.

- **A card** says who it is (the name, then the maker and hardware address, or for a machine with
  none the program and how it is doing), whether it is there, its addresses, the programs that
  list it (`AssetSources`: "OPNsense · ARP table, DHCP leases · 2 minutes ago", and for a
  machine merged by guess, "matched by address") and the interfaces it is on. Flags say only what
  is worth noticing: new this week, a private hardware address, nothing says what it is. The
  state is always an icon and its words (`AssetStatusChip`: online, seen recently, not seen for
  a while), and the bar on the card's side repeats it in color. A card lays itself out by its own
  width (a container query): in columns on a computer, one thing under another on a phone.
- **What Fingerbank says it is.** Once Fingerbank has been asked about a device (see
  [Fingerbank](integrations.md#fingerbank)) the asset's `identity` says what it found, and the
  card shows it as a flag with the model's name. The asset's page has a *What it is* section
  (`AssetIdentity`): the model's name, the steps from the widest kind to it as chips, the maker, the
  operating system and how sure Fingerbank is as a bar with its words and number (`identityConfidence`
  in `src/inventory.ts`, in the bands Fingerbank gives), and when and why it was asked. A device it
  had no match for says so and that it is asked again after a week, rather than showing nothing.
- **The choices.** The states are a row of toggle buttons with how many each holds (counts
  respect the other choices) that scrolls sideways on a phone instead of wrapping. The programs,
  *New this week* and *Not identified* are buttons with `aria-pressed` and their counts over the
  whole inventory, so each says what it would find; *Interface* is a select that appears only
  when an interface has networks to tell which assets are on it. *Clear filters* leaves the state
  and the order alone. Slash goes to the search from anywhere but a field.
- **What it is.** The owner says what each device is and what it is for (`AssetClassify`, a card
  on the asset's page: a kind from `GET /api/assets/kinds`, grouped, and a purpose of up to 200
  characters; saved with `PUT /api/assets/{key}/profile`, taken back with `DELETE`). The kind shows as
  an `AssetKindChip` (a picture and its words) and the purpose under the name on the card; a *What it
  is* select filters the list (`kind`, or `unclassified`) once anything is said. Where the name or the
  maker suggests a kind it is offered with *Use that*, never applied. What is said goes to the
  analyst: see [Assets](operations.md#assets). Under the kind, *How much does it matter?* (normal,
  important or critical, `ChoiceToggle`) offers the level a kind usually has when it is first picked
  and says so; a guest's device or a smart home device says that a threat that touched only it takes
  more proof. See [Which devices matter](threats.md#which-devices-matter).
- **Nothing to show** says why and what to do: nothing narrowed matches (*Clear filters*); no
  asset is in that state; no program that lists devices is connected (leads to Integrations); one
  is connected but has listed nothing yet (leads to Status). More assets than a page are asked for
  with *Show more*, and the page asks again every 30 seconds for as many as are shown.
- **The Internet side is left out.** A device on the provider's side of the firewall (its addresses
  are public, and it is not one of the firewall's own, which the ARP table marks as permanent) is
  not an asset: the page says how many were left out (`outside` in `GET /api/assets`). A network of
  the owner's on the Internet interface leaves out what is on it, and one on a home interface keeps
  what is on it. The Internet is not offered as an *Interface* choice.

## Devices

The Devices page lists every address that took part in a connection the connected programs
reported over the last week (`GET /api/devices`), and a page for each (`GET /api/devices/{address}`).
The Assets page is the owner's inventory, what the network says is on it; this is what it did, so a
server on the Internet that a camera called, or a scanner that knocked on the firewall, is here and
is not an asset. It is read from the events the integrations stored (`app/devices/seen.py`), so a
connection is an event such as a firewall block or an alert, not every packet, and the page says so.
The route's query keeps what the list is narrowed to (`q`, `scope`, `direction`, `flagged`, `sort`;
the words and defaults are in `src/devices.ts`), as on the Assets page.

- **A card** (`DeviceCard`) names the address, links to its page, and says whose it is: *Your
  devices* (an address of an asset), *Other local* (a private address no asset holds) or *On the
  Internet*, each with its own icon. A bar splits its connections into those made *to* it (in) and
  those it made (out), with both counts, and chips list the ports they used. Flags appear only when
  there is something to say: the incidents it is in, what threat intelligence kept of it (the same
  judgement as on the asset page, never asked for to show it) and what Fingerbank says it is, for an
  address that is an asset. Its asset's name links to the asset's page.
- **The choices.** The scopes are a row of toggle buttons with how many each holds among the devices
  the search finds; *Connections* narrows to those connected to or those that connected out; *In an
  incident* is a button; *Order* is the most recently seen, the busiest or by address. Slash goes to
  the search, which finds an address, a name from a reverse lookup that is already kept, or the name,
  maker or hardware address of its asset.
- **A device's page** has four tiles (connections to it, connections from it, when it was last seen,
  events in the last day), then *Connections*: a row for each peer and port with the direction in
  words and an arrow, the source and destination (the other end links to its own page), the port with
  the service it stands for, and how often and when. Below are *Your device* for an asset (its name,
  maker, hardware address, what the owner said it is, and what Fingerbank says it is), *What threat
  intelligence says* for an address on the Internet (what is kept, the owner's ruling over it), the
  incidents it is in, each with links to its kind of threat and its attack chain, and the latest
  events. On a phone the connections stack and on a computer they are a table, by the card's own
  width.
- **Nothing to show** says why: nothing has been reported in the last 7 days (leads to Integrations)
  or nothing matches the choices (*Clear filters*, which leaves the scope and the order alone). More
  devices than a page are asked for with *Show more*. If more addresses were seen than are read (5,000
  for each side of a connection), the page says the list is the ones seen most recently.
- An address nothing is known of (in no event of the week, no incident, and not an asset) has no
  page: the API answers 404 and the page says so.

## Integrations

The Integrations page (`IntegrationsView`) has one `IntegrationCard` for each integration, with a
search above them and a row of toggle buttons for each kind of integration (Network monitoring,
Threat intelligence, Device intelligence) with how many each holds. The search needs every word to
be in an integration's name, what it provides or its kind, in any order; the kind and the search
narrow the list together, and *No integration matches* offers to clear them. The set-up count
("2 of 7 set up") is always of every integration. Both live in the page, since there are few
enough integrations that they filter at once (`narrowIntegrations` in `src/integrations.ts`).

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
there only for something that is not a page. A place in the menu can carry `keywords`, words that
find it though they are not shown (AI usage: *spending*, *tokens*, *budget*).

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
- **Addresses.** The built files are in `/static` (Vite's `assetsDir`), not `/assets`, which is the
  Assets page: nginx answers a folder that is named like a page with files only, and the page
  would be a 404 in the container (the host test run, which falls back to the index for any
  address, does not show it). Before giving a page an address, check there is no folder of that
  name in the built app; `smoke-test.sh` checks the address of the Assets page.
- **Test ids.** `data-test="…"` on what tests look for. The shared parts have fixed ones
  (`page-heading`, `page-description`, `section-title`, `load-error-message`, `confirm-accept`,
  `confirm-cancel`) so the same page object code works for every page.

## Checking a new page

Add its page object to `frontend/e2e/support/pages`, a spec to `e2e/specs`, an axe check in
`accessibility.spec.ts` (it runs in both themes) and a fit check in `layout.mobile.spec.ts`.
