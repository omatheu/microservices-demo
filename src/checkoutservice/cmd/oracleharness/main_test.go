// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0

package main

import (
	"context"
	"encoding/json"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	pb "github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice/genproto"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/test/bufconn"
)

type fakeCheckout struct {
	pb.UnimplementedCheckoutServiceServer
}

func (fakeCheckout) PlaceOrder(context.Context, *pb.PlaceOrderRequest) (*pb.PlaceOrderResponse, error) {
	return &pb.PlaceOrderResponse{Order: &pb.OrderResult{OrderId: "fake-order"}}, nil
}

func harnessWithFakeCheckout(t *testing.T) *oracleHarness {
	t.Helper()
	listener := bufconn.Listen(1024 * 1024)
	server := grpc.NewServer()
	pb.RegisterCheckoutServiceServer(server, fakeCheckout{})
	go func() { _ = server.Serve(listener) }()
	connection, err := grpc.NewClient(
		"passthrough:///fake-checkout",
		grpc.WithContextDialer(func(ctx context.Context, _ string) (net.Conn, error) {
			return listener.DialContext(ctx)
		}),
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		t.Fatalf("create fake checkout client: %v", err)
	}
	t.Cleanup(func() {
		_ = connection.Close()
		server.Stop()
		_ = listener.Close()
	})
	return &oracleHarness{
		checkoutClient: pb.NewCheckoutServiceClient(connection),
		carts:          make(map[string][]*pb.CartItem),
		cartCleared:    make(map[string]bool),
	}
}

func TestLuhnValidation(t *testing.T) {
	t.Parallel()
	for _, value := range []string{"4111111111111111", "5555555555554444", "378282246310005"} {
		if !luhnValid(value) {
			t.Errorf("expected %q to satisfy Luhn", value)
		}
	}
	for _, value := range []string{"1234567890", "4111111111111112", "not-a-card"} {
		if luhnValid(value) {
			t.Errorf("expected %q to fail Luhn", value)
		}
	}
}

func TestCardCasesMatchOracleContract(t *testing.T) {
	t.Parallel()
	now := time.Date(2026, time.September, 20, 0, 0, 0, 0, time.UTC)
	if err := validateCard(cardForCase("valid", now), now); err != nil {
		t.Fatalf("valid card rejected: %v", err)
	}
	for _, cardCase := range []string{"unsupported-card", "expired-card", "invalid-number"} {
		if err := validateCard(cardForCase(cardCase, now), now); err == nil {
			t.Errorf("%s should be rejected", cardCase)
		}
	}
}

func TestNormalizeExerciseRejectsUnboundedInputs(t *testing.T) {
	t.Parallel()
	request := exerciseRequest{
		Currency: "USD",
		Items:    []itemInput{{ProductID: "sku-1", Quantity: 4}},
	}
	if err := normalizeExercise(&request); err == nil {
		t.Fatal("quantity above the declared oracle matrix was accepted")
	}

	request = exerciseRequest{Currency: "BTC"}
	if err := normalizeExercise(&request); err == nil {
		t.Fatal("currency outside the declared oracle matrix was accepted")
	}
}

func TestIdentityConversionPreservesValueAndChangesCurrency(t *testing.T) {
	t.Parallel()
	result := identityConversion(&pb.CurrencyConversionRequest{
		From:   &pb.Money{CurrencyCode: "USD", Units: 3, Nanos: 250_000_000},
		ToCode: "EUR",
	})
	if result.GetCurrencyCode() != "EUR" || result.GetUnits() != 3 || result.GetNanos() != 250_000_000 {
		t.Fatalf("unexpected identity conversion: %v", result)
	}
}

func TestLoadOrderEndpointAllowsConcurrentProfileDriver(t *testing.T) {
	t.Parallel()
	harness := harnessWithFakeCheckout(t)
	request := httptest.NewRequest(
		http.MethodPost,
		"/load-order",
		strings.NewReader(`{"user_id":"load-user","currency":"USD","items":[{"product_id":"sku-1","quantity":1}]}`),
	)
	response := httptest.NewRecorder()

	harness.loadOrderHandler(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("HTTP status = %d, body = %s", response.Code, response.Body.String())
	}
	var result loadOrderResult
	if err := json.Unmarshal(response.Body.Bytes(), &result); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if result.GRPCCode != "OK" {
		t.Fatalf("gRPC code = %s, error = %s", result.GRPCCode, result.Error)
	}
	if harness.counters.LoadOrders != 1 || harness.counters.LoadSuccesses != 1 {
		t.Fatalf("unexpected counters: %+v", harness.counters)
	}
}

func TestLoadTailFaultAddsBoundedDelay(t *testing.T) {
	t.Parallel()
	harness := &oracleHarness{
		carts:       make(map[string][]*pb.CartItem),
		cartCleared: make(map[string]bool),
		loadFault:   "payment-tail-latency",
		loadDelay:   5 * time.Millisecond,
	}
	request := &pb.ChargeRequest{
		Amount:     &pb.Money{CurrencyCode: "USD", Units: 1},
		CreditCard: cardForCase("valid", time.Now().UTC()),
	}
	started := time.Now()

	if _, err := harness.Charge(context.Background(), request); err != nil {
		t.Fatalf("charge failed: %v", err)
	}

	if time.Since(started) < 5*time.Millisecond {
		t.Fatal("configured payment tail latency was not applied")
	}
}
