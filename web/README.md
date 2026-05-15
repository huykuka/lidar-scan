# Web

This project was generated using [Angular CLI](https://github.com/angular/angular-cli) version 21.1.4.

## Development server

To start a local development server, run:

```bash
ng serve
```

Once the server is running, open your browser and navigate to `http://localhost:4200/`. The application will automatically reload whenever you modify any of the source files.

## Code scaffolding

Angular CLI includes powerful code scaffolding tools. To generate a new component, run:

```bash
ng generate component component-name
```

For a complete list of available schematics (such as `components`, `directives`, or `pipes`), run:

```bash
ng generate --help
```

## Building

To build the project run:

```bash
ng build
```

This will compile your project and store the build artifacts in the `dist/` directory. By default, the production build optimizes your application for performance and speed.

## Running unit tests

To execute unit tests with the [Vitest](https://vitest.dev/) test runner, use the following command:

```bash
ng test
```

## Running end-to-end tests

For end-to-end (e2e) testing, run:

```bash
ng e2e
```

Angular CLI does not come with an end-to-end testing framework by default. You can choose one that suits your needs.

## Additional Resources

For more information on using the Angular CLI, including detailed command references, visit the [Angular CLI Overview and Command Reference](https://angular.dev/tools/cli) page.

---

## Point Cloud File Serving — Architectural Rule

PCD files produced by backend processing nodes are served as **static assets** via the backend's `/data` mount.

### Contract

The Results API (`GET /api/v1/results/<node_id>/<result_id>`) returns `pcd_files` as an array of `PcdFileEntry`:

```typescript
interface PcdFileEntry {
  label: string;
  path: string; // relative, e.g. 'results/<node_id>/<result_id>/<label>.pcd'
}
```

### URL Formation Rule

The frontend **always** derives the fetch URL as:

```typescript
const url = `/data/${entry.path}`;
// e.g. /data/results/volume_calc_abc123/550e8400.../empty.pcd
```

Use `ResultsApiService.getPcdUrl(entry.path)` to form this URL consistently.

### Rules for Maintainers

- ✅ `pcdUrl` passed to `<app-pcd-viewer>` is always `/data/<relative-path>`
- ✅ `PcdFileEntry.path` is always a **relative** path, never an absolute URL
- ❌ Never use the download API (`/api/.../download`) for point cloud viewing
- ❌ Never proxy PCD requests through the Angular dev server or any HTTP API endpoint
- ❌ Never construct PCD URLs from `node_id` + `result_id` + `label` in components — use `PcdFileEntry.path` directly
