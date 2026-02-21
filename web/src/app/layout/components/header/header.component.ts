import { Component, ViewChild, input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynergyComponentsModule, SynHeaderComponent } from '@synergy-design-system/angular';

@Component({
  selector: 'app-header',
  standalone: true,
  imports: [CommonModule, SynergyComponentsModule],
  templateUrl: './header.component.html',
  styleUrl: './header.component.css',
})
export class HeaderComponent {
  label = input<string>('Synergy');
  @ViewChild('header', { static: true }) synHeader!: SynHeaderComponent;

  get nativeElement() {
    return this.synHeader.nativeElement;
  }
}
