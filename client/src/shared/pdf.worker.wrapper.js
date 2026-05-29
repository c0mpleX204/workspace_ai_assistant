if (typeof Promise.withResolvers !== 'function') {
  Promise.withResolvers = function () {
    let resolve, reject
    const p = new Promise(function (res, rej) { resolve = res; reject = rej })
    return { promise: p, resolve: resolve, reject: reject }
  }
}
if (typeof URL.parse !== 'function') {
  URL.parse = function (url, base) {
    try { return new URL(url, base) } catch { return null }
  }
}

import 'react-pdf/node_modules/pdfjs-dist/build/pdf.worker.min.mjs'
