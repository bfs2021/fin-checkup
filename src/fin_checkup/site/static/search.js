/* fin-checkup 검색 — 회사 이름 · 6자리 종목코드 · 초성(ㅅㅅㅈㅈ).
   인덱스(search-index.json)는 처음 입력할 때 한 번 받는다. 링크는 <html data-root> 기준 상대경로라
   GitHub Pages 하위 경로(/fin-checkup/)에서도 그대로 동작한다. 외부 요청·저장·추적 없음.
   결과 순서는 "얼마나 맞았나 → 이름순" 뿐이다. 지표로 줄 세우지 않는다. */
(function () {
  "use strict";

  // site/hangul.py normalize_name 과 같은 규칙.
  function norm(s) {
    return String(s).replace(/\s+|\(주\)|㈜|주식회사/g, "").toLowerCase();
  }

  function rank(item, q) {
    var name = item._n || (item._n = norm(item.name));
    var code = item.code.toLowerCase();
    var cho = item.chosung || "";
    if (name === q || code === q) return 0;
    if (name.indexOf(q) === 0 || code.indexOf(q) === 0) return 1;
    if (name.indexOf(q) > 0) return 2;
    if (cho.indexOf(q) === 0) return 3;
    if (cho.indexOf(q) > 0) return 4;
    return -1;
  }

  function search(items, raw, limit) {
    var q = norm(raw || "");
    if (!q) return [];
    var hits = [];
    for (var i = 0; i < items.length; i++) {
      var r = rank(items[i], q);
      if (r >= 0) hits.push([r, items[i]]);
    }
    hits.sort(function (a, b) {
      if (a[0] !== b[0]) return a[0] - b[0];
      return a[1].name < b[1].name ? -1 : a[1].name > b[1].name ? 1 : 0;
    });
    return hits.slice(0, limit || 10).map(function (h) { return h[1]; });
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { search: search, norm: norm };
    return;
  }

  var root = document.documentElement.getAttribute("data-root") || "./";
  var loading = null;

  function load() {
    if (!loading) {
      loading = fetch(root + "search-index.json")
        .then(function (r) { return r.json(); })
        .then(function (data) { return data.companies; })
        .catch(function () { loading = null; return []; });
    }
    return loading;
  }

  function hrefOf(item) { return root + "c/" + item.code + "/"; }

  function wire(form) {
    var input = form.querySelector("input[type=search]");
    var list = form.querySelector(".fc-results");
    if (!input || !list) return;
    var shown = [];
    var active = -1;

    function paint() {
      list.textContent = "";
      shown.forEach(function (item, i) {
        var li = document.createElement("li");
        li.id = list.id + "-" + i;
        li.setAttribute("role", "option");
        li.setAttribute("aria-selected", i === active ? "true" : "false");
        var a = document.createElement("a");
        a.href = hrefOf(item);
        a.tabIndex = -1;
        var name = document.createElement("span");
        name.textContent = item.name;
        var meta = document.createElement("small");
        meta.textContent = item.code + (item.market ? " · " + item.market : "");
        a.appendChild(name);
        a.appendChild(meta);
        li.appendChild(a);
        list.appendChild(li);
      });
      var open = shown.length > 0;
      list.hidden = !open;
      input.setAttribute("aria-expanded", open ? "true" : "false");
      if (active >= 0) input.setAttribute("aria-activedescendant", list.id + "-" + active);
      else input.removeAttribute("aria-activedescendant");
    }

    function update() {
      var q = input.value;
      load().then(function (items) {
        if (input.value !== q) return;
        shown = search(items, q, 10);
        active = shown.length ? 0 : -1;
        paint();
      });
    }

    input.addEventListener("input", update);
    input.addEventListener("focus", load);
    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        if (!shown.length) return;
        e.preventDefault();
        var step = e.key === "ArrowDown" ? 1 : -1;
        active = (active + step + shown.length) % shown.length;
        paint();
      } else if (e.key === "Escape") {
        shown = [];
        active = -1;
        paint();
      }
    });
    // Enter: 고른 결과로, 아직 목록이 없으면(인덱스를 받는 중) 가장 잘 맞는 회사로.
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var q = input.value;
      load().then(function (items) {
        var hits = search(items, q, 10);
        var pick = hits[Math.max(active, 0)] || hits[0];
        if (pick) window.location.href = hrefOf(pick);
      });
    });

    var initial = new URLSearchParams(window.location.search).get("q");
    if (initial && !input.value) {
      input.value = initial;
      update();
    }
  }

  var forms = document.querySelectorAll("form.fc-search");
  for (var i = 0; i < forms.length; i++) wire(forms[i]);
})();
