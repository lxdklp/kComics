import os
import shutil

import config
from . import mobi_convert

IMG_EXTS = ('.jpg', '.jpeg', '.webp', '.png', '.gif')

# Kindle 封面图
THUMB_DIR = '/mnt/us/system/thumbnails'
THUMB_W, THUMB_H = 168, 240

# 安全化文件名
def _safe(name):
    for ch in '\\/:*?"<>|':
        name = name.replace(ch, '_')
    return name.strip() or '未知'

# 获取封面图路径
def _thumb_path(asin):
    return os.path.join(THUMB_DIR, f'thumbnail_{asin}_EBOK_portrait.jpg')

# 制作封面图
def _make_thumb_jpeg(cover_mime, cover_data):
    from PIL import Image
    import io as _io
    img = Image.open(_io.BytesIO(cover_data))
    img.load()
    w, h = img.size
    scale = min(1.0, THUMB_W / w, THUMB_H / h)
    if scale < 1.0:
        w, h = max(1, int(w * scale)), max(1, int(h * scale))
        img = img.resize((w, h), Image.Resampling.LANCZOS)
    if img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')
    buf = _io.BytesIO()
    img.save(buf, 'JPEG', quality=88)
    return buf.getvalue()

# 写入封面
def _write_thumb(asin, cover_mime, cover_data):
    try:
        os.makedirs(THUMB_DIR, exist_ok=True)
        path = _thumb_path(asin)
        tmp = path + '.tmp'
        with open(tmp, 'wb') as f:
            f.write(_make_thumb_jpeg(cover_mime, cover_data))
        os.replace(tmp, path)
        print(f"[导出] 已写入锁屏缩略图 {path}")
    except OSError as e:
        print(f"[导出] 缩略图写入失败(不影响导出):{type(e).__name__}: {e}")

# 清理下载目录
def cleanup_downloads(root=None):
    base = root or config.get_downloads_dir()
    if not os.path.isdir(base):
        return
    for entry in os.listdir(base):
        p = os.path.join(base, entry)
        try:
            if os.path.isdir(p) and not os.path.islink(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                os.remove(p)
        except OSError:
            pass

# 返回漫画已下载章节
def scan_comic(title, root=None):
    base = root or config.get_downloads_dir()
    comic_dir = os.path.join(base, _safe(title))
    chapters = []
    if not os.path.isdir(comic_dir):
        return chapters
    for name in sorted(os.listdir(comic_dir)):
        d = os.path.join(comic_dir, name)
        if not os.path.isdir(d):
            continue
        imgs = [os.path.join(d, p) for p in sorted(os.listdir(d))
                if os.path.splitext(p)[1].lower() in IMG_EXTS]
        if imgs:
            chapters.append((name, imgs))
    return chapters

# 导出漫画为 Kindle MOBI
def _convert_with_calibre(bname, page_paths, rtl, out_dir, resolution=None, tmp_dir=None,
                            asin=None, grayscale=True, jpeg_quality=70, progress=None):
    filename = _safe(bname) + '.mobi'
    target = os.path.join(out_dir, filename)
    tmp = target + '.tmp'
    try:
        mobi_convert.build_mobi_from_paths(page_paths, bname, rtl=rtl, resolution=resolution,
                                            out_path=tmp, tmp_dir=tmp_dir, asin=asin,
                                            grayscale=grayscale, jpeg_quality=jpeg_quality,
                                            progress=progress)
        os.replace(tmp, target)
        return True, filename
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass

# 按导出设置把章节分组
def _group_books(title, chapters, merged, chapters_per_book):
    if not merged:
        return [(f'{title}-{name}', paths) for name, paths in chapters]
    books = []
    for i in range(0, len(chapters), chapters_per_book):
        group = chapters[i:i + chapters_per_book]
        if len(group) == 1:
            bname = f'{title}-{group[0][0]}'
        else:
            bname = f'{title}-{group[0][0]}~{group[-1][0]}'
        books.append((bname, [p for _, paths in group for p in paths]))
    return books

# 导出漫画为 Kindle MOBI 并移动到书库
# 三阶段流程:
#   1. 处理图片:逐书转码落盘到任务临时目录,每页确认落盘后删除 download 原图(页进度)
#   2. 导出为MOBI:逐书从 tmp 读回构建 .mobi(书本进度 stage='mobi')
#   3. 移动:统一移入 Kindle 书库 + 锁屏缩略图(文件进度 stage='move')
def export_comic(title, merged=True, chapters_per_book=5, rtl=True, docs_dir=None,
                progress=None, ask_overwrite=None, stage_callback=None,
                root=None, resolution=None, grayscale=None, jpeg_quality=None,
                workers=None):
    if grayscale is None:
        grayscale = config.get_export_grayscale()
    if jpeg_quality is None:
        jpeg_quality = config.get_export_jpeg_quality()
    if workers is None:
        workers = 2 if config.get_export_parallel() else 1
    docs_dir = docs_dir or config.get_kindle_documents_dir()
    chapters = scan_comic(title, root)
    if not chapters:
        return False, '没有已下载的章节可导出'
    if not docs_dir:
        return False, 'Kindle 书库目录不存在'
    try:
        os.makedirs(docs_dir, exist_ok=True)
    except OSError as e:
        return False, f'创建书库目录失败:{type(e).__name__}'
    books = _group_books(title, chapters, merged, max(1, chapters_per_book))
    view_w, view_h = mobi_convert.parse_resolution(resolution)
    import tempfile
    export_tmp_dir = config.get_export_tmp_dir()
    os.makedirs(export_tmp_dir, exist_ok=True)
    task_tmp = tempfile.mkdtemp(prefix='kcomics_export_', dir=export_tmp_dir)
    built = []
    generated = []
    failed = []
    try:
        total_pages = sum(len(paths) for _, paths in books)
        pages_done = [0]
        # ———— 阶段1:处理图片(转码落盘 tmp,确认成功才删原图)————
        ready_books = []
        for bname, paths in books:
            if stage_callback:
                stage_callback('build', 0, len(books), bname)
            base = pages_done[0]

            def _page_progress(i, _total):
                pages_done[0] = base + i
                if progress:
                    progress(pages_done[0], total_pages, bname)

            book_tmp = os.path.join(task_tmp, _safe(bname))
            cover, fail_n = mobi_convert.transcode_pages(
                paths, book_tmp, view_w, view_h,
                grayscale=grayscale, jpeg_quality=jpeg_quality,
                workers=workers, progress=_page_progress)
            if fail_n:
                failed.append(f'{bname} 处理失败({fail_n} 页,已保留原图)')
                continue
            ready_books.append((bname, book_tmp, cover))
        # ———— 阶段2:导出为MOBI(逐书从 tmp 读回构建,书本进度)————
        total_books = len(ready_books)
        for i, (bname, book_tmp, cover) in enumerate(ready_books, 1):
            if stage_callback:
                stage_callback('mobi', i - 1, total_books, bname)
            asin = mobi_convert._make_asin()
            tmp_paths = [os.path.join(book_tmp, n) for n in sorted(os.listdir(book_tmp))]
            try:
                ok, filename = _convert_with_calibre(bname, tmp_paths, rtl, task_tmp,
                                                    resolution, tmp_dir=export_tmp_dir,
                                                    asin=asin, grayscale=grayscale,
                                                    jpeg_quality=jpeg_quality)
            except Exception as e:
                ok, filename = False, f'{bname} 生成失败:{type(e).__name__}'
            if ok:
                built.append((filename, os.path.join(task_tmp, filename), asin, cover))
                generated.append(filename)
            else:
                failed.append(filename)
            if stage_callback:
                stage_callback('mobi', i, total_books, bname)
        # ———— 阶段3:移动到 Kindle 书库 ————
        for i, (filename, tmp_path, asin, cover) in enumerate(built, 1):
            if stage_callback:
                stage_callback('move', i, len(built), filename)
            target = os.path.join(docs_dir, filename)
            if os.path.exists(target):
                if ask_overwrite is None:
                    continue
                if not ask_overwrite(filename):
                    continue
            try:
                os.replace(tmp_path, target)
            except OSError as e:
                failed.append(f'{filename} 移动失败:{type(e).__name__}')
            else:
                # 移动成功后写入封面
                _write_thumb(asin, cover[0], cover[1])
    finally:
        shutil.rmtree(task_tmp, ignore_errors=True)
    # 清理已下载的原始图片(成功页在阶段1已逐页删除,此处清残留)
    if generated:
        cleanup_downloads(root)
    if failed:
        return False, ';'.join(failed[:3])
    if not generated:
        return False, '导出完成(已被跳过)'
    return True, f"{len(generated)} 本已导出到Kindle书库"
