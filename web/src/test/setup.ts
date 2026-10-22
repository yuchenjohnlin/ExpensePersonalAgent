import "@testing-library/jest-dom/vitest";

// jsdom lays nothing out, so it has no ResizeObserver; the tables only use it to measure width.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};
