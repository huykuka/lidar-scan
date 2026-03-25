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
      resetToDefault:     vi.fn(),
      setHorizontalSplit: vi.fn(),
      setVerticalSplit:   vi.fn(),
      setFourPaneGrid:    vi.fn(),
      layoutMode:         signal('single'),
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

  it('should expose 4 preset entries', () => {
    expect(component.presets.length).toBe(4);
    const ids = component.presets.map(p => p.id);
    expect(ids).toEqual(['single', 'h-split', 'v-split', '4-grid']);
  });

  it('should render 4 preset buttons', () => {
    const buttons = fixture.nativeElement.querySelectorAll('button[data-preset]');
    expect(buttons.length).toBe(4);
  });

  it('applyPreset("single") calls resetToDefault()', () => {
    component.applyPreset('single');
    expect(mockLayout.resetToDefault).toHaveBeenCalledOnce();
  });

  it('applyPreset("h-split") calls setHorizontalSplit()', () => {
    component.applyPreset('h-split');
    expect(mockLayout.setHorizontalSplit).toHaveBeenCalledOnce();
  });

  it('applyPreset("v-split") calls setVerticalSplit()', () => {
    component.applyPreset('v-split');
    expect(mockLayout.setVerticalSplit).toHaveBeenCalledOnce();
  });

  it('applyPreset("4-grid") calls setFourPaneGrid()', () => {
    component.applyPreset('4-grid');
    expect(mockLayout.setFourPaneGrid).toHaveBeenCalledOnce();
  });

  it('clicking a preset button invokes applyPreset', () => {
    const spy = vi.spyOn(component, 'applyPreset');
    const btn = fixture.nativeElement.querySelector('button[data-preset="v-split"]');
    btn?.click();
    fixture.detectChanges();
    expect(spy).toHaveBeenCalledWith('v-split');
  });
});
