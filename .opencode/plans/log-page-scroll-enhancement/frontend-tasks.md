# Frontend Implementation Tasks — Log Page Scroll Enhancement

**Feature:** `log-page-scroll-enhancement`  
**Assignee:** @fe-dev  
**References:**
- Requirements: `.opencode/plans/log-page-scroll-enhancement/requirements.md`
- Technical Spec: `.opencode/plans/log-page-scroll-enhancement/technical.md`

---

## Rules Reminder

- All components MUST be Angular 20 **Standalone Components** — no `NgModule`.
- State management MUST use **Angular Signals** (`signal()`, `computed()`, `effect()`, `input()`, `viewChild()`).
- Styling MUST use **Tailwind CSS utility classes** — no custom CSS unless absolutely necessary.
- If a `.css` file is needed, scope with `:host` and use `ng-deep` sparingly.
- Smart components handle state/API calls. Presentation (`input()` / `output()` only) components do not inject services.
- **No Angular CLI scaffold needed** — this feature modifies existing files only.
- **No backend or API changes** — this is a pure frontend CSS/layout fix.

---

## Phase 1 — Fix the Table Host Element (Critical Path)

This is the root-cause fix. Without it, no overflow scrolling will work.

- [x] **FE-1.1** Open `web/src/app/features/logs/components/logs-table.component.ts`

- [x] **FE-1.2** Add a `host` metadata object to the `@Component` decorator of `LogsTableComponent`:
  ```typescript
  @Component({
    selector: 'app-logs-table',
    standalone: true,
    host: {
      class: 'flex flex-col flex-1 min-h-0 overflow-hidden'
    },
    imports: [SynergyComponentsModule],
    template: `...`,
  })
  ```
  - `flex flex-col`: The host element becomes a flex column child, participating in the parent flex height chain.
  - `flex-1`: Takes all remaining vertical space allocated by the parent `.flex-1.min-h-0...flex-col` wrapper in `logs.component.html`.
  - `min-h-0`: **Critical.** Overrides the browser default `min-height: auto` on flex children, which otherwise prevents the element from shrinking below its content height. Without this, the scroll container never gets a bounded height.
  - `overflow-hidden`: Clips any content that visually overflows the host boundary, deferring scroll to the inner container.

---

## Phase 2 — Fix the Inner Scroll Container

- [x] **FE-2.1** In the `LogsTableComponent` template, locate the outermost `<div>`:

- [x] **FE-2.2** Replace it with the corrected scroll container:

- [x] **FE-2.3** Verify the closing `</div>` tag still correctly wraps the entire table and "Load More" section. The closing tag at the end of the `@else` block remains unchanged.

---

## Phase 3 — Wire Auto-Scroll Inputs

- [x] **FE-3.1** Add two new Signal inputs to `LogsTableComponent` class:

- [x] **FE-3.2** Add the `viewChild` Signal reference for the scroll container. Add this to the class body:

- [x] **FE-3.3** Add the auto-scroll `effect()` inside the class **constructor** (not `ngOnInit`):

- [x] **FE-3.4** Update the `imports` in `@Component` to ensure `ElementRef`, `viewChild`, `effect` are imported from `'@angular/core'`. The full import line should read:
  ```typescript
  import { Component, ElementRef, effect, input, output, viewChild } from '@angular/core';
  ```

---

## Phase 4 — Thread New Inputs from Parent LogsComponent

- [x] **FE-4.1** Open `web/src/app/features/logs/logs.component.html`

- [x] **FE-4.2** Locate the `<app-logs-table>` binding block (currently lines 56–62) and add the two new input bindings:
  ```html
  <app-logs-table
    (entrySelected)="onSelectEntry($event)"
    (loadMoreClicked)="loadMoreLogs()"
    [autoScroll]="autoScroll()"
    [isStreaming]="isStreaming()"
    [entries]="displayEntries()"
    [isLoadingMore]="isLoadingMore()"
    [isLoading]="isLoading()"
    [selectedEntry]="selectedEntry()"
  />
  ```
  - `autoScroll()` and `isStreaming()` are already exposed from `LogsStoreService` via `logs.component.ts` (lines 37 and 34 respectively). **No changes to `logs.component.ts` are needed.**

---

## Phase 5 — Verify Sticky Header Behaviour

No code changes are required for sticky headers — the existing `sticky top-0 z-20` on each `<th>` is architecturally correct once Phase 1 fixes the scroll container. This phase is a **verification checklist**.

- [ ] **FE-5.1** Open the app in a browser and navigate to `/logs`
- [ ] **FE-5.2** Load 100+ log entries (use "Refresh" or live streaming)
- [ ] **FE-5.3** Scroll down in the table — confirm the `Timestamp`, `Level`, `Module`, `Message` column headers remain **fixed** at the top of the scroll container as content scrolls beneath them
- [ ] **FE-5.4** Open browser DevTools → Elements panel; confirm the `<th>` elements have `position: sticky` and `top: 0` in computed styles
- [ ] **FE-5.5** Verify there is **no** `border-collapse: collapse` style applied to `<table>`. (Sticky headers are broken by `border-collapse: collapse` in all browsers. The existing per-`<td>` `border-b` approach is correct and must be preserved.)

---

## Phase 6 — Verify Detail Panel Interaction

- [ ] **FE-6.1** With 100+ entries loaded, scroll down approximately halfway in the table
- [ ] **FE-6.2** Click a log entry row — the detail panel (`app-logs-detail`, `h-75` height) slides in from the bottom
- [ ] **FE-6.3** Confirm the **table scroll position is preserved** — it must NOT jump to top when the detail panel opens
- [ ] **FE-6.4** Close the detail panel — confirm scroll position is again preserved
- [ ] **FE-6.5** Confirm the scrollbar remains functional in both the collapsed (full-height) and expanded (with detail panel) states

---

## Phase 7 — Verify Cross-Browser Scrollbar Rendering

- [ ] **FE-7.1** Test in **Chrome** — verify styled thin scrollbar appears on the right of the table when entries overflow
- [ ] **FE-7.2** Test in **Firefox** — verify `scrollbar-width: thin` takes effect (Firefox does not support WebKit pseudoelements but the `scrollbar-width` property applies)
- [ ] **FE-7.3** Test in **Safari** — verify WebKit scrollbar pseudoelement styles from `.syn-scrollbar::-webkit-scrollbar` apply
- [ ] **FE-7.4** Test in **Edge** — verify Chrome-equivalent rendering (Chromium-based)

---

## Phase 8 — Build & Lint Verification

- [ ] **FE-8.1** Run the Angular production build — must have zero compilation errors:
  ```bash
  cd web && ng build --configuration production
  ```
- [ ] **FE-8.2** Run the Angular linter — must have zero new errors:
  ```bash
  cd web && ng lint
  ```
- [ ] **FE-8.3** Confirm no new TypeScript errors in `logs-table.component.ts` related to:
  - `viewChild` return type (`Signal<ElementRef<HTMLDivElement> | undefined>`)
  - `effect()` constructor injection context (must be in constructor, not `ngOnInit`)
  - `input()` signal types for `autoScroll` and `isStreaming`

---

## Dependencies & Order of Operations

| Task | Depends On | Note |
|---|---|---|
| FE-1.x (Host fix) | None | Must be done first — everything else depends on correct flex height |
| FE-2.x (Scroll container) | FE-1.x | Requires host to be correctly sized |
| FE-3.x (Auto-scroll effect) | FE-2.x (needs `#scrollContainer`), FE-3.1 inputs | Can be done alongside FE-2 |
| FE-4.x (Parent bindings) | FE-3.1 (new inputs defined) | Must add inputs before binding them |
| FE-5.x (Sticky header verify) | FE-1.x + FE-2.x complete | Verification only |
| FE-6.x (Detail panel verify) | FE-1.x + FE-2.x complete | Verification only |
| FE-7.x (Cross-browser) | FE-2.x complete | Manual browser testing |
| FE-8.x (Build/lint) | All code changes complete | Final gate before PR |

---

## Definition of Done

All tasks are checked off AND:

- [ ] The logs table shows a vertical scrollbar when entries exceed the visible viewport height
- [ ] The scrollbar uses the `syn-scrollbar` style (thin, neutral colour, matching Synergy theme)
- [ ] Table column headers remain sticky at the top of the scroll container while scrolling
- [ ] Scroll position is preserved when the log detail panel opens or closes
- [ ] During live streaming with `autoScroll=true`, the table scrolls to the top (newest entry) as new entries arrive
- [ ] Keyboard scrolling works (Tab to focus scroll container, then arrow keys / Page Up / Page Down)
- [ ] A visible focus ring appears when the scroll container is keyboard-focused
- [ ] No horizontal scrollbar appears
- [ ] `ng build --configuration production` exits with zero errors
- [ ] `ng lint` exits with zero new errors
- [ ] No new JavaScript console errors on the `/logs` route
