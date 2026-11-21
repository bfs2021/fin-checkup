/* fin-checkup 관심종목 — 이 브라우저의 저장소에만 둔다. 서버·계정·쿠키·추적 없음.
   저장소 접근은 키를 글자 그대로 쓴다 — 사이트 가드(site/guard.py storage)가 그 꼴만 허용한다.

   저장 형식 (키 "fin-checkup:watch", JSON):
     { "v": 1,
       "items": [ { "code": "005930",          // 종목코드 6자리
                    "name": "삼성전자",
                    "year": 2024,               // 담을 때 보던 사업연도 (가져오기로 들어오면 null)
                    "saved": "2026-11-21",      // 그 기준을 잡은 날 (KST, 가져오기면 null)
                    "signals": { "debt_ratio": "yellow", ... },  // 지표 key → 신호 key, 없으면 null
                    "seen": ["20261121000123"]  // 기준일 당일에 이미 확인한 공시 접수번호 (없으면 [])
                  } ] }

   회사 페이지: .fc-watch-toggle 버튼 (data-watch = 지금 페이지의 위 항목 하나, JSON)
   /watch/:    #fc-watch-app — 담은 회사를 이름순으로, 각 회사의 api/c/<코드>.json 을 받아 지금 상태와
               "지난번 이후 바뀐 것"(기준값과 다른 신호·새 사업연도·data/disclosures.json 의 위험 공시)을 보여 준다.
               "확인함" 은 그 회사의 기준값을 지금 상태로 바꾼다.
   숫자 배지·연속 방문 기록·재촉 문구는 두지 않는다. */
(function () {
  "use strict";

  var KEY = "fin-checkup:watch";
  var VERSION = 1;
  var MAX_ITEMS = 200;
  var CODE = /^[0-9A-Z]{6}$/;
  // metrics/signals.py Signal 과 같아야 한다 (테스트가 확인).
  var SIGNALS = {
    green: { emoji: "🟢", label: "정상" },
    yellow: { emoji: "🟡", label: "주의" },
    red: { emoji: "🔴", label: "위험" },
    neutral: { emoji: "⚪", label: "측정값" },
    not_applicable: { emoji: "⊘", label: "해당 없음" },
    unknown: { emoji: "⚫", label: "데이터 없음" },
  };
  // presentation.summary_chips 와 같은 순서: 위험·주의·정상은 늘, 나머지는 있을 때만.
  var PRIMARY = ["red", "yellow", "green"];
  var SECONDARY = ["neutral", "not_applicable", "unknown"];

  // ── 순수 로직 (node 로 테스트한다) ─────────────────────────────

  function empty() { return { v: VERSION, items: [] }; }

  function cleanItem(raw) {
    if (!raw || typeof raw !== "object") return null;
    var code = String(raw.code || "").toUpperCase();
    if (!CODE.test(code)) return null;
    var signals = null;
    if (raw.signals && typeof raw.signals === "object") {
      signals = {};
      Object.keys(raw.signals).forEach(function (k) {
        if (typeof raw.signals[k] === "string") signals[k] = raw.signals[k];
      });
    }
    var seen = Array.isArray(raw.seen)
      ? raw.seen.filter(function (n) { return typeof n === "string"; }).slice(0, 200)
      : [];
    return {
      code: code,
      name: typeof raw.name === "string" ? raw.name : code,
      year: typeof raw.year === "number" ? raw.year : null,
      saved: typeof raw.saved === "string" ? raw.saved : null,
      signals: signals,
      seen: seen,
    };
  }

  // 망가진 값·다른 형식이 들어 있어도 죽지 않고 쓸 수 있는 항목만 건진다.
  function parse(text) {
    var data;
    try { data = JSON.parse(text); } catch (e) { return empty(); }
    if (!data || typeof data !== "object" || !Array.isArray(data.items)) return empty();
    var state = empty();
    data.items.forEach(function (raw) {
      var item = cleanItem(raw);
      if (item && !has(state, item.code) && state.items.length < MAX_ITEMS) state.items.push(item);
    });
    return state;
  }

  function serialize(state) { return JSON.stringify({ v: VERSION, items: state.items }); }

  function has(state, code) {
    for (var i = 0; i < state.items.length; i++) if (state.items[i].code === code) return true;
    return false;
  }

  function add(state, raw) {
    var item = cleanItem(raw);
    if (!item) return state;
    var items = state.items.filter(function (it) { return it.code !== item.code; });
    if (items.length >= MAX_ITEMS) return state;
    items.push(item);
    return { v: VERSION, items: items };
  }

  function remove(state, code) {
    return { v: VERSION, items: state.items.filter(function (it) { return it.code !== code; }) };
  }

  // 내보내기: 한 줄에 종목코드 하나. 이름은 참고로 붙인다(가져올 때 무시된다).
  function exportText(state) {
    return byName(state.items).map(function (it) { return it.code + " " + it.name; }).join("\n");
  }

  // 가져오기: 줄·쉼표·공백으로 나뉜 글에서 6자리 종목코드만 뽑는다. 순서 유지, 중복 제거.
  function parseCodes(text) {
    var seen = {};
    var codes = [];
    String(text || "").toUpperCase().split(/[\s,;]+/).forEach(function (tok) {
      if (CODE.test(tok) && /[0-9]/.test(tok) && !seen[tok]) {
        seen[tok] = true;
        codes.push(tok);
      }
    });
    return codes;
  }

  function importCodes(state, codes) {
    var next = state;
    codes.forEach(function (code) {
      if (!has(next, code)) next = add(next, { code: code, name: code });
    });
    return next;
  }

  // 목록 순서는 이름순뿐이다. 신호로 줄 세우지 않는다.
  function byName(items) {
    return items.slice().sort(function (a, b) {
      return a.name < b.name ? -1 : a.name > b.name ? 1 : a.code < b.code ? -1 : a.code > b.code ? 1 : 0;
    });
  }

  // 회사 JSON(api/c/<코드>.json)에서 기준으로 저장할 것.
  function snapshotOf(company, today) {
    var signals = {};
    company.metrics.forEach(function (m) { signals[m.key] = m.signal.key; });
    return {
      code: company.company.stock_code,
      name: company.company.name,
      year: company.fiscal_year,
      saved: today,
      signals: signals,
      seen: [],
    };
  }

  var DART = /^https:\/\/dart\.fss\.or\.kr\//;

  function compact(day) { return String(day || "").replace(/-/g, ""); }

  function dashed(yyyymmdd) {
    var d = String(yyyymmdd);
    return d.slice(0, 4) + "-" + d.slice(4, 6) + "-" + d.slice(6, 8);
  }

  // 기준일(당일 포함) 이후 접수된 그 회사의 위험 공시, 최신순. 당일 이미 확인한 접수번호는 뺀다.
  function disclosuresSince(item, disclosures) {
    if (!disclosures || !Array.isArray(disclosures.items) || !item.saved) return [];
    var since = compact(item.saved);
    var seen = item.seen || [];
    return disclosures.items
      .filter(function (d) {
        return d && d.stock_code === item.code && String(d.rcept_dt) >= since && seen.indexOf(d.rcept_no) < 0;
      })
      .sort(function (a, b) {
        var ka = a.rcept_dt + a.rcept_no, kb = b.rcept_dt + b.rcept_no;
        return ka < kb ? 1 : ka > kb ? -1 : 0;
      });
  }

  // 지난번 기준값과 지금 사이에 바뀐 사실들. 해석·권유 없이 무엇이 무엇으로 바뀌었는지만.
  function changesSince(item, company, disclosures) {
    var out = [];
    if (!item.signals) return out;
    if (item.year != null && company.fiscal_year !== item.year) {
      out.push({ kind: "year", from: item.year, to: company.fiscal_year });
    }
    company.metrics.forEach(function (m) {
      var before = item.signals[m.key];
      if (before && before !== m.signal.key) {
        out.push({ kind: "signal", key: m.key, label: m.label, from: before, to: m.signal.key });
      }
    });
    disclosuresSince(item, disclosures).forEach(function (d) {
      out.push({
        kind: "disclosure",
        date: dashed(d.rcept_dt),
        rcept_no: d.rcept_no,
        title: d.report_nm,
        category: d.category_label,
        url: DART.test(d.url || "") ? d.url : null,
      });
    });
    return out;
  }

  // "확인함": 지금 상태를 새 기준으로. 오늘 접수돼 이미 본 공시는 seen 에 남겨 다시 뜨지 않게 한다.
  function acknowledge(item, company, disclosures, today) {
    var snap = snapshotOf(company, today);
    var todayKey = compact(today);
    snap.seen = disclosuresSince(item, disclosures)
      .filter(function (d) { return String(d.rcept_dt) === todayKey; })
      .map(function (d) { return d.rcept_no; });
    return snap;
  }

  function chipCounts(company) {
    var counts = {};
    company.metrics.forEach(function (m) { counts[m.signal.key] = (counts[m.signal.key] || 0) + 1; });
    return PRIMARY.map(function (k) { return [k, counts[k] || 0]; }).concat(
      SECONDARY.filter(function (k) { return counts[k]; }).map(function (k) { return [k, counts[k]]; })
    );
  }

  // KST 날짜 (YYYY-MM-DD). toISOString 은 UTC 라 한국 00~09시에 어제가 된다.
  function kstToday(now) {
    var d = new Date((now || new Date()).getTime() + 9 * 3600 * 1000);
    return d.toISOString().slice(0, 10);
  }

  var core = {
    KEY: KEY, parse: parse, serialize: serialize, has: has, add: add, remove: remove,
    exportText: exportText, parseCodes: parseCodes, importCodes: importCodes, byName: byName,
    snapshotOf: snapshotOf, kstToday: kstToday, chipCounts: chipCounts, SIGNALS: SIGNALS,
    changesSince: changesSince, acknowledge: acknowledge,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = core;
    return;
  }

  // ── 브라우저 ───────────────────────────────────────────────

  var root = document.documentElement.getAttribute("data-root") || "./";

  // 사생활 보호 모드 등에선 저장소 접근 자체가 예외를 던진다.
  function storage() {
    try {
      window.localStorage.getItem("fin-checkup:watch");
      return true;
    } catch (e) { return false; }
  }

  function load() {
    try { return parse(window.localStorage.getItem("fin-checkup:watch") || ""); } catch (e) { return empty(); }
  }

  function save(state) {
    try {
      window.localStorage.setItem("fin-checkup:watch", serialize(state));
      return true;
    } catch (e) { return false; }
  }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  // 회사 페이지 토글.
  function wireToggle(button) {
    var status = document.querySelector(".fc-watch-status");
    var entry;
    try { entry = JSON.parse(button.getAttribute("data-watch")); } catch (e) { return; }
    if (!storage()) return;  // 저장할 수 없으면 버튼을 보이지 않는다
    function paint() {
      var on = has(load(), entry.code);
      button.setAttribute("aria-pressed", on ? "true" : "false");
      button.textContent = on ? "관심종목에 담김" : "관심종목에 담기";
    }
    button.addEventListener("click", function () {
      var state = load();
      var on = has(state, entry.code);
      var next = on ? remove(state, entry.code) : add(state, Object.assign({}, entry, { saved: kstToday() }));
      if (!save(next)) {
        if (status) status.textContent = "이 브라우저에는 저장할 수 없습니다.";
        return;
      }
      paint();
      if (status) {
        status.textContent = on
          ? "관심종목에서 뺐습니다."
          : "관심종목에 담았습니다. 이 브라우저에만 저장됩니다.";
      }
    });
    paint();
    button.hidden = false;
    var link = document.querySelector(".fc-watch-link");
    if (link) link.hidden = false;
  }

  function fetchCompany(code) {
    return fetch(root + "api/c/" + code + ".json").then(function (r) {
      if (!r.ok) throw new Error(String(r.status));
      return r.json();
    });
  }

  // 공시 목록은 사이트 빌드가 함께 싣는 정적 파일이다. 없으면(시크릿 없는 빌드) 공시 비교를 건너뛴다.
  var disclosuresLoad = null;
  function fetchDisclosures() {
    if (!disclosuresLoad) {
      disclosuresLoad = fetch(root + "data/disclosures.json")
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) { return d && d.format_version === 1 ? d : null; })
        .catch(function () { return null; });
    }
    return disclosuresLoad;
  }

  // 신호 모양은 CSS(.fc-mark) — 이모지 글꼴에 기대지 않는다 (_signal.html 과 같은 모양).
  function signalMark(key) {
    var mark = el("span", "fc-mark mark-" + key);
    mark.setAttribute("aria-hidden", "true");
    return mark;
  }

  function signalBadge(key) {
    var s = SIGNALS[key] || { emoji: "", label: key };
    var badge = el("span", "fc-sig sig-" + key);
    badge.appendChild(signalMark(key));
    badge.appendChild(document.createTextNode(s.label));
    return badge;
  }

  function changeLine(change, code) {
    var li = el("li", "fc-watch-change");
    if (change.kind === "year") {
      li.appendChild(document.createTextNode(
        "새 사업연도 숫자: " + change.from + " → " + change.to + " 사업연도 "
      ));
      var page = el("a", null, "회사 페이지");
      page.href = root + "c/" + code + "/";
      li.appendChild(page);
    } else if (change.kind === "signal") {
      var a = el("a", null, change.label);
      a.href = root + "c/" + code + "/#m-" + change.key;
      li.appendChild(a);
      li.appendChild(document.createTextNode(": "));
      li.appendChild(signalBadge(change.from));
      li.appendChild(document.createTextNode(" → "));
      li.appendChild(signalBadge(change.to));
    } else {
      li.appendChild(document.createTextNode(
        "위험 공시 " + change.date + " · " + change.category + " — " + change.title + " "
      ));
      if (change.url) {
        var src = el("a", null, "DART 원문");
        src.href = change.url;
        src.rel = "noopener noreferrer";
        li.appendChild(src);
      }
    }
    return li;
  }

  function changesBox(item, company, disclosures, li, app) {
    var box = el("div", "fc-watch-changes");
    if (!item.saved) return box;
    var changes = changesSince(item, company, disclosures);
    box.appendChild(el("p", "fc-watch-since", "지난번 확인(" + item.saved + ") 이후"));
    if (!changes.length) {
      box.appendChild(el("p", "fc-hint", "바뀐 것은 없습니다."));
    } else {
      var list = el("ul", "fc-watch-change-list");
      changes.forEach(function (c) { list.appendChild(changeLine(c, item.code)); });
      box.appendChild(list);
      var ack = el("button", "fc-button fc-watch-ack", "확인함");
      ack.type = "button";
      ack.setAttribute("aria-label", company.company.name + " 바뀐 것 확인함 — 지금 상태를 새 기준으로 저장");
      ack.addEventListener("click", function () {
        var next = acknowledge(item, company, disclosures, kstToday());
        save(add(load(), next));
        var fresh = renderItem(next, company, app, disclosures);
        li.replaceWith(fresh);
        var focus = fresh.querySelector(".fc-watch-since");
        if (focus) { focus.tabIndex = -1; focus.focus(); }
      });
      box.appendChild(ack);
    }
    if (disclosures && compact(item.saved) < String(disclosures.bgn_de)) {
      box.appendChild(el("p", "fc-hint",
        "위험 공시는 " + dashed(disclosures.bgn_de) + "~" + dashed(disclosures.end_de) +
        " 접수분만 비교합니다. 그 전 공시는 DART 에서 확인하세요."));
    } else if (!disclosures) {
      box.appendChild(el("p", "fc-hint", "이번 빌드에는 위험 공시 목록이 없어 공시는 비교하지 않았습니다."));
    }
    return box;
  }

  function chipsOf(company) {
    var list = el("ul", "fc-chips");
    list.setAttribute("aria-label", "신호 개수");
    chipCounts(company).forEach(function (pair) {
      var sig = SIGNALS[pair[0]];
      var li = el("li", "fc-chip sig-" + pair[0]);
      li.appendChild(signalMark(pair[0]));
      li.appendChild(document.createTextNode(sig.label + " "));
      li.appendChild(el("b", null, String(pair[1])));
      list.appendChild(li);
    });
    return list;
  }

  function renderItem(item, company, app, disclosures) {
    var li = el("li", "fc-watch-item");
    li.setAttribute("data-code", item.code);
    var head = el("div", "fc-watch-head");
    var a = el("a", "fc-watch-name", company ? company.company.name : item.name);
    a.href = root + "c/" + item.code + "/";
    head.appendChild(a);
    head.appendChild(el("span", "fc-code", item.code));
    var feed = el("a", "fc-feed-link", "피드");
    feed.href = root + "feeds/c/" + item.code + ".xml";
    feed.setAttribute("aria-label", (company ? company.company.name : item.name) + " Atom 피드");
    head.appendChild(feed);
    var drop = el("button", "fc-button fc-watch-remove", "빼기");
    drop.type = "button";
    drop.setAttribute("aria-label", (company ? company.company.name : item.name) + " 관심종목에서 빼기");
    drop.addEventListener("click", function () {
      save(remove(load(), item.code));
      li.remove();
      refreshExport(app);
      if (!load().items.length) app.querySelector(".fc-watch-empty").hidden = false;
    });
    head.appendChild(drop);
    li.appendChild(head);
    if (!company) {
      li.appendChild(el("p", "fc-hint", "이번 빌드에는 이 회사 페이지가 없습니다 (상장 폐지·재무 미수집 등)."));
      return li;
    }
    li.appendChild(el("p", "fc-basis", company.fiscal_year + "년 " + company.report.label + " 기준"));
    li.appendChild(chipsOf(company));
    li.appendChild(changesBox(item, company, disclosures, li, app));
    return li;
  }

  function refreshExport(app) {
    var out = app.querySelector(".fc-watch-export");
    if (out) out.value = exportText(load());
  }

  function renderList(app) {
    var list = app.querySelector(".fc-watch-list");
    var emptyNote = app.querySelector(".fc-watch-empty");
    var state = load();
    list.textContent = "";
    refreshExport(app);
    emptyNote.hidden = state.items.length > 0;
    var companiesLoad = Promise.all(state.items.map(function (item) {
      return fetchCompany(item.code).then(
        function (company) { return [item, company]; },
        function () { return [item, null]; }
      );
    }));
    var disclosures = null;
    return Promise.all([companiesLoad, state.items.length ? fetchDisclosures() : null]).then(function (got) {
      var rows = got[0];
      disclosures = got[1];
      var today = kstToday();
      var current = load();
      var companies = {};
      var shown = rows.map(function (row) {
        var item = row[0], company = row[1];
        companies[item.code] = company;
        // 가져오기로 들어와 기준이 없는 항목은 처음 본 지금 상태를 기준으로 삼는다.
        if (company && !item.signals) {
          item = snapshotOf(company, today);
          current = add(current, item);
        } else if (company && item.name !== company.company.name) {
          item = Object.assign({}, item, { name: company.company.name });
          current = add(current, item);
        }
        return item;
      });
      save(current);
      // 이름이 확정된 뒤에 이름순으로.
      byName(shown).forEach(function (item) {
        list.appendChild(renderItem(item, companies[item.code], app, disclosures));
      });
      refreshExport(app);
    });
  }

  function wireApp(app) {
    var noStore = app.querySelector(".fc-watch-nostore");
    if (!storage()) { if (noStore) noStore.hidden = false; return; }
    app.hidden = false;
    var status = app.querySelector(".fc-watch-io-status");
    var importBox = app.querySelector(".fc-watch-import");
    app.querySelector(".fc-watch-import-button").addEventListener("click", function () {
      var codes = parseCodes(importBox.value);
      if (!codes.length) { status.textContent = "6자리 종목코드를 찾지 못했습니다."; return; }
      var before = load().items.length;
      save(importCodes(load(), codes));
      var added = load().items.length - before;
      status.textContent = "종목코드 " + codes.length + "개 중 " + added + "개를 새로 담았습니다.";
      importBox.value = "";
      renderList(app);
    });
    app.querySelector(".fc-watch-clear").addEventListener("click", function () {
      if (!load().items.length) return;
      if (!window.confirm("이 브라우저에 저장된 관심종목을 모두 지울까요? 되돌릴 수 없습니다.")) return;
      save(empty());
      status.textContent = "모두 지웠습니다.";
      renderList(app);
    });
    renderList(app);
  }

  var toggles = document.querySelectorAll(".fc-watch-toggle");
  for (var i = 0; i < toggles.length; i++) wireToggle(toggles[i]);
  var app = document.getElementById("fc-watch-app");
  if (app) wireApp(app);
})();
