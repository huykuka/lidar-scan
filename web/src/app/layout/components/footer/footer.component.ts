import {Component, ChangeDetectionStrategy} from '@angular/core';


@Component({
  selector: 'app-footer',
  standalone: true,
  imports: [],
  templateUrl: './footer.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './footer.component.css',
})
export class FooterComponent {
  year =  new Date().getFullYear()
}
