#!/bin/bash
# One-time Mac setup for Izaiah's production machine. Paste into Terminal:
#   curl -fsSL https://raw.githubusercontent.com/izaiahwest/my-ai-project/claude/tiktok-shop-affiliate-system-3srjzv/tools/mac_setup.sh | bash
# (or run it from the repo after cloning). Safe to run more than once.
set -e
if ! command -v brew >/dev/null; then
  echo "Installing Homebrew (it will ask for your Mac password)..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv)"
fi
brew install ffmpeg yt-dlp python git
python3 -m pip install --user --upgrade faster-whisper "av<16" openpyxl
if [ ! -d "$HOME/My-ai-project" ]; then
  git clone -b claude/tiktok-shop-affiliate-system-3srjzv https://github.com/izaiahwest/my-ai-project.git "$HOME/My-ai-project"
fi
mkdir -p "$HOME/My-ai-project/raw"
echo
echo "Done. Your footage drop folder is: $HOME/My-ai-project/raw"
echo "Next: open the Claude desktop app -> Code -> open the folder My-ai-project."
