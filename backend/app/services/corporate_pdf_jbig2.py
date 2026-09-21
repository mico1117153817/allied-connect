"""In-process PDF.js JBIG2 validation; called only inside the bounded PDF worker.

No host callbacks, JS file/network APIs, native decoder child, or recovery path.
The original Apache-2.0 bundle is loaded as an ES module, unmodified.
"""
from pathlib import Path

_RESOURCE = Path(__file__).resolve().parents[1] / 'vendor' / 'pdfjs'
_JS_MEMORY = 64 * 1024 * 1024

# Appended in the same module so the adapter can enforce page information before
# PDF.js allocates its output. Actual entropy/bitmap decoding is still PDF.js.
_BRIDGE = r'''
globalThis.validateJbig2 = function(hex, globalsHex, width, height, budget) {
  function bytes(s) {
    const result = new Uint8Array(s.length / 2);
    for (let i = 0; i < result.length; i++) result[i] = parseInt(s.slice(i*2, i*2+2), 16);
    return result;
  }
  const chunks = [];
  let pages = 0;
  for (const [s, global] of [[globalsHex, true], [hex, false]]) {
    if (!s.length) { if (global) continue; throw Error('empty JBIG2'); }
    const data = bytes(s);
    const segments = readSegments({}, data, 0, data.length);
    if (!segments.length || segments[segments.length-1].end !== data.length)
      throw Error('JBIG2 segment framing');
    for (const segment of segments) {
      if (segment.start > data.length || segment.end > data.length || segment.end < segment.start)
        throw Error('truncated JBIG2 segment');
      if (segment.header.type === 48) {
        if (global || segment.end-segment.start < 19 || ++pages !== 1)
          throw Error('JBIG2 page information');
        if (readUint32(data, segment.start) !== width || readUint32(data, segment.start+4) !== height)
          throw Error('JBIG2 dimension mismatch');
      }
    }
    chunks.push({data, start: 0, end: data.length});
  }
  if (pages !== 1) throw Error('missing JBIG2 page');
  const original = SimpleSegmentVisitor.prototype.onPageInformation;
  SimpleSegmentVisitor.prototype.onPageInformation = function(info) {
    if (info.width !== width || info.height !== height || Math.ceil(info.width/8)*info.height > budget)
      throw Error('JBIG2 decoded budget');
    return original.call(this, info);
  };
  try {
    const output = new Jbig2Image().parseChunks(chunks);
    if (!output || output.length !== Math.ceil(width/8)*height)
      throw Error('JBIG2 missing bitmap');
    return output.length;
  } finally { SimpleSegmentVisitor.prototype.onPageInformation = original; }
};
'''


def _normalize_filters(stream):
    """Resolve and validate before any pypdf dispatch (which zips parameters)."""
    from pypdf.generic import ArrayObject, DictionaryObject, NameObject, NullObject, StreamObject

    filters = stream.get('/Filter', ArrayObject()).get_object()
    if isinstance(filters, NameObject):
        filters = ArrayObject([filters])
    if not isinstance(filters, ArrayObject):
        raise ValueError('PDF filter shape')
    filters = ArrayObject([item.get_object() for item in filters])
    if any(not isinstance(item, NameObject) for item in filters):
        raise ValueError('PDF filter name required')
    params = stream.get('/DecodeParms', NullObject()).get_object()
    if isinstance(params, NullObject):
        params = ArrayObject([NullObject() for _ in filters])
    elif isinstance(params, DictionaryObject) and not isinstance(params, StreamObject) and len(filters) == 1:
        params = ArrayObject([params])
    if not isinstance(params, ArrayObject) or len(params) != len(filters):
        raise ValueError('PDF filter parameters')
    params = ArrayObject([item.get_object() for item in params])
    if any(not isinstance(item, (DictionaryObject, NullObject)) or isinstance(item, StreamObject)
           for item in params):
        raise ValueError('PDF filter parameter dictionary required')
    # Ordinary streams must also use these resolved, cardinality-checked values.
    if '/Filter' in stream:
        stream[NameObject('/Filter')] = filters
        stream[NameObject('/DecodeParms')] = params
    return filters, params


def decoded_size(stream, budget):
    """Decode a JBIG2 image (including prefix filters/globals), return byte count.

    Other streams return None and retain the ordinary pypdf strict path.
    Unsupported filter placement and recursive globals fail closed.
    """
    from pypdf.generic import ArrayObject, NameObject, StreamObject
    filters, params = _normalize_filters(stream)
    if '/JBIG2Decode' not in filters:
        return None
    if filters[-1] != '/JBIG2Decode' or filters.count('/JBIG2Decode') != 1:
        raise ValueError('JBIG2 must be the final image filter')
    if stream.get('/Subtype') != '/Image' or stream.get('/BitsPerComponent', 1) != 1:
        raise ValueError('JBIG2 image required')
    width, height = stream.get('/Width'), stream.get('/Height')
    if (not isinstance(width, int) or not isinstance(height, int)
            or width <= 0 or height <= 0 or width > 0x7ffffff0
            or ((width + 7) // 8) * height > budget):
        raise ValueError('JBIG2 decoded budget')
    last_params = params[-1]
    globals_data = b''
    if hasattr(last_params, 'get') and last_params.get('/JBIG2Globals') is not None:
        globals_stream = last_params['/JBIG2Globals'].get_object()
        if not isinstance(globals_stream, StreamObject):
            raise ValueError('JBIG2 globals stream required')
        gf, _ = _normalize_filters(globals_stream)
        if '/JBIG2Decode' in gf:
            raise ValueError('recursive JBIG2 globals')
        globals_data = globals_stream.get_data()
    data = stream._data
    if len(filters) > 1:
        # Use pypdf for all preceding filters, never its external JBIG2 decoder.
        from pypdf.generic import EncodedStreamObject
        prefix = EncodedStreamObject()
        prefix._data = data
        prefix[NameObject('/Filter')] = ArrayObject(filters[:-1])
        prefix[NameObject('/DecodeParms')] = ArrayObject(params[:-1])
        data = prefix.get_data()
    if not data or len(data) + len(globals_data) > 20 * 1024 * 1024:
        raise ValueError('JBIG2 encoded budget')
    import quickjs
    context = quickjs.Context()
    context.set_memory_limit(_JS_MEMORY)
    context.set_max_stack_size(512 * 1024)
    context.set_time_limit(3)
    try:
        context.module((_RESOURCE / 'pdf.image_decoders.mjs').read_text(encoding='utf-8') + _BRIDGE)
        return context.get('validateJbig2')(data.hex(), globals_data.hex(), width, height, budget)
    except quickjs.JSException as exc:
        raise ValueError('JBIG2 decode failed') from exc
