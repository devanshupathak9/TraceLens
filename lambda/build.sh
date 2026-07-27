#!/usr/bin/env bash
# Build lambda.zip for manual upload through the AWS console.
#
#   ./build.sh                # x86_64 / python3.12
#   ARCH=arm64 ./build.sh     # for a Graviton function
#
# No AWS credentials needed — this only packages. Upload the result at
# Lambda → your function → Code → Upload from → .zip file.
set -euo pipefail
cd "$(dirname "$0")"

# psycopg2 is a compiled extension, so the wheel must match the Lambda's
# platform — NOT the Mac building the zip. Without this you get a macOS wheel
# and the function fails at import with "No module named 'psycopg2._psycopg'".
ARCH="${ARCH:-x86_64}"
case "$ARCH" in
    x86_64) PLATFORM="manylinux2014_x86_64" ;;
    arm64)  PLATFORM="manylinux2014_aarch64" ;;
    *) echo "error: ARCH must be x86_64 or arm64 (got '$ARCH')." >&2; exit 1 ;;
esac

# Must match the function's configured runtime, or the wheel's ABI tag won't load.
PY_VERSION="${PY_VERSION:-3.12}"

echo "==> packaging for $ARCH / python$PY_VERSION"
rm -rf build lambda.zip
mkdir -p build

pip install \
    --quiet \
    --target build \
    --platform "$PLATFORM" \
    --python-version "$PY_VERSION" \
    --only-binary=:all: \
    -r requirements.txt

# Handler file must sit at the zip root for lambda_function.lambda_handler to resolve.
cp lambda_function.py build/

( cd build && zip -qr ../lambda.zip . )

echo "==> built $(pwd)/lambda.zip ($(du -h lambda.zip | cut -f1))"
echo
echo "Next, in the AWS console:"
echo "  1. Lambda → tracelens-worker → Code → Upload from → .zip file → pick lambda.zip → Save"
echo "  2. Runtime settings → Handler must be: lambda_function.lambda_handler"
echo "  3. Configuration → Environment variables → DATABASE_URL (Supabase session pooler, plain postgresql://)"
