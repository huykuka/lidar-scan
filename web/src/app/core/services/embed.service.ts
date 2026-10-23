import {Injectable} from '@angular/core';

export type UiPart = 'header' | 'nav' | 'toolbar' | 'settings' | 'legend' | 'onboarding';

const TRUTHY = new Set(['1', 'true', 'on']);
const FALSY = new Set(['0', 'false', 'off']);

/**
 * Embedded (iframe) mode and per-part visibility. Read once at boot so it
 * survives in-app navigation, which drops the query string.
 *
 *   ?embed=1               hides header, nav and onboarding
 *   ?header=0|1            top bar
 *   ?nav=0|1               side navigation
 *   ?toolbar=0|1           workspace layout/view switcher
 *   ?settings=0|1          workspace right-hand controls panel
 *   ?legend=0|1            topic colour legend
 *
 * An explicit flag always wins over the `embed` default.
 */
@Injectable({providedIn: 'root'})
export class EmbedService {
  private readonly params = new URLSearchParams(window.location.search);

  readonly isEmbedded: boolean = TRUTHY.has(this.params.get('embed') ?? '');

  private readonly hiddenWhenEmbedded: ReadonlySet<UiPart> = new Set(['header', 'nav', 'onboarding']);

  /** Whether a UI part should be rendered. */
  show(part: UiPart): boolean {
    const raw = this.params.get(part) ?? '';
    if (TRUTHY.has(raw)) return true;
    if (FALSY.has(raw)) return false;
    return !(this.isEmbedded && this.hiddenWhenEmbedded.has(part));
  }
}
