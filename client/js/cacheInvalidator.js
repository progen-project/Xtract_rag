/**
 * cacheInvalidator.js — Vanilla JS, no modules, no bundler
 * =========================================================
 * بيعمل patch على window.fetch نفسه عشان كل الكود الموجود
 * يشتغل تلقائي من غير ما تعدل سطر واحد في api.js أو app.js.
 *
 * الاستخدام:
 *   ضيف السكريبت ده قبل api.js في الـ HTML وخلاص:
 *   <script src="js/cacheInvalidator.js"></script>
 *   <script src="js/api.js"></script>
 */

(function (window) {
  'use strict';

  // Scopes اللي محتاجة cache bypass
  var pendingPurges = {};

  // كل scope → الـ URL prefixes المرتبطة بيه
  var SCOPE_PREFIXES = {
    categories: ['/client-api/categories'],
    documents:  ['/client-api/documents', '/client-api/categories'],
    chat:       ['/client-api/chat'],
  };

  function needsPurge(url) {
    for (var scope in pendingPurges) {
      if (!pendingPurges[scope]) continue;
      var prefixes = SCOPE_PREFIXES[scope] || [];
      for (var i = 0; i < prefixes.length; i++) {
        if (url.indexOf(prefixes[i]) !== -1) return true;
      }
    }
    return false;
  }

  function clearScopeForUrl(url) {
    for (var scope in pendingPurges) {
      if (!pendingPurges[scope]) continue;
      var prefixes = SCOPE_PREFIXES[scope] || [];
      for (var i = 0; i < prefixes.length; i++) {
        if (url.indexOf(prefixes[i]) !== -1) {
          pendingPurges[scope] = false;
          break;
        }
      }
    }
  }

  // ── Patch window.fetch ────────────────────────────────────────────────────
  var originalFetch = window.fetch.bind(window);

  window.fetch = function (resource, options) {
    options = options || {};
    var url    = (typeof resource === 'string') ? resource : resource.url;
    var method = (options.method || 'GET').toUpperCase();

    // Clone headers so we don't mutate the caller's object
    var headers = new Headers(options.headers || {});

    // لو GET وفيه pending purge → ابعت X-No-Cache: 1
    if (method === 'GET' && needsPurge(url)) {
      headers.set('X-No-Cache', '1');
    }

    var patchedOptions = Object.assign({}, options, { headers: headers });

    return originalFetch(resource, patchedOptions).then(function (response) {

      if (method !== 'GET') {
        // بعد أي mutation → اقرأ X-Cache-Invalidate وخزن الـ scopes
        var invalidateHeader = response.headers.get('X-Cache-Invalidate');
        if (invalidateHeader) {
          invalidateHeader.split(',').forEach(function (scope) {
            pendingPurges[scope.trim()] = true;
          });
        }
      } else {
        // لو بعتنا X-No-Cache: 1 → الكاش اتبايباس، امسح الـ scope
        if (headers.get('X-No-Cache') === '1') {
          clearScopeForUrl(url);
        }
      }

      return response;
    });
  };
  // ─────────────────────────────────────────────────────────────────────────

  // لو محتاج تعمل invalidation يدوي (مثلاً بعد chat stream يخلص)
  window.invalidate = function () {
    for (var i = 0; i < arguments.length; i++) {
      pendingPurges[arguments[i]] = true;
    }
  };

})(window);