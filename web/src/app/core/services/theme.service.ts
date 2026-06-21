import { computed, effect, inject, Injectable, PLATFORM_ID, signal } from '@angular/core';
import { DOCUMENT, isPlatformBrowser } from '@angular/common';

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'app-theme';
const DARK_CLASS = 'syn-theme-dark';

/**
 * ThemeService
 *
 * Manages light/dark mode by:
 * 1. Swapping the Synergy token CSS file via the #app-theme <link> tag
 * 2. Toggling `syn-theme-dark` on <html> for Synergy and `dark` for Tailwind's darkMode: 'selector'
 * 3. Persisting the preference to localStorage
 */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly platformId = inject(PLATFORM_ID);
  private readonly document = inject(DOCUMENT);
  private readonly isBrowser = isPlatformBrowser(this.platformId);

  readonly theme = signal<Theme>(this.resolveInitialTheme());

  /** Convenience computed signal — true when dark mode is active */
  readonly isDark = computed(() => this.theme() === 'dark');

  /** @deprecated Use theme signal instead */
  get isDarkTheme(): boolean { return this.theme() === 'dark'; }
  set isDarkTheme(v: boolean) { this.apply(v ? 'dark' : 'light'); }

  constructor() {
    // Keep DOM in sync whenever theme signal changes
    effect(() => {
      this.applyToDom(this.theme());
    });
  }

  toggle(): void {
    this.theme.update(t => (t === 'dark' ? 'light' : 'dark'));
  }

  setTheme(t: Theme): void {
    this.theme.set(t);
  }

  /** Called by AppInitService on startup (optional — theme self-initialises) */
  checkTheme(): void {
    const stored = localStorage.getItem(STORAGE_KEY) as Theme | null;
    const prefersDark = this.isBrowser && window.matchMedia('(prefers-color-scheme: dark)').matches;
    this.apply(stored ?? (prefersDark ? 'dark' : 'light'));
  }

  /** @deprecated Use toggle() */
  apply(theme: Theme): void {
    this.theme.set(theme);
  }

  private applyToDom(theme: Theme): void {
    if (!this.isBrowser) return;

    const html = this.document.documentElement;

    // Synergy class
    if (theme === 'dark') {
      html.classList.add(DARK_CLASS);
    } else {
      html.classList.remove(DARK_CLASS);
    }

    // Tailwind darkMode: 'selector'
    if (theme === 'dark') {
      html.classList.add('dark');
    } else {
      html.classList.remove('dark');
    }

    // Swap Synergy CSS token file
    const link = this.document.getElementById('app-theme') as HTMLLinkElement | null;
    if (link) {
      link.href = `assets/themes/${theme}.css`;
    }

    localStorage.setItem(STORAGE_KEY, theme);
  }

  private resolveInitialTheme(): Theme {
    if (!this.isBrowser) return 'light';
    const stored = localStorage.getItem(STORAGE_KEY) as Theme | null;
    if (stored === 'dark' || stored === 'light') return stored;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
}
