// node tests/arcade_library_deadline.mjs
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../league/static/league/arcade-library.js', import.meta.url), 'utf8');
function setup({remaining = 1000, featured = true, valid = true, focused = false} = {}) {
  let clock = 12345, removed = false, focusMoved = false, nextId = 0;
  const timers = new Map(), events = new Map();
  const card = {dataset: {contestDeadline: valid ? new Date(remaining).toISOString() : 'invalid',
      serverTime: new Date(0).toISOString()}, contains: () => focused, remove: () => {removed = true;}};
  const title = {focus: () => {focusMoved = true;}};
  const document = {activeElement: {}, querySelector: selector => selector.includes('data-contest') ? (featured ? card : null) : title,
    addEventListener: (name, fn) => events.set(name, fn), removeEventListener: name => events.delete(name)};
  const window = {setTimeout: (fn, delay) => {timers.set(++nextId, {fn, delay}); return nextId;},
    clearTimeout: id => timers.delete(id), addEventListener: document.addEventListener,
    removeEventListener: document.removeEventListener};
  vm.runInNewContext(source, {document, window, Date: {parse: Date.parse, now: () => clock}});
  return {timers, events, title, advance: ms => {clock += ms;}, removed: () => removed,
    focusMoved: () => focusMoved};
}

const state = setup({focused: true});
assert.equal(state.removed(), false);
assert.equal([...state.timers.values()][0].delay, 1000); // Server time, not the device's wall clock.
state.advance(999);
state.events.get('visibilitychange')();
assert.equal(state.removed(), false);
assert.equal([...state.timers.values()][0].delay, 1);
state.advance(1);
[...state.timers.values()][0].fn();
assert.equal(state.removed(), true);
assert.equal(state.focusMoved(), true);
assert.equal(state.title.tabIndex, -1);
assert.equal(state.timers.size, 0);
assert.equal(state.events.size, 0);

const restored = setup();
restored.advance(2000);
restored.events.get('pageshow')();
assert.equal(restored.removed(), true);
assert.equal(setup({remaining: 0}).removed(), true);
assert.equal([...setup({remaining: 86400000 * 40}).timers.values()][0].delay, 86400000);
for (const options of [{featured: false}, {valid: false}]) {
  const idle = setup(options);
  assert.equal(idle.timers.size, 0);
  assert.equal(idle.removed(), false);
}
console.log('Arcade library deadline OK: exact boundary, server time, restored tabs, cleanup and timer bounds');
