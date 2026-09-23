"""Real JBIG2 decoder + real OS-isolated worker acceptance regressions."""
from pathlib import Path
import io
import json
import subprocess
import sys
import zlib

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NullObject, NumberObject
from app.services import corporate_pdf_worker as worker
from app.services.corporate_pdf_jbig2 import decoded_size
from tests.test_corporate_documents import harness, upload

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'frontend/tests/fixtures/jbig2.pdf'


def image():
    reader = PdfReader(FIXTURE)
    return next(iter(reader.pages[0]['/Resources']['/XObject'].values())).get_object()


def altered_pdf(data):
    writer = PdfWriter(clone_from=FIXTURE)
    obj = next(iter(writer.pages[0]['/Resources']['/XObject'].values())).get_object()
    obj._data = data
    result = io.BytesIO()
    writer.write(result)
    return result.getvalue()


def test_real_jbig2_scan_accepted_without_external_decoder(monkeypatch):
    def forbid_child(*args, **kwargs):
        raise AssertionError('PDF validation must not launch an external decoder')
    monkeypatch.setattr(subprocess, 'Popen', forbid_child)
    worker.validate(FIXTURE.read_bytes())


@pytest.mark.parametrize('data', [b'not-a-JBIG2-bitstream', b'', image()._data[:-1]])
def test_corrupt_jbig2_rejected(data):
    with pytest.raises(ValueError):
        worker.validate(altered_pdf(data))


def indirect_pdf(kind, *, corrupt=False, empty_params=False):
    writer = PdfWriter(clone_from=FIXTURE)
    obj = next(iter(writer.pages[0]['/Resources']['/XObject'].values())).get_object()
    name = NameObject('/JBIG2Decode')
    filters = (writer._add_object(name) if kind == 'name' else
               writer._add_object(ArrayObject([name])) if kind == 'array' else
               ArrayObject([writer._add_object(name)]))
    obj[NameObject('/Filter')] = filters
    if corrupt:
        obj._data = b'not-a-JBIG2-bitstream'
    if empty_params:
        obj[NameObject('/DecodeParms')] = ArrayObject()
    result = io.BytesIO()
    writer.write(result)
    return result.getvalue()


@pytest.fixture
def no_external_jbig2(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('EXTERNAL_DECODER_PATH_REACHED')
    monkeypatch.setattr('pypdf.filters.JBIG2Decode.decode', forbidden)


@pytest.mark.parametrize('kind', ['name', 'array', 'element'])
@pytest.mark.parametrize('corrupt,empty_params', [(False, False), (True, False), (True, True)])
def test_indirect_jbig2_dispatch(kind, corrupt, empty_params, no_external_jbig2):
    content = indirect_pdf(kind, corrupt=corrupt, empty_params=empty_params)
    if corrupt:
        with pytest.raises(ValueError):
            worker.validate(content)
    else:
        worker.validate(content)


def test_real_worker_rejects_indirect_empty_parameters():
    result = subprocess.run([sys.executable, '-I', str(ROOT / 'backend/app/services/corporate_pdf_worker.py')],
                            input=indirect_pdf('array', corrupt=True, empty_params=True),
                            capture_output=True, timeout=12)
    assert json.loads(result.stdout) == {'ok': False, 'isolation': True}
    assert result.returncode == 1


@pytest.mark.parametrize('filters', [NumberObject(1), ArrayObject([NumberObject(1)])])
def test_invalid_ordinary_filter_shape(filters):
    obj = image()
    obj[NameObject('/Filter')] = filters
    with pytest.raises(ValueError):
        decoded_size(obj, 2048)


@pytest.mark.parametrize('jbig2', [False, True])
@pytest.mark.parametrize('params', [ArrayObject(), ArrayObject([NullObject(), NullObject()]),
                                   NumberObject(1), ArrayObject([NumberObject(1)])])
def test_filter_parameter_shape_and_cardinality(jbig2, params):
    obj = image()
    obj[NameObject('/Filter')] = ArrayObject([NameObject('/JBIG2Decode' if jbig2 else '/FlateDecode')])
    obj[NameObject('/DecodeParms')] = params
    with pytest.raises(ValueError):
        decoded_size(obj, 2048)


@pytest.mark.parametrize('params', [DictionaryObject(), ArrayObject([NullObject()])])
def test_ordinary_multiple_filters_require_matching_parameters(params):
    obj = image()
    obj[NameObject('/Filter')] = ArrayObject([NameObject('/ASCIIHexDecode'), NameObject('/FlateDecode')])
    obj[NameObject('/DecodeParms')] = params
    with pytest.raises(ValueError):
        decoded_size(obj, 2048)


def test_ordinary_indirect_filters_and_parameters_decode():
    from pypdf.generic import EncodedStreamObject
    writer = PdfWriter()
    obj = EncodedStreamObject()
    obj._data = zlib.compress(b'ordinary stream')
    obj[NameObject('/Filter')] = writer._add_object(ArrayObject([writer._add_object(NameObject('/FlateDecode'))]))
    obj[NameObject('/DecodeParms')] = writer._add_object(ArrayObject([writer._add_object(DictionaryObject())]))
    assert decoded_size(obj, 2048) is None
    assert obj.get_data() == b'ordinary stream'


@pytest.mark.parametrize('location', ['globals', 'prefix'])
@pytest.mark.parametrize('kind', ['name', 'array', 'element'])
def test_indirect_nested_jbig2_never_external(location, kind, no_external_jbig2):
    from pypdf.generic import EncodedStreamObject
    writer = PdfWriter()
    obj = image()
    name = writer._add_object(NameObject('/JBIG2Decode'))
    filters = (name if kind == 'name' else
               writer._add_object(ArrayObject([NameObject('/JBIG2Decode')])) if kind == 'array' else
               ArrayObject([name]))
    if location == 'globals':
        nested = EncodedStreamObject()
        nested._data = b'not-a-JBIG2-bitstream'
        nested[NameObject('/Filter')] = filters
        obj[NameObject('/DecodeParms')] = DictionaryObject({NameObject('/JBIG2Globals'): nested})
    else:
        obj[NameObject('/Filter')] = ArrayObject([filters, NameObject('/JBIG2Decode')])
    with pytest.raises(ValueError):
        decoded_size(obj, 2048)


def test_real_decoder_bitmap_size():
    assert decoded_size(image(), 2048) == 2048


@pytest.mark.parametrize('valid', [True, False])
def test_upload_jbig2_through_isolated_service(harness, valid):
    client, _, _ = harness
    content = FIXTURE.read_bytes() if valid else altered_pdf(b'not-a-JBIG2-bitstream')
    response = upload(client, content=content)
    assert response.status_code == (201 if valid else 400), response.text
    if valid:
        assert client.get(response.json()['document']['view_url']).content == content


def test_dimension_mismatch_rejected():
    obj = image()
    obj[NameObject('/Width')] = NumberObject(129)
    with pytest.raises(ValueError):
        decoded_size(obj, worker.MAX_PAGE_DECODED)


@pytest.mark.parametrize('budget', [0, 2047])
def test_decoded_output_bound(budget):
    with pytest.raises(ValueError):
        decoded_size(image(), budget)


def test_filter_prefix_decoded():
    obj = image()
    obj._data = zlib.compress(obj._data)
    obj[NameObject('/Filter')] = ArrayObject([NameObject('/FlateDecode'), NameObject('/JBIG2Decode')])
    obj[NameObject('/DecodeParms')] = ArrayObject([NullObject(), NullObject()])
    assert decoded_size(obj, 2048) == 2048


def test_globals_actually_decoded():
    obj = image()
    globals_stream = DecodedStreamObject()
    # A valid empty Huffman symbol dictionary, segment 0, page association 0.
    globals_stream.set_data(bytes.fromhex('000000000000000000000a00010000000000000000'))
    obj[NameObject('/DecodeParms')] = DictionaryObject({NameObject('/JBIG2Globals'): globals_stream})
    assert decoded_size(obj, 2048) == 2048
    globals_stream.set_data(b'not-a-JBIG2-bitstream')
    with pytest.raises(ValueError):
        decoded_size(obj, 2048)


def test_page_budget_enforced(monkeypatch):
    monkeypatch.setattr(worker, 'MAX_PAGE_DECODED', 2047)
    with pytest.raises(ValueError):
        worker.validate(FIXTURE.read_bytes())


def test_aggregate_budget_enforced(monkeypatch):
    writer = PdfWriter()
    page = PdfReader(FIXTURE).pages[0]
    writer.add_page(page)
    writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    monkeypatch.setattr(worker, 'MAX_TOTAL_DECODED', 4000)
    with pytest.raises(ValueError):
        worker.validate(out.getvalue())


@pytest.mark.parametrize('valid', [True, False])
def test_real_os_isolated_jbig2_worker(valid):
    content = FIXTURE.read_bytes() if valid else altered_pdf(b'not-a-JBIG2-bitstream')
    result = subprocess.run([sys.executable, '-I', str(ROOT / 'backend/app/services/corporate_pdf_worker.py')],
                            input=content, capture_output=True, timeout=12)
    assert json.loads(result.stdout) == {'ok': valid, 'isolation': True}
    assert result.returncode == (0 if valid else 1)
