# syntax=docker/dockerfile:1.7

FROM python:3.12.14-alpine3.24@sha256:c4634f578a412db396771b61b064c6e546c9d6414c7fb5b1b05d5871f1885f7b

RUN addgroup -S -g 10001 controller \
    && adduser -S -D -H -u 10001 -G controller controller

WORKDIR /controller
COPY experiment/pdt/controller/checkout_pdt_controller.py ./checkout_pdt_controller.py

USER 10001:10001
ENTRYPOINT ["python3", "/controller/checkout_pdt_controller.py"]
