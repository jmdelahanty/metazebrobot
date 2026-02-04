#!/usr/bin/env bash
set -euo pipefail

REPO="/home/delahantyj@hhmi.org/gitrepos/metazebrobot"
cd "$REPO"

pixi run python -m metazebrobot.cli
