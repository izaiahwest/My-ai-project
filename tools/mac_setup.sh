#!/bin/bash
# One-time Mac setup for Izaiah's production machine. No password needed.
# Installs Miniforge (conda-forge) into ~/miniforge3, then ffmpeg, yt-dlp,
# Python 3.12, faster-whisper and openpyxl into it. Nothing outside your home folder.
#   curl -fsSL https://raw.githubusercontent.com/izaiahwest/my-ai-project/claude/tiktok-shop-affiliate-system-3srjzv/tools/mac_setup.sh | bash
# (or run it from the repo after cloning). Safe to run more than once.
# Tools live in ~/miniforge3/bin; our scripts call them by that path.
set -e
MF="$HOME/miniforge3"
if [ ! -x "$MF/bin/conda" ]; then
  echo "Installing Miniforge into $MF ..."
  TMP="$(mktemp -d)"
  curl -fsSL -o "$TMP/Miniforge3.sh" "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-MacOSX-$(uname -m).sh"
  bash "$TMP/Miniforge3.sh" -b -p "$MF"
  rm -rf "$TMP"
fi
"$MF/bin/mamba" install -y -n base -c conda-forge python=3.12 ffmpeg yt-dlp openpyxl pip
"$MF/bin/python" -m pip install --upgrade faster-whisper "av<16"
if [ ! -d "$HOME/My-ai-project" ]; then
  git clone -b claude/tiktok-shop-affiliate-system-3srjzv https://github.com/izaiahwest/my-ai-project.git "$HOME/My-ai-project"
fi
mkdir -p "$HOME/My-ai-project/raw"
echo
echo "Done. Your footage drop folder is: $HOME/My-ai-project/raw"
echo "Next: open the Claude desktop app -> Code -> open the folder My-ai-project."
