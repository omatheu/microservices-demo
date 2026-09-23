# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Define a default value so it's not empty if the builder fails to provide it
ARG BUILDPLATFORM=linux/amd64

FROM --platform=$BUILDPLATFORM alpine:3.24.1@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b AS base

RUN apk upgrade --no-cache

FROM base AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apk add --no-cache g++ linux-headers python3 py3-pip

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

# get packages
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# The runtime does not install packages. Removing pip also removes its embedded
# build-tool SBOM, so scanners do not misclassify vendored tooling as runtime
# dependencies.
RUN pip uninstall --yes pip

FROM base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Enable Profiler
ENV ENABLE_PROFILER=1

RUN apk add --no-cache libstdc++ python3 \
    && addgroup -S -g 10001 app \
    && adduser -S -D -H -u 10001 -G app app

WORKDIR /email_server

# Grab the isolated dependency environment from the builder.
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

# Add the application
COPY . .

EXPOSE 8080
USER 10001:10001
ENTRYPOINT [ "python", "email_server.py" ]
