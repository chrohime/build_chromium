#!/usr/bin/env python3

import argparse
import os
import subprocess
import sys

from bootstrap import ROOT_DIR, add_depot_tools_to_path, current_cpu, current_os

def gn_gen(src_dir, out_dir, args):
  joined_args = ' '.join(args)
  gn_bin = 'gn.bat' if current_os() == 'win' else 'gn'
  process = subprocess.Popen([ gn_bin, 'gen', out_dir, f'--args={joined_args}'],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, cwd=src_dir)
  for line in process.stdout:
    if '.gclient_entries missing' not in line:
      print(line.strip())
  process.wait()

def main():
  parser = argparse.ArgumentParser(description='Generate GN build config')
  parser.add_argument('--target-cpu', default=current_cpu(),
                      help='Target CPU architecture')
  parser.add_argument('--target-os', default=current_os(),
                      help='Target operating system (win, mac, or linux)')
  parser.add_argument('--src-dir', default=os.path.join(ROOT_DIR, 'src'),
                      help='The path of src dir')
  parser.add_argument('--arg', action='append', default=[],
                      help='Pass arguments to GN')
  parser.add_argument('--reclient', action='store_true', default=False,
                      help='Build with reclient')
  parser.add_argument('--config', choices=[ 'Component', 'Release', 'Debug' ],
                      help='Which config to generate')
  parser.add_argument('--custom-config', help='Generate custom config')
  args = parser.parse_args()

  add_depot_tools_to_path(args.src_dir)

  args.arg += [
      f'target_cpu="{args.target_cpu}"',
      f'target_os="{args.target_os}"',
  ]
  if not args.custom_config:
    args.arg += [ 'enable_nacl=false' ]
  if args.reclient:
    args.arg += [ 'use_remoteexec=true' ]

  generate_all = not args.config and not args.custom_config

  if generate_all or args.config == 'Component':
    gn_gen(args.src_dir, 'out/Component', args.arg + [
        'is_component_build=true',
        'is_debug=false',
    ])
  if generate_all or args.config == 'Release':
    gn_gen(args.src_dir, 'out/Release', args.arg + [
        'is_component_build=false',
        'is_debug=false',
        'chrome_pgo_phase=0',
        'is_official_build=true',
    ])
  if generate_all or args.config == 'Debug':
    gn_gen(args.src_dir, 'out/Debug', args.arg + [
        'is_component_build=true',
        'is_debug=true',
    ])
  if args.custom_config:
    gn_gen(args.src_dir, f'out/{args.custom_config}', args.arg)

if __name__ == '__main__':
  main()
