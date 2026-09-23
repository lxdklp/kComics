"""MOBI 磁盘资源：输出兼容性、载荷内存上限和故障处理。"""

import io
import os
import random
import tempfile
import time
import tracemalloc
from datetime import datetime, timezone

import pytest
from PIL import Image

from export import kindle, mobi_convert
from export.disk_resources import COPY_BUFFER_SIZE, DiskRecord, RecordStore


def _fixed_metadata(monkeypatch):
    class FixedDatetime:
        @staticmethod
        def now(tz):
            return datetime(2026, 1, 1, tzinfo=timezone.utc)

    monkeypatch.setattr(mobi_convert, 'datetime', FixedDatetime)
    monkeypatch.setattr(time, 'time', lambda: 1767225600)
    monkeypatch.setattr(random, 'randint', lambda *_: 123456789)


@pytest.mark.parametrize('rtl,grayscale', [(True, True), (False, False)])
def test_streamed_mobi_matches_legacy_bytes(tmp_path, monkeypatch, rtl, grayscale):
    """比较完整的 PalmDB、KF8 元数据、资源索引和图片字节。"""
    _fixed_metadata(monkeypatch)
    paths = []
    for i, fmt in enumerate(('JPEG', 'PNG', 'GIF', 'WEBP')):
        path = tmp_path / f'{i}.{fmt.lower()}'
        with Image.new('RGB', (180, 240), (i * 60, 80, 120)) as img:
            img.save(path, fmt)
        paths.append(str(path))
    # 这张较小的 JPEG 不会缩放；Calibre 会根据 EXIF 方向对其进行规范化。
    # 因此最终资源大小与 OEB 图片不同。
    path = tmp_path / 'exif.jpg'
    with Image.new('RGB', (60, 80), (30, 60, 90)) as img:
        exif = Image.Exif()
        exif[0x0112] = 6
        img.save(path, 'JPEG', exif=exif)
    paths.append(str(path))
    opts = dict(title='测试漫画', author='作者', rtl=rtl, grayscale=grayscale,
                resolution='120x160', asin='B0ABC12345', tmp_dir=str(tmp_path))
    expected = mobi_convert.build_mobi([mobi_convert._read_page(p) for p in paths], **opts)
    target = tmp_path / 'streamed.mobi'
    mobi_convert.build_mobi_from_paths(paths, out_path=str(target), **opts)
    assert target.read_bytes() == expected
    # 同时保留可选的字节返回接口；设备导出使用 out_path。
    assert mobi_convert.build_mobi_from_paths(paths, **opts) == expected
    assert all(os.path.isfile(p) for p in paths)


def test_disk_record_copies_in_bounded_chunks():
    class ReadTracker(io.BytesIO):
        def __init__(self):
            super().__init__()
            self.read_sizes = []

        def read(self, size=-1):
            self.read_sizes.append(size)
            assert 0 <= size <= COPY_BUFFER_SIZE
            return super().read(size)

    with ReadTracker() as spool:
        store = RecordStore(spool)
        store.add(b'previous record')
        data = random.Random(42).randbytes(COPY_BUFFER_SIZE * 3 + 7)
        record = store.add(data)
        store.add(b'next record')
        assert len(record) == len(data)
        assert record[:4] == data[:4]
        assert spool.read_sizes == [4]
        output = io.BytesIO()
        record.copy_to(output)
        assert output.getvalue() == data
        assert spool.read_sizes == [4, COPY_BUFFER_SIZE, COPY_BUFFER_SIZE, COPY_BUFFER_SIZE, 7]


def test_truncated_disk_record_fails():
    with tempfile.TemporaryFile() as spool:
        record = RecordStore(spool).add(b'page bytes')
        spool.truncate(3)
        with pytest.raises(OSError, match='缓存不完整'):
            record.read()
        with pytest.raises(OSError, match='缓存不完整'):
            record.copy_to(io.BytesIO())


@pytest.mark.parametrize('failure', ['cache_write', 'cache_read', 'output_write'])
def test_export_failure_closes_spool_and_preserves_target(tmp_path, monkeypatch, failure):
    source = tmp_path / 'page.jpg'
    with Image.new('L', (80, 120), 128) as img:
        img.save(source, 'JPEG')
    target = tmp_path / 'book.mobi'
    target.write_bytes(b'previous valid book')
    opened = []
    temporary_file = tempfile.NamedTemporaryFile

    def track_file(*args, **kwargs):
        file = temporary_file(*args, **kwargs)
        opened.append(file)
        return file

    def fail(*args, **kwargs):
        raise OSError('simulated I/O failure')

    monkeypatch.setattr(tempfile, 'NamedTemporaryFile', track_file)
    owner, method = {'cache_write': (RecordStore, 'add'),
                     'cache_read': (DiskRecord, 'read'),
                     'output_write': (DiskRecord, 'copy_to')}[failure]
    monkeypatch.setattr(owner, method, fail)
    with pytest.raises((OSError, ValueError)):
        kindle._convert_with_calibre('book', [str(source)], True, str(tmp_path),
                                     resolution='1236x1648', tmp_dir=str(tmp_path))
    assert target.read_bytes() == b'previous valid book'
    assert source.exists()
    assert not (tmp_path / 'book.mobi.tmp').exists()
    assert opened and all(file.closed for file in opened)
    assert not list(tmp_path.glob('kcomics_mobi_*'))


def test_spool_stays_linked_and_uses_project_tmp(tmp_path, monkeypatch):
    """Kindle 的 fsp 无法定位到已解除链接的文件；不要使用匿名 /tmp 存储。"""
    import config

    source = tmp_path / 'page.jpg'
    with Image.new('L', (80, 120), 128) as img:
        img.save(source, 'JPEG')
    cache_dir = tmp_path / 'project_tmp'
    monkeypatch.setattr(config, 'get_export_tmp_dir', lambda: str(cache_dir))
    seen = []

    def interrupted_progress(i, total):
        seen.extend(cache_dir.glob('kcomics_mobi_*'))
        assert len(seen) == 1 and seen[0].is_file()
        raise RuntimeError('interrupted')

    with pytest.raises(RuntimeError, match='interrupted'):
        mobi_convert.build_mobi_from_paths([str(source)], 'book',
                                           out_path=str(tmp_path / 'book.mobi'),
                                           progress=interrupted_progress)
    assert seen and not seen[0].exists()
    assert source.exists()


def test_large_book_does_not_retain_image_payloads(tmp_path):
    """不使用模拟对象，通过约 32 MiB 的 JPEG 资源运行真实写入器。"""
    source = tmp_path / 'noise.jpg'
    with Image.frombytes('L', (512, 512), random.Random(42).randbytes(512 * 512)) as img:
        img.save(source, 'JPEG', quality=95)
    paths = [str(source)] * 128
    payload_size = source.stat().st_size * len(paths)
    target = tmp_path / 'large.mobi'
    tracemalloc.start()
    try:
        mobi_convert.build_mobi_from_paths(paths, 'large', out_path=str(target),
                                           tmp_dir=str(tmp_path), resolution='1236x1648')
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert target.stat().st_size > payload_size
    # 峰值包含所有追踪到的标记和索引分配，以及临时字节。
    # 旧实现会在序列化前至少保留 payload_size 大小的数据。
    assert peak < payload_size / 2, f'peak={peak}, image payload={payload_size}'
