# Technical Specification — Log Page Scroll Enhancement

**Feature:** `log-page-scroll-enhancement`  
**Author:** @architecture  
**Date:** 2026-03-12  
**Status:** Approved for Implementation  
**Scope:** Frontend only — no backend or API changes.

---

## 1. Problem Statement

The `app-logs-table` component (`logs-table.component.ts`) renders an HTML `<table>` inside a `<div class="flex-1 overflow-auto relative">` wrapper. Although `overflow-auto` is applied to this inner div, the component is projected into a parent container (`logs.component.html`) whose flex height chain is broken — the table wrapper never receives a constrained height and therefore never produces a scrollable overflow. The visible result: with 100+ log entries, rows spill past the viewport and cannot be scrolled to.

Additionally, the sticky `<thead>` cells rely on `position: sticky` combined with `top: 0`, which only works correctly when the scroll container is the direct parent of the `<table>`. If the scroll container is a grandparent or an ancestral flex child without `min-height: 0`, sticky headers detach from the scroll container and either re-scroll with content or disappear behind fixed UI chrome.

---

## 2. Root Cause Analysis

### 2.1 Flex Height Chain

The full ancestor chain from `html` to the table wrapper is:

```
html, body           → height: 100%;  overflow: hidden   (app.css)
app-root             → display: block; height: 100%      (app.css)
app-main-layout      → height: 100vh                     (main-layout.component.css :host)
  └── .flex.flex-col.h-screen.overflow-hidden            (main-layout.component.html line 1)
      └── .flex.flex-1.overflow-hidden                   (line 5)
          └── .flex-1.flex.flex-col.overflow-hidden      (content area, line 15)
              └── <main .flex-1.flex.flex-col.overflow-hidden.px-4.py-3>  (line 16)
                  └── <div [@routeAnimations] .flex-1.flex.flex-col.min-h-0>  (line 41-43)
                      └── <router-outlet>  (line 44)
                          └── app-logs
                              └── <div .h-full.flex.flex-col.gap-3.p-2>     (logs.component.html line 1)
                                  └── [toolbar card]                         (line 3–49, shrink-0 via shadow/border)
                                  └── <div .flex-1.min-h-0...overflow-hidden.flex.flex-col>  (line 52–54)
                                      └── app-logs-table
                                          └── <div .flex-1.overflow-auto.relative>   ← THE SCROLL CONTAINER
                                              └── <table>
```

**The issue**: `app-logs-table` is a standalone component but its `:host` element has no `display: block` or height constraint. Angular renders the component's host element as an inline element by default, which does not participate correctly in the flex height chain. The `<div class="flex-1 overflow-auto relative">` inside the template therefore never gets a bounded height and `overflow-auto` produces no scrollbar.

### 2.2 Sticky Header Broken Context

`sticky top-0` on `<thead> <th>` cells requires that the nearest scrollable ancestor is **also the nearest positioned ancestor** of the sticky element. When the scroll container is not the direct parent of `<table>`, browser sticky positioning can fail in Chrome/Safari/Firefox. The fix must guarantee the `overflow-auto` div is the direct, bounded scroll container.

### 2.3 Detail Panel Height Competition

`app-logs-detail` renders as a sibling to `app-logs-table` inside the `.flex-1.min-h-0...flex.flex-col` wrapper. When the detail panel is open (`h-75` ≈ 18.75rem), it takes a fixed height from the flex column, reducing the remaining height for the table. The `app-logs-table` must shrink gracefully without losing its scroll capability.

---

## 3. Architectural Solution

### 3.1 Fix the Host Display Binding

**This is the primary fix.** `LogsTableComponent` must declare its host element as a flex column that fills the available space. The Angular best practice for this (per `frontend.md`) is to add a `host` metadata binding — no separate `.css` file needed.

```typescript
@Component({
  selector: 'app-logs-table',
  host: {
    class: 'flex flex-col flex-1 min-h-0 overflow-hidden'
  },
  ...
})
```

This makes the `<app-logs-table>` host element itself a flex child participant, matching how the parent `<div class="flex-1 min-h-0 ... flex flex-col">` allocates space. The `min-h-0` is critical: in CSS Flexbox, a flex child's minimum height defaults to `auto` (the content's natural size), which prevents shrinking below content height. `min-h-0` overrides this and allows the child to shrink to its allocated flex space.

### 3.2 Inner Scroll Wrapper

The existing template's top-level `<div class="flex-1 overflow-auto relative">` becomes the natural scroll container once the host is correctly sized. No change to the `overflow-auto` class is needed. However, the `flex-1` must be replaced with `flex-1 min-h-0` to be safe in nested flex contexts:

```html
<!-- Before -->
<div class="flex-1 overflow-auto relative">

<!-- After -->
<div class="flex-1 min-h-0 overflow-y-auto overflow-x-hidden relative syn-scrollbar">
```

Key changes:
- `overflow-auto` → `overflow-y-auto overflow-x-hidden`: Enables only vertical scrolling (horizontal is out of scope per requirements).
- `syn-scrollbar` class: Applies the globally defined custom scrollbar styling from `styles.css` (thin, `#cbd5e1` thumb, consistent with the Synergy Design System aesthetics).
- `min-h-0` added: Extra safety guard for the inner flex child.

### 3.3 Sticky Header Continuity

The existing `sticky top-0 z-20` on each `<th>` is architecturally correct once the scroll container is the immediate parent of the `<table>`. After Fix 3.1 and 3.2, the `overflow-y-auto` div is the direct scroll container and the sticky headers will function correctly. **No changes are needed to the `<th>` elements.**

One subtle risk: Chrome requires `border-collapse: separate` (the default) for `sticky` `<th>` to work inside a scrollable overflow container. Do NOT add `border-collapse: collapse` to the table. The existing `syn-table--default` Synergy class and per-cell `border-b` borders already achieve the visual separation without `border-collapse: collapse`.

### 3.4 Auto-Scroll on Live Streaming

The `LogsStoreService` already has `autoScroll: boolean` state (default `true`) and the `addEntry()` mutation prepends new entries. For live streaming, the auto-scroll requirement (requirements.md line 47) means the scroll container should jump to the **top** of the list when new entries arrive (since `addEntry()` prepends, newest entries are at `scrollTop = 0`).

Implementation: Use Angular's `viewChild` to get a reference to the scroll container div, then use an `effect()` that watches `entries()` and, when `autoScroll()` is true and `isStreaming()` is true, calls `scrollContainer.scrollTop = 0`.

```typescript
// In LogsTableComponent:
protected readonly scrollContainer = viewChild<ElementRef<HTMLDivElement>>('scrollContainer');

constructor() {
  effect(() => {
    const entries = this.entries();
    if (this.autoScroll() && this.isStreaming() && entries.length > 0) {
      // New entries prepended — scroll to top
      const el = this.scrollContainer()?.nativeElement;
      if (el) el.scrollTop = 0;
    }
  });
}
```

The scroll container `<div>` must be given `#scrollContainer` template reference variable.

> **Note**: `autoScroll` and `isStreaming` inputs must be threaded from `LogsComponent` through to `LogsTableComponent`.

### 3.5 Scroll Position Persistence During Entry Selection

When a user clicks a row, `LogsDetailComponent` opens and takes `h-75` (300px) from the flex column. This causes the table container to shrink. Because the scroll container uses `overflow-y-auto`, the browser naturally preserves the `scrollTop` value — no Angular-side intervention is needed. **No changes are required here.**

### 3.6 Load More — Scroll Anchor

When "Load More" appends entries at the bottom, the scroll position must not jump. Since `appendEntries()` adds to the end of the array and the browser preserves `scrollTop` during DOM extensions at the bottom, this works correctly by default. **No changes are required.**

---

## 4. CSS Changes Summary

### 4.1 `styles.css` (global, no changes needed)

The `.syn-scrollbar` class already exists in `styles.css` with the correct `scrollbar-width: thin` and `scrollbar-color` properties. It will be applied to the scroll container in the table template. **No modifications to `styles.css` are required.**

### 4.2 `app.css` (no changes needed)

`app.css` governs `html`, `body`, `app-root`, and `syn-dialog`. The logs page scroll fix does not require any global overrides. **No modifications to `app.css` are required.**

### 4.3 `logs-table.component.ts` — template & host changes

All CSS changes are applied through Tailwind utility classes in the component template and Angular `host` metadata:

| Location | Before | After | Reason |
|---|---|---|---|
| `@Component host` metadata | *(absent)* | `class: 'flex flex-col flex-1 min-h-0 overflow-hidden'` | Fix host element flex participation |
| Inner scroll `<div>` | `flex-1 overflow-auto relative` | `flex-1 min-h-0 overflow-y-auto overflow-x-hidden relative syn-scrollbar` | Vertical-only scroll, styled scrollbar, safe min-height |
| Scroll `<div>` template ref | *(absent)* | `#scrollContainer` | Allow viewChild access for auto-scroll |

No `.css` component stylesheet file is needed — the component currently uses an inline template and no `styleUrl`.

---

## 5. Angular 20 & Synergy UI Integration

### 5.1 Signal Inputs — New Props for LogsTableComponent

To support auto-scroll, two new Signal inputs are added to `LogsTableComponent`:

```typescript
autoScroll = input<boolean>(true);
isStreaming = input<boolean>(false);
```

These are threaded from `LogsComponent` (which already reads both from `LogsStoreService`):

```html
<!-- logs.component.html — existing app-logs-table binding -->
<app-logs-table
  [autoScroll]="autoScroll()"
  [isStreaming]="isStreaming()"
  ...
/>
```

### 5.2 `viewChild` for DOM Access

Angular 20 `viewChild` (Signal-based) is used to get the scroll container reference. This is the correct Angular pattern for direct DOM manipulation within a component — it avoids `@ViewChild` decorator syntax and follows the codebase's Signals-first convention.

```typescript
protected readonly scrollContainer = viewChild<ElementRef<HTMLDivElement>>('scrollContainer');
```

### 5.3 `effect()` for Auto-Scroll Reaction

A reactive `effect()` in the component constructor watches `entries()`, `autoScroll()`, and `isStreaming()` together. Because effects run after each render cycle, `scrollTop = 0` is set after the DOM has been updated with the new prepended entries:

```typescript
effect(() => {
  const entries = this.entries();   // tracked reactive dependency
  const shouldScroll = this.autoScroll() && this.isStreaming();
  if (shouldScroll && entries.length > 0) {
    const el = this.scrollContainer()?.nativeElement;
    if (el) el.scrollTop = 0;
  }
});
```

> `effect()` must be called inside the component constructor (not `ngOnInit`) for correct dependency tracking per Angular 20 Signals spec.

### 5.4 Synergy UI Components — No Changes

`syn-badge`, `syn-spinner`, `syn-button`, and `syn-icon` inside the table template are unaffected. Synergy Web Components (`syn-*`) render in Shadow DOM and do not conflict with the host or scroll container layout.

### 5.5 No New Components or Services

This feature requires zero new components, services, or Angular CLI scaffold commands. All changes are confined to existing files.

---

## 6. Accessibility

### 6.1 Keyboard Navigation

The scroll container `<div>` must be keyboard-accessible for Page Up / Page Down / Arrow key scrolling. A scrollable `<div>` that is not itself focusable will not receive key events. Two approaches:

**Preferred (Approach A — Tailwind):** Add `tabindex="0"` directly to the scroll container `<div>`. This makes the div focusable via Tab key and allows keyboard scroll events. The table rows remain individually clickable.

```html
<div #scrollContainer tabindex="0"
  class="flex-1 min-h-0 overflow-y-auto overflow-x-hidden relative syn-scrollbar focus:outline-none focus-visible:ring-2 focus-visible:ring-syn-color-primary-300">
```

- `focus:outline-none`: Removes the default browser focus ring on click (avoids visual noise during mouse use).
- `focus-visible:ring-2 focus-visible:ring-syn-color-primary-300`: Shows a subtle focus ring only during keyboard navigation (modern `:focus-visible` pseudo-class).

### 6.2 ARIA Role

Add `role="region"` and `aria-label="Log entries"` to the scroll container `<div>` so screen readers can identify it as a distinct scrollable region:

```html
<div #scrollContainer
  role="region"
  aria-label="Log entries"
  tabindex="0"
  ...>
```

### 6.3 Table Semantics

The existing `<table>`, `<thead>`, `<tbody>`, `<th>`, `<tr>`, `<td>` structure is semantically correct HTML for tabular data and requires no changes. Screen readers will correctly announce column headers for each row.

---

## 7. Component Interaction & Data Flow Diagram

```
LogsStoreService
  ├── entries:      Signal<LogEntry[]>
  ├── autoScroll:   Signal<boolean>       (true by default)
  └── isStreaming:  Signal<boolean>

LogsComponent  [smart, h-full flex-col]
  ├── reads: entries, autoScroll, isStreaming, displayEntries, isLoading,
  │          isLoadingMore, selectedEntry
  ├── writes: store.addEntry(), store.setStreaming(), etc.
  │
  └── <div .flex-1.min-h-0 ...flex-col>             ← outer flex column
        ├── <app-logs-toolbar />                     ← shrinks to its content height
        │
        ├── <div .flex-1.min-h-0 ...flex-col>        ← remaining space split between table + detail
        │     │
        │     ├── <app-logs-table                    ← host: flex flex-col flex-1 min-h-0 overflow-hidden
        │     │     [entries]="displayEntries()"
        │     │     [autoScroll]="autoScroll()"      ← NEW
        │     │     [isStreaming]="isStreaming()"     ← NEW
        │     │     ...
        │     │   >
        │     │       <div #scrollContainer           ← overflow-y-auto, syn-scrollbar, tabindex="0"
        │     │             role="region"
        │     │             aria-label="Log entries">
        │     │         <table class="syn-table--default w-full">
        │     │           <thead> [sticky top-0 z-20] </thead>  ← sticky within scrollContainer
        │     │           <tbody> @for entries </tbody>
        │     │         </table>
        │     │         [Load More button]
        │     │       </div>
        │     │   </app-logs-table>
        │     │
        │     └── <app-logs-detail />                ← h-75 fixed, open/close animation
        │
        └── [status bar: isStreaming / streamError]
```

---

## 8. Files Changed Summary

| File | Change Type | Description |
|---|---|---|
| `web/src/app/features/logs/components/logs-table.component.ts` | **Modify** | Add `host` class binding; update scroll `<div>` classes; add `#scrollContainer` template ref; add `autoScroll` and `isStreaming` signal inputs; add `viewChild` + `effect()` for auto-scroll |
| `web/src/app/features/logs/logs.component.html` | **Modify** | Pass new `[autoScroll]` and `[isStreaming]` inputs to `<app-logs-table>` |
| `web/src/styles.css` | No change | `.syn-scrollbar` already present |
| `web/src/app/app.css` | No change | No global overrides needed |
| All other files | No change | — |

---

## 9. Non-Goals (Confirmed Out of Scope)

- Virtual scrolling / windowing for extremely large datasets (100k+ entries)
- Horizontal scroll support
- Mobile/touch scroll optimisation
- Scroll position memory between page navigations
- Infinite scroll (retains "Load More" pattern)
- Custom scroll animations
- Performance monitoring integration for scroll metrics
- Any backend, API, or WebSocket changes
