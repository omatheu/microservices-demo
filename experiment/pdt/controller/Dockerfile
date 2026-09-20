# syntax=docker/dockerfile:1.7

FROM python:3.12.11-alpine@sha256:efcdfa6a6b2fd2afb9c7dfa9a5b288a6f68338b5cfdebe6b637d986067d85757

RUN addgroup -S -g 10001 controller \
    && adduser -S -D -H -u 10001 -G controller controller

WORKDIR /controller
COPY experiment/pdt/controller/checkout_pdt_controller.py ./checkout_pdt_controller.py

USER 10001:10001
ENTRYPOINT ["python3", "/controller/checkout_pdt_controller.py"]
