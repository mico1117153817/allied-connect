# Vendored PDF.js decoder provenance

`pdf.image_decoders.mjs` is the **unmodified** npm `pdfjs-dist@4.10.38`
image-decoder ES module (build `f9bea397f`). The Python adapter appends its
own module-scope bridge at load time; it does not rewrite this asset.

- Source: https://unpkg.com/pdfjs-dist@4.10.38/image_decoders/pdf.image_decoders.mjs
- Upstream: https://github.com/mozilla/pdf.js/tree/v4.10.38
- SHA-256: `9f4c84cfe904230c65ef1907674d8f46ded8deb5084c5b821859bdb6f3c15c34`
- License: Apache-2.0, copyright Mozilla Foundation; full npm package LICENSE
  is included alongside the retained source copyright/license banner.
- LICENSE source: https://unpkg.com/pdfjs-dist@4.10.38/LICENSE

This is intentionally the last-generation pure-JavaScript `Jbig2Image` API,
not the installed frontend's 6.3.289 PDFium-derived Emscripten decoder.
The latter has a different API and is not the backend artifact. The backend
executes `Jbig2Image.parseChunks` in-process using `quickjs-ng==0.16.2.1`
(import name `quickjs`). No browser, Node, WebAssembly, executable decoder,
AGPL libjbig2dec, or runtime asset download is used.

`QUICKJS-NG-LICENSE` is copied from the exact wheel's license metadata (MIT).
`QUICKJS-SOURCE-NOTICES` retains the license/copyright headers from the exact
PyPI 0.16.2.1 source distribution's C/H sources, including its bundled engine.
The installed wheel carries the native library; no native library is vendored
in this directory.

When upgrading either dependency, rerun the real malformed/valid/globals and
OS-isolation regressions on Windows and Linux. Do not replace detectable
decode failure with a non-null bitmap check or permit fallback to subprocesses.
