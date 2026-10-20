import {Injectable, computed, signal} from '@angular/core';

const STORAGE_KEY = 'app-onboarding-completed';

export interface TourStep {
  title: string;
  body: string;
  /** CSS selector of the element to spotlight; centered card when absent or not found. */
  target?: string;
}

export const TOUR_STEPS: TourStep[] = [
  {
    title: 'Workspaces',
    body: 'Your live 3D view. Split the viewport into panes and watch point clouds from your sensors in real time.',
    target: '[data-tour="nav-/workspaces"]',
  },
  {
    title: 'Settings',
    body: 'Build your processing pipeline here: add sensors, filters, fusion and output nodes, then connect them in the flow editor.',
    target: '[data-tour="nav-/settings"]',
  },
  {
    title: 'Recordings & Replays',
    body: 'Record sensor streams, play them back later and compare runs without needing the hardware.',
    target: '[data-tour="nav-/recordings"]',
  },
  {
    title: 'Results',
    body: 'Inspect the output produced by your pipeline nodes.',
    target: '[data-tour="nav-/results"]',
  },
  {
    title: 'Logs & Resource Monitor',
    body: 'Troubleshoot with live logs and keep an eye on CPU, memory and other host resources.',
    target: '[data-tour="nav-/host"]',
  },
  {
    title: 'Platform Guide',
    body: 'Need a refresher? Open the help icon any time for the full guide, or restart this tour from there.',
    target: '[data-tour="platform-guide"]',
  },
];

/**
 * OnboardingService
 *
 * Tracks whether the first-run welcome screen / guided tour was completed
 * (persisted in localStorage) and drives the tour state.
 */
@Injectable({providedIn: 'root'})
export class OnboardingService {
  private readonly completed = signal(this.readCompleted());

  readonly showWelcome = signal(!this.completed());
  readonly tourStep = signal<number | null>(null);

  readonly steps = TOUR_STEPS;
  readonly isTouring = computed(() => this.tourStep() !== null);

  startTour(): void {
    this.showWelcome.set(false);
    this.tourStep.set(0);
  }

  /** Re-open the welcome screen manually (e.g. from the help menu). */
  reopen(): void {
    this.tourStep.set(null);
    this.showWelcome.set(true);
  }

  next(): void {
    const step = this.tourStep();
    if (step === null) return;
    if (step >= this.steps.length - 1) {
      this.finish();
    } else {
      this.tourStep.set(step + 1);
    }
  }

  back(): void {
    const step = this.tourStep();
    if (step !== null && step > 0) this.tourStep.set(step - 1);
  }

  /** Skip or finish: closes everything and remembers it. */
  finish(): void {
    this.showWelcome.set(false);
    this.tourStep.set(null);
    this.completed.set(true);
    try {
      localStorage.setItem(STORAGE_KEY, 'true');
    } catch {
      // Storage unavailable (private mode) — welcome will show again next visit.
    }
  }

  private readCompleted(): boolean {
    try {
      return localStorage.getItem(STORAGE_KEY) === 'true';
    } catch {
      return false;
    }
  }
}
