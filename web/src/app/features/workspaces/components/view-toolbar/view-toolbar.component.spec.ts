// @vitest-environment jsdom
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { ViewToolbarComponent } from './view-toolbar.component';
import { SplitLayoutStoreService } from '@core/services/split-layout-store.service';

describe('ViewToolbarComponent', () => {
  let component: ViewToolbarComponent;
  let fixture: ComponentFixture<ViewToolbarComponent>;
  let mockLayout: any;

  beforeEach(async () => {
    mockLayout = {
      canAddPane: signal(true),
      addPane: vi.fn(),
      resetToDefault: vi.fn(),
    };

    await TestBed.configureTestingModule({
      imports: [ViewToolbarComponent],
      providers: [
        { provide: SplitLayoutStoreService, useValue: mockLayout },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ViewToolbarComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should render 4 add-view buttons', () => {
    const allButtons = fixture.nativeElement.querySelectorAll('syn-button, button');
    expect(allButtons.length).toBeGreaterThanOrEqual(4);
  });

  it('should call addPane("perspective") when Perspective button is clicked', () => {
    component.addView('perspective');
    expect(mockLayout.addPane).toHaveBeenCalledWith('perspective');
  });

  it('should call addPane("top") when Top button is clicked', () => {
    component.addView('top');
    expect(mockLayout.addPane).toHaveBeenCalledWith('top');
  });

  it('should call addPane("front") when Front button is clicked', () => {
    component.addView('front');
    expect(mockLayout.addPane).toHaveBeenCalledWith('front');
  });

  it('should call addPane("side") when Side button is clicked', () => {
    component.addView('side');
    expect(mockLayout.addPane).toHaveBeenCalledWith('side');
  });

  it('should call resetToDefault() when Reset Layout is clicked', () => {
    component.resetLayout();
    expect(mockLayout.resetToDefault).toHaveBeenCalled();
  });

  it('should expose canAdd as a signal from the layout store', () => {
    mockLayout.canAddPane.set(false);
    fixture.detectChanges();
    expect(component.canAdd()).toBeFalsy();
  });
});
