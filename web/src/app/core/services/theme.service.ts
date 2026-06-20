import {Injectable, signal, effect, PLATFORM_ID, inject} from '@angular/core';
import {isPlatformBrowser} from '@angular/common';

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'app-theme';
const DARK_CLASS = 'syn-theme-dark';

@Injectable({providedIn: 'root'})
export class ThemeService {
  private readonly platformId = inject(PLATFORM_ID);
  private readonly isBrowser = isPlatformBrowser(this.platformId);

  readonly theme = signal<Theme>(this.resolveInitialTheme());

  constructor() {
    // Keep DOM in sync whenever theme signal changes
    effect(() => {
      const t = this.theme();
      if (!this.isBrowser) return;
      const html = document.documentElement;
      if (t === 'dark') {
        html.classList.add(DARK_CLASS);
      } else {
        html.classList.remove(DARK_CLASS);
      }
      localStorage.setItem(STORAGE_KEY, t);
    });
  }

  toggle(): void {
    this.theme.update(t => (t === 'dark' ? 'light' : 'dark'));
  }

  setTheme(t: Theme): void {
    this.theme.set(t);
  }

  private resolveInitialTheme(): Theme {
    if (!this.isBrowser) return 'light';
    const stored = localStorage.getItem(STORAGE_KEY) as Theme | null;
    if (stored === 'dark' || stored === 'light') return stored;
    // Fall back to OS preference
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
}
