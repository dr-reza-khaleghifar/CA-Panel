/* Test the real responsive navigation controller with a minimal DOM.
 * No third-party browser packages, network, or CA secrets required.
 */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '..', 'app', 'static', 'navigation.js'), 'utf8');
const fakeClassList = () => {
  const found = new Set();
  return {
    add: (...values) => values.forEach(v => found.add(v)),
    remove: (...values) => values.forEach(v => found.delete(v)),
    contains: value => found.has(value),
    toggle: (value, force) => {
      if (force === undefined) force = !found.has(value);
      if (force) found.add(value);
      else found.delete(value);
      return force;
    },
  };
};
function element(id) {
  const attrs = {}, listeners = {};
  return {
    id, hidden:false, attrs, listeners, classList:fakeClassList(),
    focusCount:0, scrollCount:0, top:10000,
    getAttribute: key => attrs[key] || null,
    setAttribute(key, value) { attrs[key] = String(value); },
    removeAttribute(key) { delete attrs[key]; },
    addEventListener(type, fn) { (listeners[type] ||= []).push(fn); },
    focus() { this.focusCount++; document.activeElement = this; },
    scrollIntoView(opts) { this.scrollCount++; this.scrollOpts = opts; },
    getBoundingClientRect() { return {top:this.top}; },
    send(type, event = {preventDefault(){}}) {
      for (const fn of listeners[type] || []) fn(event);
    },
  };
}
const ids = ['sidebar','menu-toggle','menu-close','nav-backdrop',
             'overview','issue-workspace','how-it-works','faq','security','top','breadcrumb-current'];
const nodes = Object.fromEntries(ids.map(id => [id,element(id)]));
const targets = ['overview','issue-workspace','how-it-works','faq','security'];
const links = targets.map(id => {
  const link = element('link-' + id);
  link.setAttribute('href', '#' + id);
  link.querySelector = selector => selector === 'span:not(.nav-end)' ? {textContent:id} : null;
  return link;
});
nodes.overview.top = 90;
nodes['issue-workspace'].top = 600;
nodes['how-it-works'].top = 900;
nodes.faq.top = 1300;
nodes.security.top = 1800;
const brand = element('brand');
nodes.sidebar.querySelectorAll = () => [brand, nodes['menu-close'], ...links];
nodes.sidebar.contains = target => [brand, nodes['menu-close'], ...links].includes(target);
const body = element('body');
const documentListeners = {};
const document = {
  body,
  activeElement: null,
  getElementById: id => nodes[id],
  querySelectorAll: selector => selector === '.side-nav a[href^="#"]' ? links : [],
  querySelector: selector => selector === '.brand[href="#top"]' ? brand : null,
  addEventListener(type, fn) { (documentListeners[type] ||= []).push(fn); }
};
let isMobile = true;
const windowListeners = {};
const window = {
  innerHeight:800,
  history:{ pushState(_a,_b,hash){this.hash=hash;} },
  matchMedia(query){return {matches:query.includes('980px') ? isMobile : false};},
  requestAnimationFrame(fn){fn();},
  addEventListener(type, fn){(windowListeners[type] ||= []).push(fn);}
};
vm.runInNewContext(source, {document,window}, {filename:'navigation.js'});
assert.equal(nodes.sidebar.attrs['aria-hidden'], 'true');
nodes['menu-toggle'].send('click');
assert.equal(body.classList.contains('nav-open'), true);
assert.equal(nodes['menu-toggle'].attrs['aria-expanded'], 'true');
assert.equal(nodes['nav-backdrop'].hidden, false);
assert.equal(nodes['menu-close'].focusCount, 1);
// Keyboard users cannot Tab behind an open mobile navigation panel.
let tabPrevented = false;
brand.focus();
documentListeners.keydown[0]({key:'Tab',shiftKey:true,preventDefault(){tabPrevented=true;}});
assert.equal(tabPrevented, true);
assert.equal(document.activeElement, links[4]);
tabPrevented = false;
documentListeners.keydown[0]({key:'Tab',shiftKey:false,preventDefault(){tabPrevented=true;}});
assert.equal(tabPrevented, true);
assert.equal(document.activeElement, brand);
links[3].send('click');
assert.equal(nodes.faq.focusCount, 1);
assert.equal(nodes.faq.scrollCount, 1);
assert.equal(window.history.hash, '#faq');
assert.equal(links[3].attrs['aria-current'], 'location');
assert.equal(body.classList.contains('nav-open'), false);
nodes['menu-toggle'].send('click');
documentListeners.keydown[0]({key:'Escape'});
assert.equal(body.classList.contains('nav-open'), false);
assert.equal(nodes['menu-toggle'].focusCount > 0, true);
nodes.faq.top = 100;
nodes.security.top = 900;
windowListeners.scroll[0]();
assert.equal(links[3].attrs['aria-current'], 'location');
nodes['menu-toggle'].send('click');
nodes['nav-backdrop'].send('click');
assert.equal(body.classList.contains('nav-open'), false);
isMobile = false;
windowListeners.resize[0]();
assert.equal(nodes.sidebar.attrs['aria-hidden'], 'false');
console.log('Navigation interactions passed');
