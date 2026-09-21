"""Generate small deterministic scanned-PDF regressions (requires Pillow with JPEG2000)."""
from io import BytesIO
from pathlib import Path
from struct import pack
from PIL import Image, ImageDraw, features

OUT = Path(__file__).parent

def pdf(name, image, properties):
    content = b'q 128 0 0 128 0 0 cm /Im Do Q'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 128 128] /Resources << /XObject << /Im 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /XObject /Subtype /Image /Width 128 /Height 128 ' + properties + b' /Length ' + str(len(image)).encode() + b' >>\nstream\n' + image + b'\nendstream',
        b'<< /Length ' + str(len(content)).encode() + b' >>\nstream\n' + content + b'\nendstream']
    write_pdf(name, objects)

def write_pdf(name, objects):
    result = b'%PDF-1.7\n'; offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(result)); result += f'{index} 0 obj\n'.encode() + obj + b'\nendobj\n'
    xref = len(result)
    size = len(objects) + 1
    result += f'xref\n0 {size}\n0000000000 65535 f \n'.encode() + b''.join(f'{n:010d} 00000 n \n'.encode() for n in offsets[1:])
    result += f'trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
    (OUT / name).write_bytes(result)

image = Image.new('1', (128, 128), 1)
draw = ImageDraw.Draw(image)
draw.rectangle((16, 16, 63, 111), fill=0)
buffer = BytesIO(); image.save(buffer, format='TIFF', compression='group4')
tiff = Image.open(BytesIO(buffer.getvalue()))
assert len(tiff.tag_v2[273]) == 1
start, length = tiff.tag_v2[273][0], tiff.tag_v2[279][0]
ccitt = buffer.getvalue()[start:start + length]
pdf('ccitt.pdf', ccitt, b'/ColorSpace /DeviceGray /BitsPerComponent 1 /Decode [1 0] /Filter /CCITTFaxDecode /DecodeParms << /K -1 /Columns 128 /Rows 128 /BlackIs1 false >>')

def segment(number, kind, data):
    return pack('>IBBBI', number, kind, 0, 1, len(data)) + data
jbig2 = segment(1, 48, pack('>IIIIBH', 128, 128, 0, 0, 0, 0))
jbig2 += segment(2, 38, pack('>IIIIBB', 128, 128, 0, 0, 0, 1) + ccitt)
jbig2 += segment(3, 49, b'')
pdf('jbig2.pdf', jbig2, b'/ColorSpace /DeviceGray /BitsPerComponent 1 /Decode [1 0] /Filter /JBIG2Decode')
assert features.check('jpg_2000'), 'Pillow requires JPEG2000 support'
buffer = BytesIO(); image.convert('RGB').save(buffer, format='JPEG2000', irreversible=False)
pdf('jpx.pdf', buffer.getvalue(), b'/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /JPXDecode')
print('Generated CCITT Group4, JBIG2 MMR, lossless JPX: 128x128 white with black rectangle x16..63/y16..111')

for name, font, text, extra in [
    ('symbol', b'<< /Type /Font /Subtype /Type1 /BaseFont /Symbol >>', b'(abc)', []),
    ('cmap', b'<< /Type /Font /Subtype /Type0 /BaseFont /HeiseiKakuGo-W5 /Encoding /UniJIS-UCS2-H /DescendantFonts [6 0 R] >>', b'<65E5672C>', [
        b'<< /Type /Font /Subtype /CIDFontType0 /BaseFont /HeiseiKakuGo-W5 /CIDSystemInfo << /Registry (Adobe) /Ordering (Japan1) /Supplement 5 >> /FontDescriptor 7 0 R /DW 1000 >>',
        b'<< /Type /FontDescriptor /FontName /HeiseiKakuGo-W5 /Flags 4 /FontBBox [0 -200 1000 900] /ItalicAngle 0 /Ascent 900 /Descent -200 /CapHeight 700 /StemV 80 >>',
    ]),
]:
    content = b'BT /F1 32 Tf 16 64 Td ' + text + b' Tj ET'
    write_pdf(name + '.pdf', [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 128 128] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        font,
        b'<< /Length ' + str(len(content)).encode() + b' >>\nstream\n' + content + b'\nendstream',
        *extra,
    ])
print('Generated nonembedded Symbol and predefined UniJIS-UCS2-H CMap PDFs')
