# Local PDF resource regressions

- `npm test`: also checks every installed PDF.js WASM/fallback, CMap, standard font and license is emitted byte-for-byte by the production build and served by dev, including a `/portal/` base path and JS/WASM MIME types.
- `npx playwright install chromium` (once), then `npm run test:pdf`: runs the **real viewer loader, PDF.js engine and worker** in headless Chromium against Vite dev and a separately built production harness under `/portal/`. It does not call any company API or modify company records. It checks exact scan pixels, visible text, local resource requests and absence of decoder warnings. Temporary builds and screenshots go to `node_modules/.cache/pdf-scans-*`, not the application `dist`.

The five small PDFs in `fixtures/` are synthetic, contain no corporate data, and are checked in so browser tests do not require Python. To regenerate: `python tests/fixtures/generate-scans.py` with Pillow and JPEG2000 support.

- CCITT: TIFF Group 4 strip embedded with `/CCITTFaxDecode`.
- JBIG2: page-info and immediate generic MMR region segments using the same fax strip (not a renamed CCITT PDF).
- JPX: lossless JPEG2000 embedded with `/JPXDecode`.
- All scans display a 48 × 96 black rectangle on a 128 × 128 white image: exactly 4,608 dark pixels. The TIFF strip's photometric interpretation is accounted for with the grayscale Decode array.
- Symbol: unembedded standard Symbol font, exercising `FoxitSymbol.pfb`.
- CMap: Japanese text with predefined `UniJIS-UCS2-H`, exercising both that CMap and `Adobe-Japan1-UCS2`.

The Vite plugin emits all three installed resource directories (~3.5 MB total for PDF.js 6.3.289), with licenses. No generated dependency assets are checked in. `useWasm: false` is deliberately retained: CCITT/JBIG2 and JPX use the locally served JavaScript fallbacks; the complete matching WASM resources are also shipped. Documents are never sent to a CDN. These tests do not establish support for older mobile browser APIs or replace the full application's lifecycle/authorization E2E gate.
