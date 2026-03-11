import {inject, Injectable, signal} from '@angular/core';
import {Title} from '@angular/platform-browser';

export interface PageConfig {
  title: string;
  subtitle?: string;
  showActionsSlot?: boolean;
}

@Injectable({
  providedIn: 'root',
})
export class NavigationService {
  private titleService = inject(Title);
  private readonly _headline = signal('Start');
  readonly headline = this._headline.asReadonly();
  private readonly _subtitle = signal<string | null>(null);
  readonly subtitle = this._subtitle.asReadonly();
  private readonly _showActionsSlot = signal(false);
  readonly showActionsSlot = this._showActionsSlot.asReadonly();

  setHeadline(title: string) {
    this._headline.set(title);
    this._subtitle.set(null);
    this._showActionsSlot.set(false);
    this.titleService.setTitle(`${title} | LiDAR Command Surface`);
  }

  setPageConfig(config: PageConfig) {
    this._headline.set(config.title);
    this._subtitle.set(config.subtitle || null);
    this._showActionsSlot.set(config.showActionsSlot ?? false);
    this.titleService.setTitle(`${config.title} | LiDAR Command Surface`);
  }
}
