#!/usr/bin/env python3
"""使用同一份暂存应用文件构建 KUAL ZIP 和 KPM 安装包。"""

import argparse
import fnmatch
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[2]
EXCLUDE = ('__pycache__', '*.pyc', '*.pyo', '.DS_Store', '.pytest_cache',
           'logs', 'tmp', 'downloads')
HOOKS = ('install.sh', 'launch.sh', 'uninstall.sh')


def package_version(manifest, tag):
    if tag:
        if not re.fullmatch(r'v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', tag):
            raise ValueError('发布标签必须为 v主版本.次版本.修订号，例如 v1.2.3')
        return [int(part) for part in tag[1:].split('.')]
    version = manifest['version']
    if (not isinstance(version, list) or len(version) != 3
            or any(type(part) is not int or part < 0 for part in version)):
        raise ValueError('manifest.json 的 version 必须是三个非负整数')
    return version


def stage_application(destination, version):
    shutil.copytree(ROOT / 'bin', destination / 'bin', ignore=shutil.ignore_patterns(*EXCLUDE))
    for name in ('LICENSE', 'README.md'):
        shutil.copy2(ROOT / name, destination / name)
    app = destination / 'bin' / 'kcomics.py'
    source, replacements = re.subn(r'^VERSION\s*=\s*[\'"][^\'"]*[\'"]\s*$',
                                   f'VERSION = "v{version}"', app.read_text(encoding='utf-8'),
                                   flags=re.MULTILINE)
    if replacements != 1:
        raise ValueError('无法定位 bin/kcomics.py 中唯一的 VERSION 常量')
    app.write_text(source, encoding='utf-8')


def executable_scripts(directory):
    for path in directory.rglob('*.sh'):
        path.chmod(0o755)


def verify_packages(kpkg, kual_zip, manifest):
    """检查安装目录、钩子、版本、启动权限以及缓存排除情况。"""
    required = {'bin/kcomics.py', 'bin/start.sh', 'bin/kcomics.sh', 'bin/config.json', 'LICENSE'}
    with tarfile.open(kpkg, 'r:gz') as archive:
        members = {item.name: item for item in archive.getmembers()}
        missing = (required | {'manifest.json', *HOOKS}) - members.keys()
        if missing:
            raise ValueError(f'KPM 安装包缺少文件: {sorted(missing)}')
        packaged_manifest = json.load(archive.extractfile('manifest.json'))
        if packaged_manifest != manifest:
            raise ValueError('KPM 安装包 manifest 与构建版本不一致')
        for name in (*HOOKS, 'bin/start.sh', 'bin/kcomics.sh'):
            if members[name].mode & 0o111 != 0o111:
                raise ValueError(f'KPM 脚本不可执行: {name}')
        kpm_app = archive.extractfile('bin/kcomics.py').read()
        names = list(members)
    with zipfile.ZipFile(kual_zip) as archive:
        prefix = 'kcomics/'
        members = {item.filename: item for item in archive.infolist()}
        missing = {prefix + name for name in required | {'config.xml', 'menu.json'}} - members.keys()
        if missing or any(not name.startswith(prefix) for name in members):
            raise ValueError(f'KUAL 安装包目录结构错误: {sorted(missing)}')
        for name in ('bin/start.sh', 'bin/kcomics.sh'):
            if (members[prefix + name].external_attr >> 16) & 0o111 != 0o111:
                raise ValueError(f'KUAL 脚本不可执行: {name}')
        if archive.read(prefix + 'bin/kcomics.py') != kpm_app:
            raise ValueError('KPM 与 KUAL 的应用版本不一致')
        names.extend(members)
    for name in names:
        if any(fnmatch.fnmatch(part, pattern) for part in Path(name).parts for pattern in EXCLUDE):
            raise ValueError(f'安装包包含运行缓存: {name}')


def build(helper, output, tag=''):
    manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
    manifest['version'] = package_version(manifest, tag)
    version = '.'.join(map(str, manifest['version']))
    output.mkdir(parents=True, exist_ok=True)
    kpkg = output / f"{manifest['id']}_{version}_{'-'.join(manifest['supported_platforms'])}.kpkg"
    kual_zip = output / f'kComics-v{version}.zip'

    with tempfile.TemporaryDirectory(prefix='kcomics-package-') as temporary:
        staging = Path(temporary)
        kual = staging / 'kual' / 'kcomics'
        stage_application(kual, version)
        for name in ('config.xml', 'menu.json'):
            shutil.copy2(ROOT / name, kual / name)
        executable_scripts(kual)
        with zipfile.ZipFile(kual_zip, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(kual.rglob('*')):
                if path.is_file():
                    archive.write(path, path.relative_to(kual.parent).as_posix())

        kpm = staging / 'kpm'
        shutil.copytree(kual / 'bin', kpm / 'bin')
        for name in (*HOOKS, 'LICENSE', 'README.md'):
            shutil.copy2(ROOT / name, kpm / name)
        (kpm / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        executable_scripts(kpm)
        # 按官方格式和文件名处理；不要打包工作区（或其中的 .git）。
        subprocess.run([sys.executable, str(helper), 'package', 'pack', str(kpm), str(kpkg)], check=True)

    verify_packages(kpkg, kual_zip, manifest)
    with (output / 'SHA256SUMS').open('w', encoding='utf-8') as checksums:
        for path in (kpkg, kual_zip):
            with path.open('rb') as file:
                digest = hashlib.file_digest(file, 'sha256').hexdigest()
            checksums.write(f'{digest}  {path.name}\n')
            print(f'已生成并验证: {path} ({path.stat().st_size:,} bytes)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kpm-helper', required=True, type=Path)
    parser.add_argument('--output-dir', type=Path, default=Path('dist'))
    parser.add_argument('--tag', default='', help='vX.Y.Z; 不传时使用 manifest.json 的版本')
    args = parser.parse_args()
    if not args.kpm_helper.is_file():
        parser.error('找不到 kpm-helper.py，请先下载官方工具')
    try:
        build(args.kpm_helper.resolve(), args.output_dir.resolve(), args.tag)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'打包失败: {error}\n')
