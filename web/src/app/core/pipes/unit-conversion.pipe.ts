import { Pipe, PipeTransform } from '@angular/core';

@Pipe({
  name: 'meterToMm',
  standalone: true
})
export class MeterToMmPipe implements PipeTransform {
  transform(value: number | null | undefined): number {
    if (value == null) return 0;
    return value * 1000;
  }
}

@Pipe({
  name: 'mmToMeter',
  standalone: true
})
export class MmToMeterPipe implements PipeTransform {
  transform(value: number | null | undefined): number {
    if (value == null) return 0;
    return value / 1000;
  }
}
