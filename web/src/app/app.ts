import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { SynDialogComponent } from '@synergy-design-system/angular';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, SynDialogComponent],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {}
