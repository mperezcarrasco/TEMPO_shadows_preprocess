#!/usr/bin/env bash

# Some distro requires that the absolute path is given when invoking lspci
# e.g. /sbin/lspci if the user is not root.
echo 'Looking for GPUs (ETA: 10 seconds)'
gpu=$(lspci | grep -i '.* vga .* nvidia .*')
shopt -s nocasematch
if [[ $gpu == *' nvidia '* ]]; then
  echo GPU found
  docker run -it --rm \
    --privileged=true \
    --mount "type=bind,src=$(pwd),dst=/tmp/" \
    --workdir /tmp/ \
    --gpus all \
    --ipc=host \
    --ulimit memlock=-1 \
    --ulimit stack=67108864 \
    --name methane \
    -p 8889:8889 \
    methane bash
else
  docker run -it --rm \
    --privileged=true \
    --mount "type=bind,src=$(pwd),dst=/tmp/" \
    --workdir /tmp/ \
    -p 8889:8889 \
    --name methane \
    methane bash
fi
