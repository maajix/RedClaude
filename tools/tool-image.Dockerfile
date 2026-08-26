# The image the registered offline tools live in ($RK_TOOL_IMAGE).
#
# `offline_tools.executable` names two absolute paths and this file exists to
# make both of them true: `/usr/local/bin/python3`, which every analyser this
# harness ships runs under, and `/usr/bin/jq`, which is the one registered tool
# that is not one of ours. Nothing else belongs here. The analyser itself is
# mounted read-only at run time under the hash on the row, so an image that
# carried a copy would only be a second answer to a question the row settles.
#
#   docker build -f tools/tool-image.Dockerfile -t rk2tools:latest .
#
# Never pulled implicitly: `rk tool run` refuses an image it cannot find rather
# than fetching one, so building this is an operator's deliberate act.
FROM python:3.14-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends jq \
 && rm -rf /var/lib/apt/lists/*
