import os

from calibre.ebooks.mobi.writer2.main import MobiWriter
from calibre.ebooks.mobi.writer2.resources import Resources
from calibre.ebooks.oeb.base import OEB_RASTER_IMAGES


COPY_BUFFER_SIZE = 64 * 1024

# 导出暂存文件中的一个数据区间
class DiskRecord:
    def __init__(self, stream, offset, size):
        self.stream = stream
        self.offset = offset
        self.size = size
    def __len__(self):
        return self.size
    def read(self, start=0, size=None):
        size = self.size - start if size is None else size
        self.stream.seek(self.offset + start)
        data = self.stream.read(size)
        if len(data) != size:
            raise OSError('MOBI 图片缓存不完整')
        return data
    def __getitem__(self, key):
        # KF8 检查 record[:4]
        if isinstance(key, slice) and key.step in (None, 1):
            start, stop, _ = key.indices(self.size)
            return self.read(start, max(0, stop - start))
        return self.read()[key]
    def copy_to(self, output):
        self.stream.seek(self.offset)
        remaining = self.size
        while remaining:
            data = self.stream.read(min(remaining, COPY_BUFFER_SIZE))
            if not data:
                raise OSError('MOBI 图片缓存不完整')
            output.write(data)
            remaining -= len(data)

# 仅追加的磁盘存储，由 OEB 图片和 MOBI 资源共用
class RecordStore:
    def __init__(self, stream):
        self.stream = stream
    def add(self, data):
        offset = self.stream.seek(0, os.SEEK_END)
        if self.stream.write(data) != len(data):
            raise OSError('MOBI 图片缓存写入不完整')
        return DiskRecord(self.stream, offset, len(data))

# Resources 追加字节时立即暂存
class _DiskRecordList(list):
    def __init__(self, store):
        super().__init__()
        self.store = store
    def append(self, data):
        super().append(self.store.add(data) if isinstance(data, bytes) else data)
    def __setitem__(self, index, data):
        super().__setitem__(index, self.store.add(data) if isinstance(data, bytes) else data)
class DiskResources(Resources):
    def __init__(self, oeb, opts, store):
        self.store = store
        super().__init__(oeb, opts, is_periodical=False, add_fonts=False)
    def add_resources(self, add_fonts):
        self.records = _DiskRecordList(self.store)
        super().add_resources(add_fonts)
        missing = [item.href for item in self.oeb.manifest
                    if item.media_type in OEB_RASTER_IMAGES and item.href not in self.item_map]
        if missing:
            raise ValueError(f'MOBI 图片资源读取失败: {missing[0]}')


class DiskMobiWriter(MobiWriter):
    def write_content(self):
        # 继承而来的 PalmDB 文件头使用 len(record)，因此偏移量和资源索引
        # 与 Calibre 基于字节的输出保持一致。
        for record in self.records:
            if isinstance(record, DiskRecord):
                record.copy_to(self.stream)
            else:
                self.write(record)
