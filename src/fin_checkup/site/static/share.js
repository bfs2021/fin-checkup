/* fin-checkup 링크 공유 — navigator.share 가 있으면 그것으로, 없으면 클립보드 복사, 그것도 안 되면
   주소 칸을 보여 주고 선택해 둔다. 공유 주소는 canonical(없으면 현재 주소)에서 쿼리·해시를 뗀 것 —
   추적 파라미터를 붙이지도, 남기지도 않는다. 아무것도 서버로 보내지 않는다. */
(function () {
  "use strict";

  // 쿼리·해시를 뗀다. utm_* 같은 추적 파라미터가 따라 퍼지지 않게.
  function cleanUrl(href) {
    var cut = String(href).search(/[?#]/);
    return cut < 0 ? String(href) : String(href).slice(0, cut);
  }

  function shareUrl(canonicalHref, locationHref) {
    return cleanUrl(canonicalHref || locationHref);
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { cleanUrl: cleanUrl, shareUrl: shareUrl };
    return;
  }

  function wire(box) {
    var button = box.querySelector(".fc-share-button");
    var status = box.querySelector(".fc-share-status");
    var field = box.querySelector(".fc-share-field");
    if (!button || !status || !field) return;
    var canonical = document.querySelector('link[rel="canonical"]');
    var url = shareUrl(canonical && canonical.href, window.location.href);
    var title = document.title;
    var native = typeof navigator.share === "function";
    button.textContent = native ? "공유하기" : "링크 복사";
    button.hidden = false;

    function say(text) { status.textContent = text; }

    function showField() {
      field.value = url;
      field.hidden = false;
      field.focus();
      field.select();
      say("주소를 선택해 두었습니다. 복사해서 쓰세요.");
    }

    function copy() {
      if (!navigator.clipboard || !window.isSecureContext) return showField();
      navigator.clipboard.writeText(url).then(
        function () { say("링크를 복사했습니다."); },
        showField
      );
    }

    button.addEventListener("click", function () {
      say("");
      if (!native) return copy();
      navigator.share({ title: title, url: url }).catch(function (err) {
        // 사용자가 공유 창을 닫은 것(AbortError)은 실패가 아니다.
        if (!err || err.name !== "AbortError") copy();
      });
    });
  }

  var boxes = document.querySelectorAll(".fc-share");
  for (var i = 0; i < boxes.length; i++) wire(boxes[i]);
})();
