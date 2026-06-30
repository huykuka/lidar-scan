import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { App } from './app/app';
import { setGlobalDefaultSettings } from '@synergy-design-system/components';

import * as THREE from 'three';

// Set size="small" globally for all Synergy components that support it
setGlobalDefaultSettings({
  size: {
    SynAccordion: 'small',
    SynAlert: 'small',
    SynButton: 'small',
    SynButtonGroup: 'small',
    SynCheckbox: 'small',
    SynCombobox: 'small',
    SynDetails: 'small',
    SynFile: 'small',
    SynIconButton: 'small',
    SynInput: 'small',
    SynPagination: 'small',
    SynRadio: 'small',
    SynRadioButton: 'small',
    SynRadioGroup: 'small',
    SynRange: 'small',
    SynSelect: 'small',
    SynSwitch: 'small',
    SynTag: 'small',
    SynTagGroup: 'small',
    SynTextarea: 'small',
  },
});

// Must be before bootstrapApplication()
THREE.Object3D.DEFAULT_UP.set(0, 0, 1);

bootstrapApplication(App, appConfig).catch((err) => console.error(err));
