/* fin-checkup 이어 보기 — 첫 화면에서, 이 브라우저에 담아 둔 관심종목·나란히 보기로 바로 가는 링크 한 줄.
   저장소를 읽기만 한다(키는 watch.js·compare.js 와 같다). 담아 둔 것이 없으면 아무것도 보이지 않는다.
   숫자 배지·재촉 문구는 두지 않는다. */
(function () {
  "use strict";

  var box = document.getElementById("fc-resume");
  if (!box) return;

  function watched() {
    try {
      var state = JSON.parse(window.localStorage.getItem("fin-checkup:watch") || "null");
      return Boolean(state && Array.isArray(state.items) && state.items.length);
    } catch (e) {
      return false;
    }
  }

  function compared() {
    try {
      return /[0-9A-Z]{6}/.test(window.localStorage.getItem("fin-checkup:compare") || "");
    } catch (e) {
      return false;
    }
  }

  var shown = { watch: watched(), compare: compared() };
  var any = false;
  Object.keys(shown).forEach(function (key) {
    var link = box.querySelector('[data-resume="' + key + '"]');
    if (link && shown[key]) {
      link.hidden = false;
      any = true;
    }
  });
  box.hidden = !any;
})();
