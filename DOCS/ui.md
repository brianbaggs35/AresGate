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
| `StatTile` | One number that matters with its name and a line of context. It leads to where the number comes from when given `to`. |
| `FactList` | Facts as labelled values (the versions on the Status page): the label beside its value where there is room, and above it on a phone. |
| `UsageMeter` | How much of something is used: a bar that turns amber from 75% and red from 90%, with the figures in words so the meaning never rests on colour. |

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
