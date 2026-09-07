#!/usr/bin/env bash
# Link a skill from this repo into a Claude Code skills directory.
#
#   ./install.sh trading-journal              # into ./.claude/skills (cwd's project)
#   ./install.sh trading-journal --global     # into ~/.claude/skills (every project)
#   ./install.sh trading-journal ~/work/repo  # into that project's .claude/skills
#
# Symlinks rather than copies, so `git pull` here updates every project at once.
# A copy would leave each project on whatever revision it was installed at, and
# nothing would say which.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $# -lt 1 ]]; then
    echo "usage: $0 <skill> [--global | <project-dir>]" >&2
    echo >&2
    echo "available skills:" >&2
    for d in "$repo"/*/; do
        [[ -f "$d/SKILL.md" ]] && echo "  $(basename "$d")" >&2
    done
    exit 2
fi

skill="$1"
src="$repo/$skill"
[[ -f "$src/SKILL.md" ]] || { echo "no such skill: $skill (no $src/SKILL.md)" >&2; exit 1; }

case "${2-}" in
    --global) dest="$HOME/.claude/skills" ;;
    "")       dest="$PWD/.claude/skills" ;;
    *)        dest="${2%/}/.claude/skills" ;;
esac

mkdir -p "$dest"
link="$dest/$skill"

if [[ -e "$link" || -L "$link" ]]; then
    if [[ -L "$link" && "$(readlink "$link")" == "$src" ]]; then
        echo "already linked: $link -> $src"
        exit 0
    fi
    # Never clobber in silence: a real directory here is somebody's edited copy,
    # and it is the one thing this script cannot put back.
    echo "refusing to overwrite $link" >&2
    echo "  it is $( [[ -L $link ]] && echo "a symlink to $(readlink "$link")" || echo "a real directory" )" >&2
    echo "  remove it yourself if you meant to replace it" >&2
    exit 1
fi

ln -s "$src" "$link"
echo "linked $link -> $src"
