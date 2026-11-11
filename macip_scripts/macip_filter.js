"use strict";

(function () {
  const filterEscape = "\u001F";
  const filterEscapable = "!<=>\\";
  const filterEncodeRe = new RegExp("\\\\([" + filterEscapable + "\\])", "g");
  const filterDecodeRe = new RegExp(filterEscape + "(\\d)", "g");
  const filterNumberRe = /^-?\d+([.,:]\d+)?([eE]-?\d+)?$/;
  const filterDoubleRe = /^[-+]?\d+([.,:]\d+)?([eE]-?\d+)?$/;
  const filterIntRe = /^[-+]?\d+$/;
  const filterOperators = {
    "!==": {func: (a, b) => a !== b, params: 2},
    "!\\N": {func: a => !filterIntRe.test("" + a), params: 1},
    "!\\D": {func: a => !filterDoubleRe.test("" + a), params: 1},
    "\\N": {func: a => filterIntRe.test("" + a), params: 1},
    "\\D": {func: a => filterDoubleRe.test("" + a), params: 1},
    "!=": {func: (a, b) => a !== b, params: 2},
    "<=": {func: (a, b) => a <= b, params: 2},
    "==": {func: (a, b) => a === b, params: 2},
    "!!": {func: (a, b) => a == b, params: 2},
    ">=": {func: (a, b) => a >= b, params: 2},
    "<": {func: (a, b) => a < b, params: 2},
    "=": {func: (a, b) => a === b, params: 2},
    ">": {func: (a, b) => a > b, params: 2},
    "!": {func: (a, b) => a !== b, params: 2}
  };
  const filterOperatorKeys = Object.keys(filterOperators);

  function filterCompareValue(value) {
    if (filterNumberRe.test(value)) {
      const number = parseFloat(value.replace(",", ".").replace(":", "."));
      if (!Number.isNaN(number)) return [number, false];
    }
    return [value.toLowerCase(), true];
  }

  function ipv4Value(value) {
    const parts = value.split(".");
    if (parts.length !== 4 || !parts.every(part =>
      /^(0|[1-9]\d{0,2})$/.test(part) && Number(part) <= 255
    )) return null;
    return parts.reduce((number, part) => number * 256 + Number(part), 0);
  }

  class ComparatorFilter {
    constructor(filter, compareIpv4 = false) {
      filter = filter.replace(filterEncodeRe, (_, character) =>
        filterEscape + String(filterEscapable.indexOf(character)));
      this.compareIpv4 = compareIpv4;
      this.negate = filter.endsWith("!");
      if (this.negate) filter = filter.slice(0, -1);
      this.items = [];
      if (filter === "") {
        this.items.push({func: filterOperators["="].func, value: "", strValue: "", isStr: true});
        return;
      }

      let index = 0;
      while (index < filter.length) {
        let func = null;
        let operator = "";
        let params = 2;
        for (const candidate of filterOperatorKeys) {
          if (filter.startsWith(candidate, index)) {
            operator = candidate;
            ({func, params} = filterOperators[candidate]);
            index += candidate.length;
            break;
          }
        }
        let next = params < 2 ? index : filter.length;
        if (params >= 2) {
          for (const candidate of filterOperatorKeys) {
            const found = filter.indexOf(candidate, index);
            if (found !== -1 && found < next) next = found;
          }
        }
        const value = filter.slice(index, next).replace(filterDecodeRe,
          (_, code) => filterEscapable[Number(code)] ?? "");
        const [compared, isStr] = filterCompareValue(value);
        if (value === "" && !func) func = filterOperators["="].func;
        if (!func || operator === "!" || operator === "!!") {
          let pattern = value;
          if (value.endsWith("\\") && !value.endsWith("\\\\")) pattern += "\\";
          const regex = new RegExp(pattern, "i");
          func = operator === "!" ? a => !regex.test("" + a) : a => regex.test("" + a);
        }
        const ipv4 = compareIpv4 && ["<", "<=", ">", ">="].includes(operator)
          ? ipv4Value(value) : null;
        this.items.push({func, value: compared, strValue: value.toLowerCase(), isStr, ipv4});
        index = next;
      }
    }

    test(value) {
      const [number, forceString] = filterCompareValue(value);
      const lowercase = value.toLowerCase();
      const ipv4 = this.compareIpv4 ? ipv4Value(value) : null;
      let result = true;
      for (const item of this.items) {
        if (value === "" && !item.isStr) {
          result = false;
          break;
        }
        let compared = item.value;
        let current = number;
        if (ipv4 !== null && item.ipv4 != null) {
          current = ipv4;
          compared = item.ipv4;
        } else if (forceString) compared = item.strValue;
        else if (item.isStr) current = lowercase;
        if (!item.func(current, compared)) {
          result = false;
          break;
        }
      }
      return this.negate ? !result : result;
    }
  }

  globalThis.MacipFilter = {ComparatorFilter, ipv4Value};
})();
