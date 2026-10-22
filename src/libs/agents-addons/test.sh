#!/bin/bash

export ARANGO_ENDPOINT="http://127.0.0.1:8529"
export ARANGO_DB_NAME="_system"
export ARANGO_USERNAME="root"
export ARANGO_PASSWORD="root"

pytest -rs
pytest arango_test.py