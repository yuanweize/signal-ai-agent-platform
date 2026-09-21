import '@testing-library/jest-dom/vitest';

// JSDOM doesn't implement scrollIntoView or scrollTo
if (typeof window !== 'undefined') {
  window.HTMLElement.prototype.scrollIntoView = function () {};
  window.HTMLElement.prototype.scrollTo = function () {};
}
