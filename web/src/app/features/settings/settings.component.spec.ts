import { CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { SettingsComponent } from './settings.component';
import { NavigationService } from '../../core/services/navigation.service';
import { LidarApiService } from '../../core/services/api/lidar-api.service';
import { FusionApiService } from '../../core/services/api/fusion-api.service';
import { DialogService } from '../../core/services/dialog.service';
import { ToastService } from '../../core/services/toast.service';
import { LidarStoreService } from '../../core/services/stores/lidar-store.service';
import { FusionStoreService } from '../../core/services/stores/fusion-store.service';

describe('SettingsComponent', () => {
  it('loads config on init and renders lidar name', async () => {
    // JSDOM doesn't implement the Web Animations API; Synergy's <syn-details>
    // calls `getAnimations()` internally.
    if (!(Element.prototype as any).getAnimations) {
      (Element.prototype as any).getAnimations = () => [];
    }

    await TestBed.configureTestingModule({
      imports: [SettingsComponent],
      schemas: [CUSTOM_ELEMENTS_SCHEMA],
      providers: [
        { provide: NavigationService, useValue: { setHeadline: () => {} } },
        { provide: DialogService, useValue: { open: () => {} } },
        {
          provide: ToastService,
          useValue: {
            success: () => {},
            warning: () => {},
            danger: () => {},
            primary: () => {},
            neutral: () => {},
          },
        },
        {
          provide: LidarApiService,
          useFactory: (store: LidarStoreService) => ({
            getLidars: async () => {
              const lidars: any[] = [{ id: 'l1', name: 'Front', launch_args: '', mode: 'real' }];
              store.setState({ lidars, availablePipelines: [], isLoading: false });
              return { lidars, available_pipelines: [] };
            },
            setEnabled: async () => ({ status: 'success' }),
            deleteLidar: async () => ({ status: 'success' }),
            reloadConfig: async () => ({ status: 'success' }),
            saveLidar: async () => ({ status: 'success' }),
          }),
          deps: [LidarStoreService],
        },
        {
          provide: FusionApiService,
          useFactory: (store: FusionStoreService) => ({
            getFusions: async () => {
              const fusions: any[] = [];
              store.setState({ fusions, isLoading: false });
              return { fusions };
            },
            setEnabled: async () => ({ status: 'success' }),
            deleteFusion: async () => ({ status: 'success' }),
            saveFusion: async () => ({ status: 'success' }),
          }),
          deps: [FusionStoreService],
        },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(SettingsComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).textContent || '').toContain('Front');
  });
});
