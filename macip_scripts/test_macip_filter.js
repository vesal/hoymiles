"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function test(name, fn) {
  fn();
  console.log(`OK: ${name}`);
}

const source = fs.readFileSync(path.join(__dirname, "macip_filter.js"), "utf8");
const context = {};
vm.runInNewContext(source, context);
const {ComparatorFilter} = context.MacipFilter;

function matches(filter, value, compareIpv4 = false) {
  return new ComparatorFilter(filter, compareIpv4).test(value);
}

test("regular expressions and negation", () => {
  for (const [filter, value, expected] of [
    ["a|b", "CAT", true], ["a|b", "dog", false], ["!a", "cat", false],
    ["!a!b", "dog", true], ["a!b", "cab", false], ["!!a", "CAT", true],
    ["!a!", "CAT", true], ["\\!a", "!a", true], ["\\<2", "<2", true],
    ["\\d+", "abc123", true], ["a\\\\", "a\\", true]
  ]) {
    assert.equal(matches(filter, value), expected, `${filter} / ${value}`);
  }
  assert.throws(() => new ComparatorFilter("["));
});

test("empty, equality and string comparisons", () => {
  for (const [filter, value, expected] of [
    ["=", "", true], ["=", "a", false], ["!", "", false], ["!", "a", true],
    ["=a", "A", true], ["=a", "ab", false], ["!=a", "A", false],
    ["!=a", "ab", true], [">", "", false], [">", "a", true],
    ["<2", "", false], ["<2", "1a", true], [">2", "cat", true]
  ]) {
    assert.equal(matches(filter, value), expected, `${filter} / ${value}`);
  }
});

test("numeric comparisons, ranges and numeric type operators", () => {
  for (const [filter, value, expected] of [
    [">2<4", "3", true], [">2<4", "2", false], [">2<4", "4", false],
    [">=2<=4", "2", true], [">=2<=4", "4", true], [">2<4!", "3", false],
    [">2<4!", "2", true], ["=2", "2,0", true], [">2", "2:5", true],
    ["\\N>2", "3", true], ["\\N>2", "3.5", false], ["\\N>2", "cat", false],
    ["\\D", "-1.5", true], ["\\D", "3%", false], ["\\D!", "cat", true],
    ["\\N!", "3.5", true], ["!\\N", "cat", true], ["!\\D", "cat", true]
  ]) {
    assert.equal(matches(filter, value), expected, `${filter} / ${value}`);
  }
});

test("IPv4 ordering applies only when enabled and both addresses are valid", () => {
  for (const [filter, value, enabled, expected] of [
    ["<192.168.59.30", "192.168.59.9", true, true],
    ["<192.168.59.30", "192.168.59.9", false, false],
    [">192.168.59.30", "192.168.59.100", true, true],
    [">=192.168.59.30", "192.168.59.30", true, true],
    ["<=192.168.59.30", "192.168.59.30", true, true],
    ["<192.168.59.30", "192.168.59.30", true, false],
    [">=192.168.59.10<192.168.59.30", "192.168.59.9", true, false],
    [">=192.168.59.10<192.168.59.30", "192.168.59.10", true, true],
    [">=192.168.59.10<192.168.59.30", "192.168.59.30", true, false],
    ["<192.168.59.30!", "192.168.59.9", true, false],
    [">0.0.0.0", "0.0.0.1", true, true],
    ["<=255.255.255.255", "255.255.255.255", true, true],
    ["<192.168.59.30", "192.168.59.999", true, false],
    ["<192.168.59.999", "192.168.59.30", true, true],
    ["<192.168.59.30", "192.168.59.09", true, true],
    ["=192.168.59.30", "192.168.59.30", true, true],
    ["192\\.168\\.59\\.", "192.168.59.9", true, true],
    ["<2", "1", true, true],
    ["<192.168.59.30", "", true, true]
  ]) {
    assert.equal(matches(filter, value, enabled), expected, `${filter} / ${value} / ${enabled}`);
  }
});
