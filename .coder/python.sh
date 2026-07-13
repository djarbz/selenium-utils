#!/usr/bin/env bash
# Exit immediately if a command exits with a non-zero status
set -euo pipefail

echo "🚀 Starting Python environment setup for selenium-utils..."

# 1. Navigate to the repository root
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"
echo "📂 Working directory set to: $REPO_ROOT"

# 2. Install or update 'uv'
if ! command -v uv &>/dev/null; then
  echo "⬇️ 'uv' not found. Installing..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
else
  echo "🔄 'uv' is already installed. Checking for updates..."
  uv self update
fi

# 3. Define the targeted stable Python version
# Since this is a library, we don't have a Dockerfile. We will target
# 3.14 to match the STABLE_PYTHON environment in your GitHub Actions.
PYTHON_VERSION="3.14"
echo "🎯 Targeting stable Python version: $PYTHON_VERSION"

# 4. Install the specific Python version
echo "📦 Ensuring Python $PYTHON_VERSION is installed..."
uv python install "$PYTHON_VERSION"

# 5. Create or update the virtual environment
if [[ ! -d ".venv" ]]; then
  echo "🌱 Creating new virtual environment (.venv)..."
  uv venv --python "$PYTHON_VERSION"
else
  echo "♻️ Virtual environment exists. Ensuring it matches Python $PYTHON_VERSION..."
  uv venv --python "$PYTHON_VERSION" --allow-existing
fi

# 6. Install dependencies from pyproject.toml and dev tools
if [[ -f "pyproject.toml" ]]; then
  echo "📚 Installing package dependencies from pyproject.toml..."
  # The '-e .' flag installs the current directory in editable mode,
  # automatically parsing pyproject.toml for dependencies.
  # We also append our local development tools here.
  uv pip install -e . pylint pre-commit
else
  echo "❌ Error: pyproject.toml not found! Are you in the right directory?"
  exit 1
fi

# 7. Initialize pre-commit hooks
echo "🔗 Installing pre-commit hooks to local git repo..."
# Run pre-commit using the active virtual environment
.venv/bin/pre-commit install

echo "✅ Python environment setup complete!"
echo "💡 Reminder: To activate the virtual environment manually, run 'source .venv/bin/activate'"
echo ""
echo "The following packages are outdated and might need to be updated:"
uv pip list --outdated
