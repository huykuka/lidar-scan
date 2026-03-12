# QA Tasks — Log Page Scroll Enhancement

**Feature:** `log-page-scroll-enhancement`  
**Assignee:** @qa  
**References:**
- Requirements: `.opencode/plans/log-page-scroll-enhancement/requirements.md`
- Technical Spec: `.opencode/plans/log-page-scroll-enhancement/technical.md`
- Frontend Tasks: `.opencode/plans/log-page-scroll-enhancement/frontend-tasks.md`

> **Scope note**: This is a **frontend-only** feature. There are no backend changes, no API changes, and no WebSocket protocol changes. All testing targets the Angular component layer and browser rendering behaviour.

---

## TDD Preparation (Write Failing Tests First)

These tests must be written and committed as **failing** before development begins.

- [ ] **QA-TDD-1** Write a failing Angular unit test for `LogsTableComponent`:
  - Assert the component host element has `class` attribute containing `flex`, `flex-col`, `flex-1`, and `min-h-0`
  - File: `web/src/app/features/logs/components/logs-table.component.spec.ts`

- [ ] **QA-TDD-2** Write a failing Angular unit test for `LogsTableComponent`:
  - Assert that the scroll container `<div>` exists with attribute `role="region"` and `aria-label="Log entries"`

- [ ] **QA-TDD-3** Write a failing Angular unit test for `LogsTableComponent`:
  - Assert the scroll container `<div>` has `tabindex="0"` for keyboard accessibility

- [ ] **QA-TDD-4** Write a failing Angular unit test for `LogsTableComponent`:
  - Assert `autoScroll` input defaults to `true`
  - Assert `isStreaming` input defaults to `false`

- [ ] **QA-TDD-5** Write a failing Angular unit test for `LogsTableComponent`:
  - Mock `scrollContainer` nativeElement and assert `scrollTop` is set to `0` when `autoScroll=true`, `isStreaming=true`, and a new entry is added to `entries`

- [ ] **QA-TDD-6** Write a failing Angular unit test for `LogsTableComponent`:
  - Assert `scrollTop` is NOT modified when `autoScroll=false` even if new entries arrive during streaming

---

## Frontend Unit Tests

*Coordinate with @fe-dev. Check off after tests pass.*

### Component Structure Tests

- [ ] **QA-FE-1** `LogsTableComponent` host element has Tailwind classes: `flex`, `flex-col`, `flex-1`, `min-h-0`, `overflow-hidden`
- [ ] **QA-FE-2** Scroll container `<div>` has class `overflow-y-auto` (NOT `overflow-auto`)
- [ ] **QA-FE-3** Scroll container `<div>` does NOT have class `overflow-x-auto` or `overflow-x-scroll`
- [ ] **QA-FE-4** Scroll container `<div>` has class `syn-scrollbar`
- [ ] **QA-FE-5** Scroll container `<div>` has `tabindex="0"`
- [ ] **QA-FE-6** Scroll container `<div>` has `role="region"`
- [ ] **QA-FE-7** Scroll container `<div>` has `aria-label="Log entries"`
- [ ] **QA-FE-8** `<app-logs-table>` template reference variable `#scrollContainer` resolves to the correct `<div>` element

### Input Signal Tests

- [ ] **QA-FE-9** `autoScroll` Signal input defaults to `true` when not provided
- [ ] **QA-FE-10** `isStreaming` Signal input defaults to `false` when not provided
- [ ] **QA-FE-11** `entries`, `selectedEntry`, `isLoading`, `isLoadingMore` existing inputs still work correctly after changes

### Auto-Scroll Effect Tests

- [ ] **QA-FE-12** When `autoScroll=true` AND `isStreaming=true` AND a new entry is prepended: `scrollContainer.nativeElement.scrollTop` is set to `0`
- [ ] **QA-FE-13** When `autoScroll=false` AND `isStreaming=true`: `scrollTop` is NOT modified on new entry
- [ ] **QA-FE-14** When `autoScroll=true` AND `isStreaming=false` (normal load): `scrollTop` is NOT modified
- [ ] **QA-FE-15** When `entries` is empty: effect does NOT attempt to set `scrollTop` (no null-reference error)
- [ ] **QA-FE-16** Effect is only registered in the component constructor (not `ngOnInit`) — verify there are no `NG0203` injection context errors in the console

### Parent Template Binding Tests

- [ ] **QA-FE-17** `logs.component.html`: `<app-logs-table>` binds `[autoScroll]="autoScroll()"` correctly
- [ ] **QA-FE-18** `logs.component.html`: `<app-logs-table>` binds `[isStreaming]="isStreaming()"` correctly
- [ ] **QA-FE-19** `LogsComponent` still reads `autoScroll` from `LogsStoreService` (no new state added to `logs.component.ts`)
- [ ] **QA-FE-20** `LogsComponent` still reads `isStreaming` from `LogsStoreService` (no new state added to `logs.component.ts`)

### Sticky Header Tests

- [ ] **QA-FE-21** Each `<th>` element retains Tailwind class `sticky` and `top-0`
- [ ] **QA-FE-22** Each `<th>` element retains `z-20` to layer above table body rows
- [ ] **QA-FE-23** The `<table>` element does NOT have `border-collapse: collapse` in its computed style

---

## Frontend E2E / Manual Browser Tests

Navigate to `/logs` in the running application for each test.

### Core Scrolling

- [ ] **QA-E2E-1** With 50+ log entries, a vertical scrollbar is visible on the right side of the table container
- [ ] **QA-E2E-2** Mouse wheel scrolling moves the table content up and down smoothly
- [ ] **QA-E2E-3** Click-and-drag the scrollbar thumb scrolls the table content
- [ ] **QA-E2E-4** The main page itself does NOT scroll when using the mouse wheel over the table (scroll is contained within the table container)
- [ ] **QA-E2E-5** No horizontal scrollbar appears under any condition with the standard viewport width (≥1280px)
- [ ] **QA-E2E-6** With 0 log entries (empty state), no scrollbar appears and the empty state illustration centres correctly in the available space

### Sticky Header Verification

- [ ] **QA-E2E-7** When scrolled 50% down in a large dataset, the `Timestamp / Level / Module / Message` header row is visible and fixed at the top of the table container
- [ ] **QA-E2E-8** The header background (`bg-syn-color-neutral-100`) completely covers the content rows scrolling beneath it (no bleed-through)
- [ ] **QA-E2E-9** The header bottom border (`border-b border-syn-color-neutral-200`) remains visible and aligned at all scroll positions

### Detail Panel Interaction

- [ ] **QA-E2E-10** Scroll to the 30th row and click it — the detail panel opens. The table scroll position remains at the 30th row (not reset to top or bottom)
- [ ] **QA-E2E-11** With the detail panel open, scrolling in the table works and does not scroll the detail panel
- [ ] **QA-E2E-12** Close the detail panel by clicking X — the table scroll position is preserved
- [ ] **QA-E2E-13** The table scrollbar is visible and functional both with and without the detail panel open

### Keyboard Navigation

- [ ] **QA-E2E-14** Press `Tab` to focus the scroll container — a focus ring appears around it
- [ ] **QA-E2E-15** With scroll container focused, press `↓` (Down Arrow) — content scrolls down
- [ ] **QA-E2E-16** With scroll container focused, press `↑` (Up Arrow) — content scrolls up
- [ ] **QA-E2E-17** With scroll container focused, press `Page Down` — content scrolls by approximately one viewport height
- [ ] **QA-E2E-18** With scroll container focused, press `Page Up` — content scrolls up by approximately one viewport height
- [ ] **QA-E2E-19** With scroll container focused, press `Home` — scrolls to the top
- [ ] **QA-E2E-20** With scroll container focused, press `End` — scrolls to the bottom
- [ ] **QA-E2E-21** The focus ring does NOT appear when the scroll container is clicked with a mouse (`:focus-visible` only)

### Live Streaming Auto-Scroll

- [ ] **QA-E2E-22** Click "Go Live" to start streaming. As new log entries arrive, the table automatically scrolls to the top (newest entries are prepended)
- [ ] **QA-E2E-23** Manually scroll down 50+ rows while streaming is active. The auto-scroll continues to trigger, bringing view back to top on each new entry — this is **expected behaviour** with `autoScroll=true`
- [ ] **QA-E2E-24** Click "Stop Live" to stop streaming — auto-scroll stops, scroll position is no longer automatically moved
- [ ] **QA-E2E-25** After stopping streaming, manually scroll the table and load more entries — scroll position does NOT jump

### Load More Interaction

- [ ] **QA-E2E-26** Scroll to the bottom of the table and click "Load More" — new entries append at the bottom, scroll position stays at the bottom (does NOT jump to top)
- [ ] **QA-E2E-27** While "Load More" is loading (`isLoadingMore=true`), the table remains scrollable and the scrollbar is functional

### Search and Filter

- [ ] **QA-E2E-28** Enter a search term in the toolbar — filtered results render correctly and the scroll container resets to the top (natural scroll-to-top on dataset replace)
- [ ] **QA-E2E-29** Change the level filter — filtered results render correctly and scroll container is functional
- [ ] **QA-E2E-30** Clear the filter — full dataset restores, scroll container functional

### Loading States

- [ ] **QA-E2E-31** While initial load is in progress (`isLoading=true`, no entries), the spinner centres correctly within the scroll container
- [ ] **QA-E2E-32** During a filter refresh (loading overlay), the semi-transparent overlay covers the table content but the scrollbar is still visible

---

## Responsive & Layout Tests

- [ ] **QA-RESP-1** At viewport width 1280px: table scrolls correctly and sticky headers work
- [ ] **QA-RESP-2** At viewport width 1440px: table scrolls correctly and sticky headers work
- [ ] **QA-RESP-3** At viewport width 1920px: table scrolls correctly and sticky headers work
- [ ] **QA-RESP-4** With the side nav open and closed: table adapts to width change and scroll remains functional
- [ ] **QA-RESP-5** With the detail panel open at `h-75` (300px): the table section above is scrollable and the remaining height is sufficient to show at least 3 rows

---

## Cross-Browser Tests

- [ ] **QA-BROWSER-1** **Chrome** (latest): scrollbar visible, styled, functional
- [ ] **QA-BROWSER-2** **Firefox** (latest): `scrollbar-width: thin` applied; functional vertical scrolling
- [ ] **QA-BROWSER-3** **Safari** (latest): WebKit scrollbar pseudoelement styles applied; functional
- [ ] **QA-BROWSER-4** **Edge** (latest): Chromium-equivalent rendering and behaviour

---

## Performance Tests

- [ ] **QA-PERF-1** Render 200 log entries and verify scrolling maintains 60fps (Chrome DevTools Performance tab — no dropped frames during scroll gesture)
- [ ] **QA-PERF-2** Render 500 log entries (via "Load More" x5) — verify no layout thrashing on scroll (no `ResizeObserver` loop errors in console)
- [ ] **QA-PERF-3** During live streaming at high frequency (>10 entries/second), the `effect()` auto-scroll does not cause visible jank — confirm by observing the FPS counter in Chrome DevTools

---

## Accessibility Audit

- [ ] **QA-A11Y-1** Run a Lighthouse accessibility audit on `/logs` — score must not regress from the pre-feature baseline
- [ ] **QA-A11Y-2** Screen reader (NVDA/JAWS/VoiceOver) announces "Log entries" when the scroll container receives focus
- [ ] **QA-A11Y-3** Each table column header is announced correctly by screen readers when navigating table cells
- [ ] **QA-A11Y-4** The `syn-badge` level indicators (DEBUG / INFO / WARNING / ERROR / CRITICAL) have sufficient colour contrast (already provided by Synergy UI — verify no regression)

---

## Linter & Type-Check Verification

- [ ] **QA-LINT-1** Frontend TypeScript compilation — zero errors:
  ```bash
  cd web && ng build --configuration production
  ```
- [ ] **QA-LINT-2** Frontend linter — zero new errors:
  ```bash
  cd web && ng lint
  ```
- [ ] **QA-LINT-3** Confirm no `NG0203: effect() can only be called within an injection context` error in the browser console (effect must be in constructor)
- [ ] **QA-LINT-4** Confirm no `ExpressionChangedAfterItHasBeenCheckedError` in the browser console (the `effect()` scroll pattern does not mutate component state)

---

## Developer Coordination

- [ ] **QA-COORD-1** Confirm with @fe-dev that all frontend tasks (FE-1.x through FE-8.x) are checked off in `frontend-tasks.md`
- [ ] **QA-COORD-2** Verify that **no backend files were modified** during this feature — `git diff --name-only` must show only files within `web/src/app/features/logs/`
- [ ] **QA-COORD-3** Confirm `styles.css` was NOT modified (`.syn-scrollbar` was pre-existing and only referenced, not changed)
- [ ] **QA-COORD-4** Confirm `app.css` was NOT modified

---

## Pre-PR Verification Checklist

Before raising a Pull Request, confirm all of the following:

- [ ] All TDD tests written and now **passing**
- [ ] All unit tests passing: `cd web && ng test`
- [ ] All E2E/manual browser tests verified
- [ ] Lighthouse accessibility score not regressed
- [ ] Build clean: `ng build --configuration production` — zero errors
- [ ] Lint clean: `ng lint` — zero new errors
- [ ] Zero new JavaScript console errors on the `/logs` route
- [ ] Sticky headers confirmed functional in Chrome, Firefox, Safari, and Edge
- [ ] Vertical scrollbar functional with 50, 200, and 500 log entries
- [ ] Auto-scroll confirmed working during live streaming
- [ ] Keyboard navigation (Tab, arrows, Page Up/Down) confirmed working
- [ ] All acceptance criteria in `requirements.md` checked off
- [ ] `qa-report.md` written with test coverage summary and any outstanding risks
