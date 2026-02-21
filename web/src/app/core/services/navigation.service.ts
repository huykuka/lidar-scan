import { Injectable, inject, signal } from '@angular/core';
import { Title } from '@angular/platform-browser';

@Injectable({
  providedIn: 'root',
})
export class NavigationService {
  private titleService = inject(Title);
  private readonly _headline = signal('Start');
  readonly headline = this._headline.asReadonly();

  setHeadline(title: string) {
    this._headline.set(title);
    this.titleService.setTitle(`${title} | LiDAR Command Surface`);
  }
}
