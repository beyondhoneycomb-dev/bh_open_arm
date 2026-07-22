// Vitest setup: jest-dom matchers for the shell component tests. No network stub
// is installed globally — tests that exercise the REST config client inject their
// own fetch, so an accidental real fetch in a test fails loudly instead of
// silently reaching a backend that is not there.

import "@testing-library/jest-dom/vitest";
