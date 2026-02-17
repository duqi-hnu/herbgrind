#!/usr/bin/env python3

import argparse
import subprocess
import re
import os
import sys
import shlex


parser = argparse.ArgumentParser(description="test for memory leaks in a process.")
parser.add_argument("basedir", nargs="?", default=os.getcwd(), help="The base directory to run the binary from.")
parser.add_argument("executable", help="The binary to test herbgrind on.")
parser.add_argument("--print-log", help="Print out the output of the herbgrind command run.\n",
                    default=False, const=True, action='store_const', dest='print_log')

args = parser.parse_args()

print("with executable {}".format(args.executable))

timeout_cmd = os.environ.get("HG_TIMEOUT_COMMAND", "timeout -t 4200 -m 1500000 --confess")
valgrind_cmd = os.environ.get("HG_VALGRIND_COMMAND")
if valgrind_cmd is None:
    herbgrind_dir = os.environ.get(
        "HERBGRIND_DIR",
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    )
    valgrind_path = os.path.join(
        herbgrind_dir, "valgrind", "herbgrind-install", "bin", "valgrind"
    )
    valgrind_cmd = "{} --tool=herbgrind --print-moves".format(
        shlex.quote(valgrind_path)
    )

command = "{} {} {}".format(timeout_cmd, valgrind_cmd, args.executable)
log = subprocess.Popen(command,
                       shell=True, executable="/bin/bash",
                       stderr=subprocess.PIPE,
                       cwd=args.basedir).communicate()[1]

if args.print_log:
    print(log)

svs_made = [];
svs_freed = [];
for line in log.decode("utf-8").splitlines():
    make_match = re.match("Making shadow value (0x[0-9A-Fa-f]*)", line)
    if make_match:
        svs_made.append(make_match.group(1))

    free_match = re.match("Cleaning up shadow value (0x[0-9A-Fa-f]*)", line)
    if free_match:
        svs_freed.append(free_match.group(1))

assert (set(svs_freed) <= set(svs_made))

svs_leaked = list(set(svs_made) - set(svs_freed))

print("{} shadow values leaked! ({} made, {} freed)\n".format(len(set(svs_leaked)),
                                                              len(set(svs_made)),
                                                              len(svs_freed)))
