/**
 * cacheInvalidator.js
 * -------------------
 * بيراقب كل response جاي من الـ API.
 * لو لاقى header: X-Cache-Invalidate → بيحفظ الـ scope
 * اللي محتاج يتكلير.
 *
 * أي GET request جاي لنفس الـ scope هيتبعت مع X-No-Cache: 1
 * → Nginx بيعمل bypass للكاش ويجيب fresh data فوراً.
 *
 * الاستخدام:
 *   import { apiClient } from './cacheInvalidator.js';
 *
 *   // بدل fetch() العادي، استخدم:
 *   const res = await apiClient('/client-api/categories', { method: 'POST', ... });
 *   const res = await apiClient('/client-api/categories');
 */

// Scopes اللي محتاجين purge دلوقتي
const pendingPurges = new Set();

/**
 * Map: كل scope → الـ URL prefixes المرتبطة بيه
 * لما scope يكون pending، أي GET على الـ prefixes دي بيتبعت بـ X-No-Cache: 1
 */
const SCOPE_PREFIXES = {
  categories: ['/client-api/categories'],
  documents:  ['/client-api/documents', '/client-api/categories'],
  chat:       ['/client-api/chat'],
};

/**
 * شايف URL ده محتاج purge ولا لأ؟
 */
function needsPurge(url) {
  for (const scope of pendingPurges) {
    const prefixes = SCOPE_PREFIXES[scope] || [];
    if (prefixes.some(prefix => url.includes(prefix))) {
      return true;
    }
  }
  return false;
}

/**
 * بعد ما عملنا purge request نافعة، نشيل الـ scope من القائمة
 */
function clearPurgeScope(url) {
  for (const scope of pendingPurges) {
    const prefixes = SCOPE_PREFIXES[scope] || [];
    if (prefixes.some(prefix => url.includes(prefix))) {
      pendingPurges.delete(scope);
    }
  }
}

/**
 * الـ wrapper الرئيسي — استخدمه بدل fetch() في كل مكان
 *
 * @param {string} url
 * @param {RequestInit} options
 * @returns {Promise<Response>}
 */
export async function apiClient(url, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const headers = new Headers(options.headers || {});

  // لو GET وفيه pending purge لنفس الـ scope → ابعت X-No-Cache: 1
  if (method === 'GET' && needsPurge(url)) {
    headers.set('X-No-Cache', '1');
  }

  const response = await fetch(url, { ...options, headers });

  // بعد أي mutation، اقرأ X-Cache-Invalidate وحفظ الـ scopes
  if (method !== 'GET') {
    const invalidateHeader = response.headers.get('X-Cache-Invalidate');
    if (invalidateHeader) {
      invalidateHeader.split(',').forEach(scope => {
        pendingPurges.add(scope.trim());
      });
    }
  } else {
    // لو بعتنا X-No-Cache: 1 وجاء الـ response → الكاش اتكلير، شيل الـ scope
    if (headers.get('X-No-Cache') === '1') {
      clearPurgeScope(url);
    }
  }

  return response;
}

/**
 * لو محتاج تعمل invalidation يدوي من أي حتة في الكود
 * مثلاً بعد SSE stream خلص
 *
 * @param {...string} scopes  e.g. invalidate('chat'), invalidate('documents', 'categories')
 */
export function invalidate(...scopes) {
  scopes.forEach(s => pendingPurges.add(s));
}

/**
 * للـ debugging — شوف الـ pending scopes
 */
export function getPendingPurges() {
  return [...pendingPurges];
}
