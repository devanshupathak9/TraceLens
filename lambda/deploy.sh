#!/usr/bin/env bash
# Package lambda_function.py + psycopg2 and push it to an existing AWS Lambda.
#
#   ./deploy.sh                          # function name from $LAMBDA_FUNCTION_NAME
#   ./deploy.sh tracelens-writer         # or pass it explicitly
#   ARCH=arm64 ./deploy.sh my-function   # for a Graviton (arm64) function
#
# Requires the AWS CLI, configured (`aws configure`) with permission to call
# lambda:UpdateFunctionCode.
set -euo pipefail
cd "$(dirname "$0")"

FUNCTION_NAME="${1:-${LAMBDA_FUNCTION_NAME:-}}"
if [ -z "$FUNCTION_NAME" ]; then
    echo "error: no function name. Pass it as an argument or set LAMBDA_FUNCTION_NAME." >&2
    echo "       list yours with: aws lambda list-functions --query 'Functions[].FunctionName'" >&2
    exit 1
fi

# psycopg2 is a compiled extension, so the wheel must match the Lambda's
# platform — NOT the machine building the zip. Building on a Mac without this
# gives a macOS wheel and the function fails at import with
# "No module named 'psycopg2._psycopg'".
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

cp lambda_function.py build/

( cd build && zip -qr ../lambda.zip . )
echo "==> built lambda.zip ($(du -h lambda.zip | cut -f1))"

echo "==> updating $FUNCTION_NAME"
aws lambda update-function-code \
    --function-name "$FUNCTION_NAME" \
    --zip-file fileb://lambda.zip \
    --output table \
    --query '{Function:FunctionName,Size:CodeSize,Updated:LastModified,Status:LastUpdateStatus}'

# update-function-code returns before the new code is live; without this wait a
# test invoke can still hit the previous version.
echo "==> waiting for the update to finish"
aws lambda wait function-updated --function-name "$FUNCTION_NAME"
echo "==> done. Tail logs with:"
echo "    aws logs tail /aws/lambda/$FUNCTION_NAME --follow"
