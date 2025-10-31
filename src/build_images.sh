#!/bin/bash

pushd agents-executor

docker build . -t 35.223.239.192:31280/agents/executor:latest
docker push 35.223.239.192:31280/agents/executor:latest


popd

pushd agents-job-scouter

docker build . -t 35.223.239.192:31280/agents/scouter:latest
docker push 35.223.239.192:31280/agents/scouter:latest

popd


pushd db

docker build . -t 35.223.239.192:31280/agents/db:latest
docker push 35.223.239.192:31280/agents/db:latest


popd

pushd deployer

docker build . -t 35.223.239.192:31280/agents/deployer:latest
docker push 35.223.239.192:31280/agents/deployer:latest

popd