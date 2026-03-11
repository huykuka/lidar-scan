import {
  Component,
  input,
  output,
  inject,
  computed,
  CUSTOM_ELEMENTS_SCHEMA,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { LidarProfilesApiService } from '../../../../core/services/api/lidar-profiles-api';

@Component({
  selector: 'app-lidar-type-select',
  standalone: true,
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  imports: [CommonModule, SynergyComponentsModule],
  templateUrl: './lidar-type-select.component.html',
})
export class LidarTypeSelectComponent {
  private lidarProfilesApi = inject(LidarProfilesApiService);

  label = input<string>('LiDAR Type');
  value = input<string>('');
  helpText = input<string>('');

  valueChange = output<string>();

  protected options = computed(() =>
    this.lidarProfilesApi.profiles().map((profile) => ({
      value: profile.model_id,
      label: profile.display_name,
      imageSrc: profile.thumbnail_url,
    })),
  );

  protected selectedOption = computed(() => {
    const val = this.value();
    return this.options().find((opt) => opt.value === val) ?? null;
  });

  onSelectChange(event: Event) {
    const value = (event.target as any).value;
    this.valueChange.emit(value);
  }

  handleImageError(event: Event) {
    (event.target as HTMLImageElement).style.display = 'none';
  }
}
