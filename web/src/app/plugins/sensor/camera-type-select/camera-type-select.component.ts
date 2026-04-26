import {Component, computed, inject, input, output} from '@angular/core';

import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {VisionaryProfilesApiService} from '@core/services/api/visionary-profiles-api.service';

@Component({
  selector: 'app-camera-type-select',
  imports: [SynergyComponentsModule],
  templateUrl: './camera-type-select.component.html',
})
export class CameraTypeSelectComponent {
  label = input<string>('Camera Model');
  value = input<string>('');
  helpText = input<string>('');
  valueChange = output<string>();
  protected selectedOption = computed(() => {
    const val = this.value();
    return this.options().find((opt) => opt.value === val) ?? null;
  });
  private visionaryProfilesApi = inject(VisionaryProfilesApiService);
  protected options = computed(() =>
    this.visionaryProfilesApi.profiles().map((profile) => ({
      value: profile.model_id,
      label: profile.display_name,
      imageSrc: profile.thumbnail_url,
    })),
  );

  onSelectChange(event: Event) {
    const value = (event.target as any).value;
    this.valueChange.emit(value);
  }

  handleImageError(event: Event) {
    (event.target as HTMLImageElement).style.display = 'none';
  }
}
