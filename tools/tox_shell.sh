#!/bin/bash

# This shell script will run an interactive Python shell in any selected tox environment.

TOX_ENV=""
RECREATE=0
declare -a PYARGS

while [[ $# -gt 0 ]]; do
  case $1 in
    -e|--environment)
      TOX_ENV="$2"
      shift 2
      ;;
    -r)
      RECREATE=1
      shift
      ;;
    -h|--help)
      echo "Usage: $0 [-e|--environment env] [-r] [arguments]"
      echo "Run an interactive Python shell in any selected tox environment."
      echo "  -e env       Select an environment."
      echo "  -r           Regenerate the environment, even if it's already there."
      echo "  [arguments]  Further arguments are passed to the Python shell."
      exit
      ;;
    *)
      PYARGS+=("$1")
      shift
      ;;
  esac
done

if [[ $TOX_ENV == "" ]]; then
  ALL_ENVS=$(tox -l)
  TOX_ENV="${ALL_ENVS[0]}"
fi

TOOLS_DIR=$(dirname "$(pwd)/${0}")
PACKAGE_ROOT=$(dirname "$TOOLS_DIR")
ENV_DIR="${PACKAGE_ROOT}/.tox/$TOX_ENV"

if [[ (! -d $ENV_DIR) || ( $RECREATE == 1 ) ]]; then
  echo "Creating $ENV_DIR"
  tox -r -e "$TOX_ENV" --notest || exit 1
fi

# shellcheck source=/dev/null
source "$ENV_DIR/bin/activate"
"$ENV_DIR"/bin/python "${PYARGS[@]}"
