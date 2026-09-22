// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// stagingcontract exercises the deployed checkout path without oracle inputs.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"regexp"
	"time"

	pb "github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice/genproto"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/proto"
)

const productID = "0PUK6V6EV0"

var identifierPattern = regexp.MustCompile(`^[A-Za-z0-9._-]+$`)

type cartClient interface {
	AddItem(context.Context, *pb.AddItemRequest, ...grpc.CallOption) (*pb.Empty, error)
	GetCart(context.Context, *pb.GetCartRequest, ...grpc.CallOption) (*pb.Cart, error)
	EmptyCart(context.Context, *pb.EmptyCartRequest, ...grpc.CallOption) (*pb.Empty, error)
}

type checkoutClient interface {
	PlaceOrder(context.Context, *pb.PlaceOrderRequest, ...grpc.CallOption) (*pb.PlaceOrderResponse, error)
}

type contractResult struct {
	ID         string         `json:"id"`
	Status     string         `json:"status"`
	Assertions []string       `json:"assertions"`
	Observed   map[string]any `json:"observed"`
	Failure    string         `json:"failure,omitempty"`
}

type report struct {
	SchemaVersion             string           `json:"schema_version"`
	Mechanism                 string           `json:"mechanism"`
	CandidateID               string           `json:"candidate_id"`
	Repetition                int              `json:"repetition"`
	StartedAt                 string           `json:"started_at"`
	FinishedAt                string           `json:"finished_at"`
	DurationMilliseconds      int64            `json:"duration_milliseconds"`
	OperationalSnapshotAccess bool             `json:"operational_snapshot_access"`
	ServicesUnderContract     []string         `json:"services_under_contract"`
	Cases                     []contractResult `json:"cases"`
	Passed                    int              `json:"passed"`
	Failed                    int              `json:"failed"`
	Decision                  string           `json:"decision"`
}

func request(userID string, card *pb.CreditCardInfo) *pb.PlaceOrderRequest {
	return &pb.PlaceOrderRequest{
		UserId:       userID,
		UserCurrency: "USD",
		Address: &pb.Address{
			StreetAddress: "1 Staging Contract Street",
			City:          "Test City",
			State:         "SP",
			Country:       "BR",
			ZipCode:       10101,
		},
		Email:      "staging-contract@example.invalid",
		CreditCard: card,
	}
}

func validCard(now time.Time) *pb.CreditCardInfo {
	return &pb.CreditCardInfo{
		CreditCardNumber:          "4111111111111111",
		CreditCardCvv:             123,
		CreditCardExpirationMonth: 12,
		CreditCardExpirationYear:  int32(now.Year() + 2),
	}
}

func expiredCard(now time.Time) *pb.CreditCardInfo {
	card := validCard(now)
	card.CreditCardExpirationMonth = 1
	card.CreditCardExpirationYear = int32(now.Year() - 1)
	return card
}

func cartMatches(cart *pb.Cart) bool {
	items := cart.GetItems()
	return len(items) == 1 && items[0].GetProductId() == productID && items[0].GetQuantity() == 1
}

func resetAndAdd(ctx context.Context, cart cartClient, userID string) error {
	if _, err := cart.EmptyCart(ctx, &pb.EmptyCartRequest{UserId: userID}); err != nil {
		return fmt.Errorf("reset cart: %w", err)
	}
	_, err := cart.AddItem(ctx, &pb.AddItemRequest{
		UserId: userID,
		Item:   &pb.CartItem{ProductId: productID, Quantity: 1},
	})
	if err != nil {
		return fmt.Errorf("add cart item: %w", err)
	}
	return nil
}

func failure(id string, assertions []string, stage string, err error) contractResult {
	observed := map[string]any{"failed_stage": stage}
	if err != nil {
		observed["grpc_code"] = status.Code(err).String()
	}
	return contractResult{
		ID:         id,
		Status:     "FAIL",
		Assertions: assertions,
		Observed:   observed,
		Failure:    stage,
	}
}

func happyPath(ctx context.Context, cart cartClient, checkout checkoutClient, userID string, now time.Time) contractResult {
	assertions := []string{
		"cartservice stores the selected item",
		"checkoutservice returns an order and tracking identifier",
		"order preserves item, quantity, currency and address",
		"successful checkout empties the cart",
	}
	if err := resetAndAdd(ctx, cart, userID); err != nil {
		return failure("happy-path-order", assertions, "prepare-cart", err)
	}
	before, err := cart.GetCart(ctx, &pb.GetCartRequest{UserId: userID})
	if err != nil || !cartMatches(before) {
		return failure("happy-path-order", assertions, "verify-cart-before-order", err)
	}
	response, err := checkout.PlaceOrder(ctx, request(userID, validCard(now)))
	if err != nil {
		return failure("happy-path-order", assertions, "place-order", err)
	}
	order := response.GetOrder()
	validOrder := order.GetOrderId() != "" &&
		order.GetShippingTrackingId() != "" &&
		order.GetShippingCost().GetCurrencyCode() == "USD" &&
		proto.Equal(order.GetShippingAddress(), request(userID, validCard(now)).GetAddress()) &&
		len(order.GetItems()) == 1 &&
		order.GetItems()[0].GetItem().GetProductId() == productID &&
		order.GetItems()[0].GetItem().GetQuantity() == 1 &&
		order.GetItems()[0].GetCost().GetCurrencyCode() == "USD"
	if !validOrder {
		return failure("happy-path-order", assertions, "verify-order-contract", nil)
	}
	after, err := cart.GetCart(ctx, &pb.GetCartRequest{UserId: userID})
	if err != nil || len(after.GetItems()) != 0 {
		return failure("happy-path-order", assertions, "verify-cart-empty", err)
	}
	return contractResult{
		ID:         "happy-path-order",
		Status:     "PASS",
		Assertions: assertions,
		Observed: map[string]any{
			"cart_items_before": 1,
			"cart_items_after":  0,
			"order_id_present":  true,
			"tracking_present":  true,
			"item_count":        1,
			"currency":          "USD",
		},
	}
}

func paymentFailure(ctx context.Context, cart cartClient, checkout checkoutClient, userID string, now time.Time) contractResult {
	assertions := []string{
		"expired payment is rejected by the real payment path",
		"checkoutservice propagates a non-success gRPC status",
		"failed payment preserves the cart",
		"probe cleanup removes its own test cart",
	}
	if err := resetAndAdd(ctx, cart, userID); err != nil {
		return failure("payment-failure-preserves-cart", assertions, "prepare-cart", err)
	}
	response, callErr := checkout.PlaceOrder(ctx, request(userID, expiredCard(now)))
	if callErr == nil || response != nil || status.Code(callErr) != codes.Internal {
		_ = cleanupCart(ctx, cart, userID)
		return failure("payment-failure-preserves-cart", assertions, "expected-payment-rejection", callErr)
	}
	after, err := cart.GetCart(ctx, &pb.GetCartRequest{UserId: userID})
	if err != nil || !cartMatches(after) {
		_ = cleanupCart(ctx, cart, userID)
		return failure("payment-failure-preserves-cart", assertions, "verify-cart-retained", err)
	}
	if err := cleanupCart(ctx, cart, userID); err != nil {
		return failure("payment-failure-preserves-cart", assertions, "cleanup-test-cart", err)
	}
	return contractResult{
		ID:         "payment-failure-preserves-cart",
		Status:     "PASS",
		Assertions: assertions,
		Observed: map[string]any{
			"grpc_code":           codes.Internal.String(),
			"cart_items_retained": 1,
			"cleanup_completed":   true,
		},
	}
}

func cleanupCart(ctx context.Context, cart cartClient, userID string) error {
	_, err := cart.EmptyCart(ctx, &pb.EmptyCartRequest{UserId: userID})
	return err
}

func execute(ctx context.Context, cart cartClient, checkout checkoutClient, candidateID string, repetition int, now time.Time) report {
	started := time.Now().UTC()
	prefix := fmt.Sprintf("staging-contract-%s-r%d", candidateID, repetition)
	cases := []contractResult{
		happyPath(ctx, cart, checkout, prefix+"-success", now),
		paymentFailure(ctx, cart, checkout, prefix+"-payment-failure", now),
	}
	passed := 0
	for _, result := range cases {
		if result.Status == "PASS" {
			passed++
		}
	}
	finished := time.Now().UTC()
	decision := "FAIL"
	if passed == len(cases) {
		decision = "PASS"
	}
	return report{
		SchemaVersion:             "1.0.0",
		Mechanism:                 "traditional-staging-real-service-contracts",
		CandidateID:               candidateID,
		Repetition:                repetition,
		StartedAt:                 started.Format(time.RFC3339Nano),
		FinishedAt:                finished.Format(time.RFC3339Nano),
		DurationMilliseconds:      finished.Sub(started).Milliseconds(),
		OperationalSnapshotAccess: false,
		ServicesUnderContract: []string{
			"cartservice",
			"checkoutservice",
			"currencyservice",
			"paymentservice",
			"productcatalogservice",
			"shippingservice",
		},
		Cases:    cases,
		Passed:   passed,
		Failed:   len(cases) - passed,
		Decision: decision,
	}
}

func writeReport(path string, value report) error {
	if path == "" {
		return errors.New("output path is required")
	}
	stream, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
	if err != nil {
		return err
	}
	defer stream.Close()
	encoder := json.NewEncoder(stream)
	encoder.SetIndent("", "  ")
	return encoder.Encode(value)
}

func main() {
	var cartAddress string
	var checkoutAddress string
	var candidateID string
	var output string
	var repetition int
	var timeout time.Duration
	flag.StringVar(&cartAddress, "cart-address", "127.0.0.1:17070", "cartservice gRPC address")
	flag.StringVar(&checkoutAddress, "checkout-address", "127.0.0.1:15050", "checkoutservice gRPC address")
	flag.StringVar(&candidateID, "candidate-id", "", "opaque candidate identifier")
	flag.IntVar(&repetition, "repetition", 0, "positive repetition number")
	flag.StringVar(&output, "output", "", "new JSON output path")
	flag.DurationVar(&timeout, "timeout", 90*time.Second, "overall contract timeout")
	flag.Parse()

	if !identifierPattern.MatchString(candidateID) || repetition <= 0 || timeout <= 0 {
		fmt.Fprintln(os.Stderr, "candidate-id, repetition or timeout is invalid")
		os.Exit(2)
	}
	cartConnection, err := grpc.NewClient(cartAddress, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		fmt.Fprintln(os.Stderr, "create cartservice client:", err)
		os.Exit(2)
	}
	defer cartConnection.Close()
	checkoutConnection, err := grpc.NewClient(checkoutAddress, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		fmt.Fprintln(os.Stderr, "create checkoutservice client:", err)
		os.Exit(2)
	}
	defer checkoutConnection.Close()

	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	result := execute(
		ctx,
		pb.NewCartServiceClient(cartConnection),
		pb.NewCheckoutServiceClient(checkoutConnection),
		candidateID,
		repetition,
		time.Now().UTC(),
	)
	if err := writeReport(output, result); err != nil {
		fmt.Fprintln(os.Stderr, "write contract report:", err)
		os.Exit(2)
	}
	if result.Decision != "PASS" {
		os.Exit(1)
	}
}
