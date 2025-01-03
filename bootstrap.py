#!/usr/bin/env python3

import argparse
import logging
import os
import platform
import re
import subprocess
import sys
import tarfile
import types
import urllib.request

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CHROMIUM_URL = 'https://github.com/chrohime/chromium_source_tarball/releases/download'

def add_depot_tools_to_path(src_dir):
  os.environ['DEPOT_TOOLS_UPDATE'] = '0'
  os.environ['CHROMIUM_BUILDTOOLS_PATH'] = os.path.join(os.path.abspath(src_dir), 'buildtools')
  os.environ['PATH'] = os.pathsep.join([
    os.path.join(src_dir, 'third_party/ninja'),
    os.path.join(src_dir, 'third_party/depot_tools'),
    os.environ['PATH'],
  ])
  # Download Windows toolchain, which is required for using reclient.
  os.environ['DEPOT_TOOLS_WIN_TOOLCHAIN'] = '1'
  os.environ['DEPOT_TOOLS_WIN_TOOLCHAIN_BASE_URL'] = 'https://dev-cdn.electronjs.org/windows-toolchains/_'
  os.environ['GYP_MSVS_HASH_27370823e7'] = '28622d16b1'
  os.environ['GYP_MSVS_HASH_7393122652'] = '3ba76c5c20'

def current_os():
  if sys.platform.startswith('linux'):
    return 'linux'
  elif sys.platform.startswith('win'):
    return 'win'
  elif sys.platform == 'darwin':
    return 'mac'
  else:
    raise ValueError(f'Unsupported platform: {sys.platform}')

def current_cpu():
  arch = platform.machine().lower()
  if arch == 'amd64' or arch == 'x86_64' or arch == 'x64':
    return 'x64'
  elif arch == 'arm64':
    return 'arm64'
  elif arch.startswith('arm'):
    return 'arm'
  else:
    raise ValueError(f'Unrecognized CPU architecture: {arch}')

def download_and_extract(url, extract_path):
  def track_progress(members):
    for index, member in enumerate(members):
      if (index + 1) % 5000 == 0:
        print('.', end='', flush=True)
      yield member
  stream = urllib.request.urlopen(url)
  # Set errorlevel=0 because the tarball may include linux symbolic links that
  # do not exist on current platform.
  with tarfile.open(fileobj=stream, mode='r|xz', errorlevel=0) as tar:
    tar.extractall(path=extract_path, members=track_progress(tar))

def download_from_google_storage(
    bucket, sha_file=None, checksum=None, extract=True, output=None):
  args = [ sys.executable,
           'third_party/depot_tools/download_from_google_storage.py',
           '--no_resume', '--no_auth',
           '--bucket', bucket ]
  if checksum:
    args += [ checksum ]
  if sha_file:
    args += [ '-s', sha_file ]
  if extract:
    args += [ '--extract' ]
  if output:
    args += [ '-o', output ]
  subprocess.check_call(args)

def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('--revision', help='The revision to checkout')
  parser.add_argument('--tarball-url', help='Path to Chromium source tarball')
  parser.add_argument('--src-dir', default=os.path.join(ROOT_DIR, 'src'),
                      help='The path of src dir')
  parser.add_argument('--target-cpu', default=current_cpu(),
                      help='Target CPU architecture')
  parser.add_argument('--target-os', default=current_os(),
                      help='Target operating system (win, mac, or linux)')
  args = parser.parse_args()

  if not args.revision and not args.tarball_url:
    print('Must specify either --revision or --tarball-url.')
    return 1

  if args.revision:
    tarball_url = f'{CHROMIUM_URL}/{args.revision}/chromium-{args.revision}.tar.xz'
  else:
    tarball_url = args.tarball_url

  # Download source tarball.
  if not os.path.isdir(args.src_dir):
    tarball_dir = os.path.basename(tarball_url)[:-7]
    if os.path.isdir(tarball_dir):
      print(f'Unable to download tarball since {tarball_dir} exists.')
      return 1

    print('Download and extract', tarball_dir, end='', flush=True)
    download_and_extract(tarball_url, '.')
    print('Done')

    os.rename(tarball_dir, args.src_dir)

  host_os = current_os()
  host_cpu = current_cpu()

  # Bootstrap depot_tools.
  depot_tools_path = os.path.join(args.src_dir, 'third_party/depot_tools')
  add_depot_tools_to_path(args.src_dir)
  if host_os == 'win':
    win_tools = os.path.join(depot_tools_path, 'bootstrap/win_tools.bat')
    subprocess.check_call([ win_tools ])

  # Import gclient.
  sys.path.append(depot_tools_path)
  import gclient
  import gclient_scm
  import gclient_utils

  # Custom gclient to skip git deps.
  class MyGClient(gclient.Dependency):
    def __init__(self, options):
      super(MyGClient, self).__init__(parent=None,
                                      name='src',
                                      url=None,
                                      managed=True,
                                      custom_deps=None,
                                      custom_vars=None,
                                      custom_hooks=None,
                                      deps_file='DEPS',
                                      should_process=True,
                                      should_recurse=True,
                                      relative=None,
                                      condition=None,
                                      print_outbuf=True)
      self._cipd_root = None
      self._gcs_root = None
      self._options = options

    def CreateSCM(self):
      return gclient_scm.CogWrapper()

    def GetCipdRoot(self):
      if not self._cipd_root:
        self._cipd_root = gclient_scm.CipdRoot(
            args.src_dir,
            'https://chrome-infra-packages.appspot.com')
      return self._cipd_root

    def GetGcsRoot(self):
      if not self._gcs_root:
          self._gcs_root = gclient_scm.GcsRoot(args.src_dir)
      return self._gcs_root

    @property
    def root_dir(self):
      return os.path.dirname(args.src_dir)

    @property
    def target_os(self):
      return (args.target_os, )

    @property
    def target_cpu(self):
      return (args.target_cpu, )

  # Suppress warnings from gclient.
  logger = logging.getLogger()
  logger.setLevel(logging.ERROR)

  # Options for gclient, to ignore git deps, which are included in tarball.
  options = types.SimpleNamespace(nohooks=True,
                                  noprehooks=True,
                                  no_history=True,
                                  verbose=False,
                                  false=False,
                                  break_repo_locks=False,
                                  patch_refs=[],
                                  ignore_dep_type=['git'])

  # Sync deps, i.e. gclient sync.
  gclient = MyGClient(options)
  gclient.ParseDepsFile()
  work_queue = gclient_utils.ExecutionQueue(12, None, ignore_requirements=True)
  for dep in gclient.dependencies:
    work_queue.enqueue(dep)
  work_queue.flush(revision_overrides={},
                   command='update',
                   args=[],
                   options=options,
                   patch_refs={},
                   target_branches={},
                   skip_sync_revisions={})
  if gclient._cipd_root:
    gclient._cipd_root.run('update')

  # Run hooks.
  os.chdir(args.src_dir)
  if host_os == 'win':
    subprocess.check_call([ sys.executable,
                            'build/vs_toolchain.py', 'update', '--force' ])
  if host_os == 'linux':
    if args.target_os == 'win':
      download_from_google_storage(
          'chromium-browser-clang/rc',
          extract=False,
          sha_file='build/toolchain/win/rc/linux64/rc.sha1')
  elif host_os == 'mac':
    download_from_google_storage(
        'chromium-browser-clang',
        sha_file=f'tools/clang/dsymutil/bin/dsymutil.{host_cpu}.sha1',
        extract=False,
        output='tools/clang/dsymutil/bin/dsymutil')
    if args.target_os == 'win':
      download_from_google_storage(
          'chromium-browser-clang/rc',
          extract=False,
          sha_file='build/toolchain/win/rc/mac/rc.sha1')
  elif host_os == 'win':
    download_from_google_storage(
        'chromium-browser-clang/rc',
        extract=False,
        sha_file='build/toolchain/win/rc/win/rc.exe.sha1')

if __name__ == '__main__':
  exit(main())
