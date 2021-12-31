#!/bin/bash
coverage run --source='.' docker_monitor_test.py && coverage report && coverage xml
