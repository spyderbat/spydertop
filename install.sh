#!/bin/sh

set -ex

PIP=${PIP_COMMAND:-pip}

if [ ! -x "$(command -v $PIP)" ]; then
    cat << EOF
Command $PIP not found. Please install it or set the PIP_COMMAND
environment variable to a command which does exist.
EOF
    exit 1
fi

git clone https://github.com/spyderbat/api_examples.git
cd api_examples/python
$PIP install .

cd ../../

$PIP install .

set +ex
