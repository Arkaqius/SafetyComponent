import assert from 'node:assert/strict';
import test from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import FreezeFrame from './FreezeFrame.js';

test('renders capture and lifecycle values in a single Freeze frame section', () => {
  const markup = renderToStaticMarkup(
    <FreezeFrame
      record={{ source: { state: 31.2, threshold: 28 }, activation_count: 3, last_valid_pass_at: null, clock_uncertain: false }}
    />
  );
  assert.equal((markup.match(/<section/g) ?? []).length, 1);
  assert.equal((markup.match(/<strong>Freeze frame<\/strong>/g) ?? []).length, 1);
  assert.match(markup, /31\.2/);
  assert.match(markup, /Liczba aktywacji/);
  assert.match(markup, /<dd>3<\/dd>/);
  assert.match(markup, /<dd>—<\/dd>/);
  assert.match(markup, /<dd>Nie<\/dd>/);
  assert.doesNotMatch(markup, /Dane rozszerzone|Extended data/);
});
