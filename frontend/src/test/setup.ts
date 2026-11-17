import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Vitest globals are off, so Testing Library cannot register this itself.
afterEach(cleanup);

// jsdom has no layout, so scrolling is a no-op rather than an error.
window.scrollTo = () => {};

// jsdom has no object URLs; previews and downloads create and free them.
URL.createObjectURL ??= () => "blob:test";
URL.revokeObjectURL ??= () => {};
