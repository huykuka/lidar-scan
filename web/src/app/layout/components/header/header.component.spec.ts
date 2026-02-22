import { TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';

import { HeaderComponent } from './header.component';
import { SystemStatusService } from '../../../core/services/system-status.service';

describe('HeaderComponent', () => {
  it('computes status dot class from backendOnline', async () => {
    const backendOnline = signal<boolean | null>(null);
    const backendVersion = signal<string | null>(null);
    const activeSensors = signal<string[]>([]);
    const unreadCount = signal<number>(0);
    const lastNotice = signal<any>(null);

    await TestBed.configureTestingModule({
      imports: [HeaderComponent],
      providers: [
        {
          provide: SystemStatusService,
          useValue: {
            backendOnline,
            backendVersion,
            activeSensors,
            unreadCount,
            lastNotice,
            backendLabel: () => 'Checking',
            acknowledge: () => {},
            refreshNow: () => {},
          },
        },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(HeaderComponent);
    fixture.detectChanges();

    const cmp = fixture.componentInstance as any;
    expect(cmp.statusDotClass()).toContain('neutral');

    backendOnline.set(true);
    fixture.detectChanges();
    expect(cmp.statusDotClass()).toContain('success');

    backendOnline.set(false);
    fixture.detectChanges();
    expect(cmp.statusDotClass()).toContain('danger');
  });
});
