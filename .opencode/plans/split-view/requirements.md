# Split-View Feature - Requirements Document

## Feature Overview

The Split-View feature enables users to dynamically add, arrange, and manage multiple orthometric viewport windows within the main workspace page. Users can view the same point cloud data from different camera orientations (Perspective, Top, Front, Side) simultaneously, enabling better spatial understanding and analysis of 3D point cloud data.

This feature enhances the existing single-view workspace by introducing a flexible split-pane layout system where users can:
- Add up to 4 concurrent views via toolbar buttons
- Resize views by dragging dividers between panes
- Switch view orientations using in-view dropdown controls
- Maintain independent camera controls per view
- Persist layout configurations across browser sessions

## User Stories

### US-1: Add Orthometric Views
**As a** point cloud analyst  
**I want to** add Top, Front, and Side orthometric views to my workspace  
**So that** I can analyze the point cloud from multiple standardized angles simultaneously without manually rotating the camera

### US-2: Resize and Arrange Views
**As a** user working with complex point cloud data  
**I want to** resize individual views by dragging dividers  
**So that** I can allocate more screen space to the views that are most important for my current task

### US-3: Independent Camera Control
**As a** user analyzing spatial relationships  
**I want to** pan, zoom, and rotate cameras independently in each view  
**So that** I can focus on different areas or details in each viewport without affecting the others

### US-4: Persistent Layout
**As a** frequent user  
**I want to** have my view layout saved between sessions  
**So that** I don't have to recreate my preferred workspace configuration every time I open the application

### US-5: Switch View Orientations
**As a** user adjusting my workspace  
**I want to** change the orientation of an existing view without closing and recreating it  
**So that** I can quickly adapt my workspace to different analysis needs

### US-6: Keyboard Navigation
**As a** power user  
**I want to** use keyboard shortcuts to add, close, and navigate between views  
**So that** I can work more efficiently without relying solely on mouse interactions

### US-7: Performance at Scale
**As a** user working with large point clouds (100k+ points)  
**I want to** maintain smooth 60 FPS rendering across all active views  
**So that** I can interact with the data in real-time without lag or stuttering

## Acceptance Criteria

### View Management
- [ ] Toolbar at the top of the workspace provides buttons to add: Perspective, Top, Front, Side views
- [ ] Users can add up to 4 concurrent views maximum
- [ ] At least 1 view must always remain active (cannot close the last view)
- [ ] When adding a new view, the system splits the largest existing view in half
- [ ] Split direction (horizontal/vertical) is determined automatically based on the largest view's aspect ratio
- [ ] Each view displays a minimal overlay in the corner showing:
  - Orientation label (e.g., "TOP", "SIDE", "PERSPECTIVE")
  - Dropdown to change orientation type
  - Close button (×)
- [ ] Clicking the close button removes that view and redistributes space to remaining views
- [ ] Toolbar includes a "Reset Layout" button that restores the default single perspective view

### Resizing and Layout
- [ ] Users can drag dividers between adjacent views to resize them
- [ ] Minimum view size is enforced: 200px × 200px
- [ ] Split-pane resize operations update smoothly with 200-300ms CSS transitions
- [ ] Layout system prevents resizing beyond minimum size constraints
- [ ] All views share available workspace space dynamically

### View Orientation Types
- [ ] Available orientations: Perspective (default 3D), Top (XY plane), Front (XZ plane), Side (YZ plane)
- [ ] Users can change a view's orientation using the in-view dropdown menu
- [ ] Changing orientation preserves the view's position in the layout
- [ ] Each orientation type can appear multiple times (e.g., two Top views is allowed)

### Camera Behavior
- [ ] Each view has independent camera controls (pan, zoom, rotate)
- [ ] Camera movements in one view do NOT affect other views
- [ ] Orthometric views (Top, Front, Side) use orthographic camera projection
- [ ] Perspective view uses standard perspective camera projection
- [ ] Camera state is NOT persisted between sessions (resets to defaults)

### Data Rendering
- [ ] All views display the same point cloud data
- [ ] Point cloud updates via WebSocket are shared across all views using a single connection
- [ ] Each view renders independently using Three.js BufferGeometry
- [ ] Performance target: maintain 60 FPS across all views with 100k+ point clouds
- [ ] If performance target cannot be met with multiple views, system should reduce point density or detail level in smaller views

### Empty State
- [ ] When no point cloud is loaded, each view displays:
  - Large orientation label (e.g., "TOP VIEW")
  - Hint text: "No point cloud loaded"
- [ ] Empty views maintain their layout position and controls

### Persistence
- [ ] Layout configuration is saved to browser localStorage:
  - Number of views
  - Position and size of each view
  - Orientation type of each view
- [ ] Layout is automatically restored when user returns to the workspace
- [ ] If localStorage data is corrupted or unavailable, gracefully fallback to default single perspective view
- [ ] No error messages shown to user on localStorage failures

### Keyboard Shortcuts
- [ ] `Ctrl+T` - Add Top view
- [ ] `Ctrl+F` - Add Front view  
- [ ] `Ctrl+S` - Add Side view
- [ ] `Ctrl+1` - Focus first view
- [ ] `Ctrl+2` - Focus second view
- [ ] `Ctrl+3` - Focus third view
- [ ] `Ctrl+4` - Focus fourth view
- [ ] `Ctrl+W` - Close currently focused view
- [ ] Focus state is indicated by keyboard interaction only (no visual highlight)
- [ ] Keyboard shortcuts work when any view has focus

### Responsive Behavior
- [ ] Split-view feature is disabled on screens narrower than 1024px
- [ ] On screens <1024px, display message: "Split-view requires desktop screen (min. 1024px width)"
- [ ] On screens <1024px, workspace reverts to single view only
- [ ] Layout preferences are preserved but not applied until screen size increases

### Error Handling
- [ ] If one view fails to render, show error message in that view only; other views continue functioning
- [ ] WebSocket connection errors do not crash the view layout system
- [ ] Console logging for all view-related errors (for developer debugging)
- [ ] Graceful degradation: if Three.js rendering fails in a view, show error message instead of blank screen

### Performance Requirements
- [ ] Target: 60 FPS rendering across all views with 100k point clouds
- [ ] Acceptable: No more than 10% FPS drop compared to single view
- [ ] Smooth layout transitions (200-300ms) when adding/removing/resizing views
- [ ] WebSocket data processing overhead <5ms per frame
- [ ] No memory leaks when creating/destroying views repeatedly

## Out of Scope

### Not Included in This Release
- **Camera synchronization between views** - All cameras operate independently. Synchronized pan/zoom/rotation is not supported.
- **Multiple point clouds per view** - All views always display the same point cloud data. Cannot assign different clouds to different views.
- **Server-side layout persistence** - Layout is stored in browser localStorage only, not synced across devices.
- **Free-floating/overlapping windows** - Views are constrained to split-pane layout. No "floating window" mode.
- **Custom view orientations** - Only standard orthometric views (Top, Front, Side) + Perspective are supported. Cannot define arbitrary camera angles as saved views.
- **View templates or presets** - No pre-defined layout templates (e.g., "Quad View", "Engineer View"). Users must manually configure layouts.
- **Per-view rendering settings** - All views share the same point cloud rendering quality, color scheme, and visual settings. No per-view customization.
- **Tab-based view switching** - No tabbed interface for views; split-pane only.
- **Mobile/touch optimization** - Feature is desktop-only (>1024px). No touch-specific gestures or mobile-optimized UI.
- **View zoom synchronization** - Even though cameras are independent, zoom level synchronization is out of scope.
- **Annotation/markup tools per view** - Any future annotation features will apply globally, not per-view.
- **Screen reader accessibility** - Only keyboard navigation is in scope. ARIA labels and screen reader optimization are deferred.
- **High contrast mode** - Standard Synergy UI theme support only. No specialized high-contrast view borders.
- **View history/undo for layout changes** - Cannot undo view splits or layout changes.
- **Export/import layout configurations** - Cannot share layout JSON with other users.

## Edge Cases & Constraints

### Edge Case: Maximum Views Reached
- When 4 views are active, toolbar buttons to add new views are disabled (grayed out)
- Attempting to add a view via keyboard shortcut when at max shows brief toast notification: "Maximum 4 views reached"

### Edge Case: Minimum View Size Violation
- When resizing would result in a view smaller than 200×200px, the divider stops moving
- Cursor changes to "not-allowed" when attempting to resize beyond constraint

### Edge Case: Last View Closure Attempt
- Close button on the last remaining view is disabled (grayed out)
- Pressing `Ctrl+W` with only one view active has no effect

### Edge Case: Rapid View Creation/Deletion
- System debounces add/remove operations to prevent race conditions
- Layout transitions queue sequentially, preventing overlapping animations

### Edge Case: Browser Window Resize
- When browser window is resized, views scale proportionally to maintain relative sizes
- If window shrinks below 1024px, layout is saved and single-view mode activates
- If window expands back above 1024px, previous layout is restored

### Edge Case: localStorage Quota Exceeded
- If localStorage is full, silently fail to save layout
- Application continues to function normally without persistence
- Console warning logged for developers

### Edge Case: Corrupted Layout Data
- If layout JSON in localStorage is invalid/corrupted:
  - Ignore persisted layout
  - Reset to default single perspective view
  - Clear corrupted data from localStorage
  - No user-facing error message

### Edge Case: WebSocket Disconnect During Multi-View
- All views show "Disconnected" state simultaneously
- When WebSocket reconnects, all views resume updating
- No need to recreate views or reset layout

### Edge Case: Point Cloud Too Large for Performance Target
- If FPS drops below 30 in multi-view mode:
  - System should automatically reduce point density in views smaller than 50% of workspace
  - Show subtle warning icon in affected views: "Rendering simplified for performance"
  - Performance downgrade affects smaller views first, largest view last

### Constraint: Three.js Rendering Context Limit
- Each view creates its own Three.js renderer and scene
- Maximum 4 WebGL contexts supported (one per view)
- Exceeding this limit is prevented by the max 4-view constraint

### Constraint: Angular Change Detection
- Use Angular Signals and `OnPush` change detection for all view components
- Prevent unnecessary re-renders when other views update

### Constraint: Synergy UI and Tailwind CSS
- All UI components (toolbar, dropdowns, buttons) must use Synergy Design System
- Layout styling must use Tailwind CSS utility classes
- No custom CSS except for split-pane divider interaction states

## Success Metrics

### Functional Success
- Users can successfully add, resize, and remove views without errors
- Layout persists correctly across browser sessions in >95% of cases
- All keyboard shortcuts function as specified

### Performance Success  
- 60 FPS maintained in quad-view mode with 100k point cloud on recommended hardware
- View split/close animations complete within 200-300ms
- WebSocket data processing adds <5ms latency per frame in multi-view mode

### User Experience Success
- Users can configure their preferred layout in <30 seconds
- Split-pane dividers respond immediately to drag interactions
- No visual glitches or flickering during layout transitions

## Assumptions & Dependencies

### Assumptions
- Users have modern desktop browsers with WebGL support (Chrome 90+, Firefox 88+, Safari 14+, Edge 90+)
- Users have at least 1920×1080 screen resolution for comfortable 4-view usage
- Point clouds are optimized for real-time rendering (LOD or downsampling applied by backend if needed)
- WebSocket connection is stable and provides consistent data stream

### Dependencies
- **Angular 20**: Signals, standalone components, control flow syntax
- **Three.js**: WebGL rendering, orthographic/perspective cameras, BufferGeometry
- **Synergy UI**: Toolbar, buttons, dropdowns, icons
- **Tailwind CSS**: Layout grid, spacing, responsive utilities
- **Browser localStorage API**: For layout persistence
- **Existing WebSocket Service**: Point cloud data streaming (LIDR protocol)
- **Existing Workspace Component**: Must be refactored to support multi-view layout system

## Open Questions for Architecture/Dev Teams

1. **Split-Pane Library**: Should we use an existing Angular split-pane library (e.g., `angular-split`) or build custom divider drag logic?
2. **Three.js Context Management**: Should we share a single WebGL context across views (more complex) or use separate contexts per view (simpler but higher memory)?
3. **BufferGeometry Sharing**: Can we share the same `BufferGeometry` instance across multiple Three.js scenes, or must each view have its own geometry copy?
4. **WebSocket Data Distribution**: Should the workspace component receive data and distribute to views, or should each view subscribe independently?
5. **Layout State Management**: Should layout state be managed in a service, or within the workspace component using Angular Signals?

---

**Document Status**: Draft Ready for Architecture Review  
**Created**: 2026-03-25  
**Last Updated**: 2026-03-25  
**Author**: Business Analyst Agent  
**Reviewers**: Pending (@architecture, @pm)
