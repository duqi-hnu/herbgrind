#!/usr/bin/env bash

source "$(dirname "$0")/paths.sh"

if ! make -C "$HERBGRIND_DIR" > compile.log.txt;
then
    exit $?
fi

RUN_ROOT="$SPEC_DIR/benchspec/CPU2006/435.gromacs/run"
if [ -n "${HG_GROMACS_RUN_DIR:-}" ]; then
    GROMACS_RUN_DIR="$HG_GROMACS_RUN_DIR"
else
    run_dirs=("$RUN_ROOT"/run_base_test_*)
    GROMACS_RUN_DIR="${run_dirs[0]}"
fi

if [ "$GROMACS_RUN_DIR" = "$RUN_ROOT/run_base_test_*" ]; then
    echo "Could not find a SPEC gromacs run directory under $RUN_ROOT" >&2
    exit 1
fi

if [ -n "${HG_GROMACS_BIN:-}" ]; then
    GROMACS_BIN="$HG_GROMACS_BIN"
else
    gromacs_bins=("$GROMACS_RUN_DIR"/gromacs_base.*)
    if [ "${gromacs_bins[0]}" = "$GROMACS_RUN_DIR/gromacs_base.*" ]; then
        echo "Could not find gromacs_base.* in $GROMACS_RUN_DIR" >&2
        exit 1
    fi
    GROMACS_BIN="./$(basename "${gromacs_bins[0]}")"
fi

if [[ "$GROMACS_BIN" != ./* ]]; then
    GROMACS_BIN="./$GROMACS_BIN"
fi

cd "$GROMACS_RUN_DIR"
(timeout -t 4200 -m 15000000 --confess "$HERBGRIND_DIR"/valgrind/herbgrind-install/bin/valgrind --tool=herbgrind --print-counts --print-moves "$GROMACS_BIN" -silent -deffnm gromacs -nice 0) &> log.txt
NUM_ALLOCED=$(grep -c "Making shadow value" log.txt)
NUM_FREED=$(grep -c "Cleaning up shadow value" log.txt)
if [ "$NUM_ALLOCED" -ne "$NUM_FREED" ]
then
    (( NUM_LEAKED = NUM_ALLOCED - NUM_FREED ))
    echo "Leaked " $NUM_LEAKED " shadow values."
fi
