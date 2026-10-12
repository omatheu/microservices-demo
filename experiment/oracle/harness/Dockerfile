# syntax=docker/dockerfile:1.7

ARG BUILDPLATFORM=linux/amd64
ARG TARGETOS=linux
ARG TARGETARCH=amd64

FROM --platform=$BUILDPLATFORM golang:1.27.2-alpine@sha256:f92b6ef800e499660581efdabdf25d9d817a9d124eaf900924f0504e7e27e12d AS builder

ARG TARGETOS
ARG TARGETARCH
WORKDIR /workspace/src/checkoutservice

COPY src/checkoutservice/go.mod src/checkoutservice/go.sum ./
RUN go mod download

COPY src/checkoutservice/genproto ./genproto
COPY src/checkoutservice/cmd/oracleharness ./cmd/oracleharness

RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} \
    go build -trimpath -ldflags="-s -w" -o /oracleharness ./cmd/oracleharness

FROM gcr.io/distroless/static@sha256:58133991db06659feaabe0f4e97a35cebf15ef4ea08f8a4c6d2ee5f75e4aa6a0

COPY --from=builder /oracleharness /oracleharness

EXPOSE 5051 8080
USER 65532:65532
ENTRYPOINT ["/oracleharness"]
