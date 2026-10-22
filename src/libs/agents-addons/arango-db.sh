#!/bin/bash

docker run -d \
  --rm \
  --name arango-test \
  -e ARANGO_ROOT_PASSWORD=root \
  --net=host \
  arangodb:3.11
