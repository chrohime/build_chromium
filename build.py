#!/usr/bin/env python3

import argparse
import os
import subprocess
import sys

from bootstrap import ROOT_DIR, add_depot_tools_to_path, current_os

def get_gn_config(args):
  args_gn = os.path.join(args.out_dir, 'args.gn')
  if not os.path.isabs(args_gn):
    args_gn = os.path.join(args.src_dir, args_gn)
  with open(args_gn, 'r') as f:
    content = f.read()
    return ('use_remoteexec = true' in content, 'goma.gn' in content)

def main():
  parser = argparse.ArgumentParser(description='Build Chromium')
  parser.add_argument('targets', nargs='*', default=[ 'views_examples' ],
                      help='The targets to build')
  parser.add_argument('--src-dir', default=os.path.join(ROOT_DIR, 'src'),
                      help='The path of src dir')
  parser.add_argument('-C', dest='out_dir', default='out/Component',
                      help='Which config to build')
  args, unknown_args = parser.parse_known_args()

  add_depot_tools_to_path(args.src_dir)

  # The python binary used for building is likely the downloaded binary in
  # depot_tools, which does not import modules installed in user's python
  # dir. Export the PYTHONPATH env so modules like pyyaml can be found.
  if current_os() == 'win':
    site_packages = []
    for path in sys.path:
      if path.endswith('site-packages'):
        site_packages.append(path)
    os.environ['PYTHONPATH'] = os.pathsep.join(site_packages)

  autoninja = 'autoninja.bat' if current_os() == 'win' else 'autoninja'
  ninja_args = [ autoninja,  '-C', args.out_dir ]

  use_reclient, use_goma = get_gn_config(args)
  if use_reclient or use_goma:
    ninja_args += [ '-j', '200' ]

  try:
    subprocess.check_call(ninja_args + unknown_args + args.targets,
                          cwd=args.src_dir)
  except KeyboardInterrupt:
    sys.exit(1)
  except subprocess.CalledProcessError as e:
    sys.exit(e.returncode)

if __name__ == '__main__':
  main()
