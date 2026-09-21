# Bounded in-process JBIG2 validation

## Implemented path

The strict pypdf page/resource traversal in `corporate_pdf_worker.py` remains
mandatory. JBIG2 image streams alone are dispatched to
`corporate_pdf_jbig2.decoded_size`; other streams retain `get_data()` validation.
The dispatcher decodes preceding PDF filters with pypdf, then invokes the
vendored Apache-2.0 PDF.js 4.10.38 `Jbig2Image.parseChunks` implementation in a
fresh in-process QuickJS-NG context. Global symbol dictionaries are supplied
as the first chunk and are decoded, not ignored. Corrupt data raises and the
worker reports failure. There is no external decoder process or fallback.

The frontend's PDF.js version and assets are unchanged. Backend resource
provenance, exact hash, and permissive notices are in
`backend/app/vendor/pdfjs/README.md`. `quickjs-ng==0.16.2.1` is pinned in backend
requirements; its Python import name is `quickjs`.

## Bounds and contract

- Existing worker: 128 MiB process address-space/memory cap, 5 CPU seconds,
  parent wall-clock timeout, single worker slot. Linux RLIMITs and Windows Job
  Object (active-process limit 1) are unchanged and installed before imports
  or reading uploaded input.
- Additional JS context limits: 64 MiB heap, 512 KiB stack, 3-second execution
  interrupt. No host callbacks, JS filesystem/network API, or asset fetching.
- 8 MiB decoded bytes per PDF page and 32 MiB per document, including repeated
  image use on different pages; JBIG2 bitmap byte size is checked against the
  *remaining* budgets before decode. Pixel dimensions must match JBIG2 page
  information. Segment framing/truncation, missing/multiple page information,
  recursive globals and unsupported JBIG2 filter placement fail closed.
- Existing 20 MiB input, 250-page and 50,000-object limits still apply.
- The worker remains `python -I`; its trusted sibling adapter is loaded by
  absolute filename, not by adding a module search path.

This is standard bounded validation, not proof that every arbitrary damaged
bitstream is invalid or that every valid PDF/JBIG2 coding variant is accepted.
PDF.js unsupported features, very expensive valid images, and decoder limits
fail closed. Arithmetic/image decoders can tolerate some damage; the supplied
malformed bitstream is explicitly rejected by the actual decoder, rather than
accepted merely because a renderer returned a black bitmap. Keep these
limitations distinct from the enforced OS isolation and output budgets.

## Evidence and repeatable Linux deployment gate

On Windows the original regression first failed with pypdf's missing external
jbig2dec dependency. It now passes with subprocess creation forbidden. The real
`python -I` worker accepts the valid fixture and rejects corrupt input with
`isolation: true`, under the unchanged Job Object. Full isolated-environment
backend run: **208 passed, 29 skipped** (pre-existing optional integration
skips), plus existing pytest/AnyIO deprecation warnings.

Run the following on the deployment host against the exact candidate tree,
using a staging virtualenv/container, before promotion. The production Render
allocation is approved at 2 GB / 1 CPU; do not increase worker limits to consume
that allocation. The frontend fixture must be present in the proof checkout.

```sh
uv venv .hermes/jbig2-linux-proof --python 3.11
uv pip install --python .hermes/jbig2-linux-proof/bin/python -r backend/requirements.txt
cd backend
../.hermes/jbig2-linux-proof/bin/python -I -m pytest tests/test_corporate_pdf_jbig2_regression.py tests/test_corporate_pdf_isolation.py -q
../.hermes/jbig2-linux-proof/bin/python -I -m pytest tests -q
../.hermes/jbig2-linux-proof/bin/python -I app/services/corporate_pdf_worker.py < ../frontend/tests/fixtures/jbig2.pdf
# Expected final JSON: {"ok": true, "isolation": true}
```

The regression launches the actual worker for both valid and corrupt PDFs;
on Linux that exercises RLIMIT_AS/RLIMIT_CPU, not a mock. The isolation suite
also checks actual memory enforcement, timeout/cancellation cleanup, secret-free
worker environment, and concurrency. Do not label Linux proof complete until
those commands have run on Linux; local evidence above is Windows only.

Deployment packaging must include `backend/app/vendor/pdfjs/*` and the adapter
alongside requirements. No frontend `node_modules` dependency is needed at
runtime. Do not install AGPL libjbig2dec or use pypdfium2's non-null bitmap as a
strict-decode success signal.
