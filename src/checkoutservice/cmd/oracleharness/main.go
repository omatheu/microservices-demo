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

// oracleharness is an independent, post-decision test dependency for the TCC
// experiment. It must never participate in staging or PDT decisions. It
// provides deterministic gRPC doubles, optional candidate/reference proxies,
// controlled faults, and an HTTP endpoint that exercises a sealed checkout
// artifact while recording its externally visible side effects.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"slices"
	"strings"
	"sync"
	"time"

	pb "github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice/genproto"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/health"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"
)

const (
	defaultGRPCPort = "5051"
	defaultHTTPPort = "8080"
	maximumBodySize = 1 << 20
)

type itemInput struct {
	ProductID string `json:"product_id"`
	Quantity  int32  `json:"quantity"`
}

type exerciseRequest struct {
	UserID       string      `json:"user_id"`
	Currency     string      `json:"currency"`
	Items        []itemInput `json:"items"`
	Fault        string      `json:"fault"`
	CardCase     string      `json:"card_case"`
	TimeoutMS    int         `json:"timeout_ms"`
	ExpectedCase string      `json:"expected_case,omitempty"`
}

type moneyView struct {
	CurrencyCode string `json:"currency_code"`
	Units        int64  `json:"units"`
	Nanos        int32  `json:"nanos"`
}

type event struct {
	Sequence int       `json:"sequence"`
	Name     string    `json:"name"`
	At       time.Time `json:"at"`
}

type conversionObservation struct {
	From      moneyView `json:"from"`
	To        string    `json:"to"`
	Actual    moneyView `json:"actual"`
	Reference moneyView `json:"reference"`
}

type exerciseResult struct {
	SchemaVersion      string                  `json:"schema_version"`
	UserID             string                  `json:"user_id"`
	ExpectedCase       string                  `json:"expected_case,omitempty"`
	Input              exerciseRequest         `json:"input"`
	GRPCCode           string                  `json:"grpc_code"`
	Error              string                  `json:"error,omitempty"`
	Response           json.RawMessage         `json:"response,omitempty"`
	Events             []event                 `json:"events"`
	Charges            []moneyView             `json:"charges"`
	Conversions        []conversionObservation `json:"conversions"`
	CartCleared        bool                    `json:"cart_cleared"`
	RemainingCartItems int                     `json:"remaining_cart_items"`
}

type activeExercise struct {
	request exerciseRequest
}

type loadOrderResult struct {
	SchemaVersion string  `json:"schema_version"`
	UserID        string  `json:"user_id"`
	GRPCCode      string  `json:"grpc_code"`
	LatencyMS     float64 `json:"latency_ms"`
	Error         string  `json:"error,omitempty"`
}

type loadConfigRequest struct {
	Fault         string `json:"fault"`
	DelayMS       int    `json:"delay_ms"`
	ResetCounters bool   `json:"reset_counters"`
}

type loadCounters struct {
	LoadOrders    int64 `json:"load_orders"`
	LoadSuccesses int64 `json:"load_successes"`
	ChargeSuccess int64 `json:"charge_successes"`
	ShipSuccess   int64 `json:"ship_successes"`
	CartClears    int64 `json:"cart_clears"`
	Confirmations int64 `json:"confirmations"`
}

type oracleHarness struct {
	pb.UnimplementedCartServiceServer
	pb.UnimplementedProductCatalogServiceServer
	pb.UnimplementedCurrencyServiceServer
	pb.UnimplementedShippingServiceServer
	pb.UnimplementedPaymentServiceServer
	pb.UnimplementedEmailServiceServer

	exerciseMu  sync.Mutex
	mu          sync.Mutex
	active      activeExercise
	carts       map[string][]*pb.CartItem
	cartCleared map[string]bool
	events      []event
	charges     []moneyView
	conversions []conversionObservation
	loadFault   string
	loadDelay   time.Duration
	counters    loadCounters

	checkoutClient          pb.CheckoutServiceClient
	currencyCandidateClient pb.CurrencyServiceClient
	currencyReferenceClient pb.CurrencyServiceClient
	paymentCandidateClient  pb.PaymentServiceClient
}

func moneyToView(value *pb.Money) moneyView {
	if value == nil {
		return moneyView{}
	}
	return moneyView{
		CurrencyCode: value.GetCurrencyCode(),
		Units:        value.GetUnits(),
		Nanos:        value.GetNanos(),
	}
}

func (h *oracleHarness) record(name string) {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.events = append(h.events, event{
		Sequence: len(h.events) + 1,
		Name:     name,
		At:       time.Now().UTC(),
	})
	switch name {
	case "charge-success":
		h.counters.ChargeSuccess++
	case "ship-success":
		h.counters.ShipSuccess++
	case "cart-clear":
		h.counters.CartClears++
	case "confirmation":
		h.counters.Confirmations++
	}
}

func (h *oracleHarness) reset(request exerciseRequest) {
	items := make([]*pb.CartItem, 0, len(request.Items))
	for _, item := range request.Items {
		items = append(items, &pb.CartItem{ProductId: item.ProductID, Quantity: item.Quantity})
	}
	h.mu.Lock()
	defer h.mu.Unlock()
	h.active = activeExercise{request: request}
	h.carts[request.UserID] = items
	h.cartCleared[request.UserID] = false
	h.events = nil
	h.charges = nil
	h.conversions = nil
}

func (h *oracleHarness) snapshot() ([]event, []moneyView, []conversionObservation, bool, int) {
	h.mu.Lock()
	defer h.mu.Unlock()
	userID := h.active.request.UserID
	return slices.Clone(h.events), slices.Clone(h.charges), slices.Clone(h.conversions),
		h.cartCleared[userID], len(h.carts[userID])
}

func (h *oracleHarness) AddItem(_ context.Context, request *pb.AddItemRequest) (*pb.Empty, error) {
	h.record("cart-add-item")
	h.mu.Lock()
	defer h.mu.Unlock()
	h.carts[request.GetUserId()] = append(
		h.carts[request.GetUserId()], proto.Clone(request.GetItem()).(*pb.CartItem),
	)
	h.cartCleared[request.GetUserId()] = false
	return &pb.Empty{}, nil
}

func (h *oracleHarness) GetCart(_ context.Context, request *pb.GetCartRequest) (*pb.Cart, error) {
	h.record("cart-read")
	h.mu.Lock()
	defer h.mu.Unlock()
	items := make([]*pb.CartItem, 0, len(h.carts[request.GetUserId()]))
	for _, item := range h.carts[request.GetUserId()] {
		items = append(items, proto.Clone(item).(*pb.CartItem))
	}
	return &pb.Cart{UserId: request.GetUserId(), Items: items}, nil
}

func (h *oracleHarness) EmptyCart(_ context.Context, request *pb.EmptyCartRequest) (*pb.Empty, error) {
	h.record("cart-clear")
	h.mu.Lock()
	defer h.mu.Unlock()
	h.cartCleared[request.GetUserId()] = true
	h.carts[request.GetUserId()] = nil
	return &pb.Empty{}, nil
}

func product(productID string) (*pb.Product, bool) {
	products := map[string]*pb.Product{
		"sku-1": {Id: "sku-1", Name: "Oracle product 1", PriceUsd: &pb.Money{CurrencyCode: "USD", Units: 3, Nanos: 250_000_000}},
		"sku-2": {Id: "sku-2", Name: "Oracle product 2", PriceUsd: &pb.Money{CurrencyCode: "USD", Units: 2, Nanos: 500_000_000}},
		"sku-3": {Id: "sku-3", Name: "Oracle product 3", PriceUsd: &pb.Money{CurrencyCode: "USD", Units: 1, Nanos: 100_000_000}},
		"sku-4": {Id: "sku-4", Name: "Oracle product 4", PriceUsd: &pb.Money{CurrencyCode: "USD", Units: 5, Nanos: 990_000_000}},
	}
	value, ok := products[productID]
	if !ok {
		return nil, false
	}
	return proto.Clone(value).(*pb.Product), true
}

func (h *oracleHarness) ListProducts(context.Context, *pb.Empty) (*pb.ListProductsResponse, error) {
	products := make([]*pb.Product, 0, 4)
	for _, id := range []string{"sku-1", "sku-2", "sku-3", "sku-4"} {
		value, _ := product(id)
		products = append(products, value)
	}
	return &pb.ListProductsResponse{Products: products}, nil
}

func (h *oracleHarness) GetProduct(_ context.Context, request *pb.GetProductRequest) (*pb.Product, error) {
	h.record("product-read:" + request.GetId())
	value, ok := product(request.GetId())
	if !ok {
		return nil, status.Errorf(codes.NotFound, "unknown oracle product %q", request.GetId())
	}
	return value, nil
}

func (h *oracleHarness) SearchProducts(context.Context, *pb.SearchProductsRequest) (*pb.SearchProductsResponse, error) {
	products, _ := h.ListProducts(context.Background(), &pb.Empty{})
	return &pb.SearchProductsResponse{Results: products.GetProducts()}, nil
}

func (h *oracleHarness) GetSupportedCurrencies(context.Context, *pb.Empty) (*pb.GetSupportedCurrenciesResponse, error) {
	return &pb.GetSupportedCurrenciesResponse{CurrencyCodes: []string{"USD", "EUR", "GBP", "JPY", "CAD"}}, nil
}

func identityConversion(request *pb.CurrencyConversionRequest) *pb.Money {
	result := proto.Clone(request.GetFrom()).(*pb.Money)
	result.CurrencyCode = request.GetToCode()
	return result
}

func (h *oracleHarness) Convert(ctx context.Context, request *pb.CurrencyConversionRequest) (*pb.Money, error) {
	h.record("currency-convert:" + request.GetToCode())
	actual := identityConversion(request)
	if h.currencyCandidateClient != nil {
		value, err := h.currencyCandidateClient.Convert(ctx, request)
		if err != nil {
			h.record("currency-error")
			return nil, err
		}
		actual = value
	}
	reference := identityConversion(request)
	if h.currencyReferenceClient != nil {
		value, err := h.currencyReferenceClient.Convert(ctx, request)
		if err != nil {
			return nil, status.Errorf(codes.Unavailable, "currency reference failed: %v", err)
		}
		reference = value
	}
	h.mu.Lock()
	h.conversions = append(h.conversions, conversionObservation{
		From:      moneyToView(request.GetFrom()),
		To:        request.GetToCode(),
		Actual:    moneyToView(actual),
		Reference: moneyToView(reference),
	})
	h.mu.Unlock()
	return actual, nil
}

func (h *oracleHarness) GetQuote(context.Context, *pb.GetQuoteRequest) (*pb.GetQuoteResponse, error) {
	h.record("shipping-quote")
	return &pb.GetQuoteResponse{CostUsd: &pb.Money{CurrencyCode: "USD", Units: 1, Nanos: 750_000_000}}, nil
}

func (h *oracleHarness) ShipOrder(_ context.Context, _ *pb.ShipOrderRequest) (*pb.ShipOrderResponse, error) {
	h.record("ship-attempt")
	h.mu.Lock()
	fault := h.active.request.Fault
	if fault == "" {
		fault = h.loadFault
	}
	delay := h.loadDelay
	h.mu.Unlock()
	if fault == "shipping-unavailable" {
		h.record("ship-error")
		return nil, status.Error(codes.Unavailable, "controlled oracle shipping failure")
	}
	if fault == "shipping-tail-latency" {
		time.Sleep(delay)
	}
	h.record("ship-success")
	return &pb.ShipOrderResponse{TrackingId: "oracle-tracking-id"}, nil
}

func luhnValid(number string) bool {
	if len(number) < 12 || len(number) > 19 {
		return false
	}
	sum := 0
	parity := len(number) % 2
	for index, character := range number {
		if character < '0' || character > '9' {
			return false
		}
		digit := int(character - '0')
		if index%2 == parity {
			digit *= 2
			if digit > 9 {
				digit -= 9
			}
		}
		sum += digit
	}
	return sum%10 == 0
}

func validateCard(card *pb.CreditCardInfo, now time.Time) error {
	if card == nil || !luhnValid(card.GetCreditCardNumber()) {
		return errors.New("invalid credit card")
	}
	if strings.HasPrefix(card.GetCreditCardNumber(), "34") || strings.HasPrefix(card.GetCreditCardNumber(), "37") {
		return errors.New("unsupported credit card")
	}
	currentMonth := int32(now.Month())
	currentYear := int32(now.Year())
	if card.GetCreditCardExpirationYear()*12+card.GetCreditCardExpirationMonth() < currentYear*12+currentMonth {
		return errors.New("expired credit card")
	}
	return nil
}

func (h *oracleHarness) Charge(ctx context.Context, request *pb.ChargeRequest) (*pb.ChargeResponse, error) {
	h.record("charge-attempt")
	h.mu.Lock()
	h.charges = append(h.charges, moneyToView(request.GetAmount()))
	fault := h.active.request.Fault
	if fault == "" {
		fault = h.loadFault
	}
	delay := h.loadDelay
	h.mu.Unlock()
	if fault == "payment-unavailable" {
		h.record("charge-error")
		return nil, status.Error(codes.Unavailable, "controlled oracle payment failure")
	}
	if fault == "payment-tail-latency" {
		time.Sleep(delay)
	}
	if h.paymentCandidateClient != nil {
		response, err := h.paymentCandidateClient.Charge(ctx, request)
		if err != nil {
			h.record("charge-error")
			return nil, err
		}
		h.record("charge-success")
		return response, nil
	}
	if err := validateCard(request.GetCreditCard(), time.Now().UTC()); err != nil {
		h.record("charge-error")
		return nil, status.Error(codes.InvalidArgument, err.Error())
	}
	h.record("charge-success")
	return &pb.ChargeResponse{TransactionId: "oracle-transaction-id"}, nil
}

func (h *oracleHarness) SendOrderConfirmation(context.Context, *pb.SendOrderConfirmationRequest) (*pb.Empty, error) {
	h.record("confirmation")
	return &pb.Empty{}, nil
}

func normalizeExercise(request *exerciseRequest) error {
	if request.UserID == "" {
		request.UserID = fmt.Sprintf("oracle-%d", time.Now().UnixNano())
	}
	if request.Currency == "" {
		request.Currency = "USD"
	}
	if !slices.Contains([]string{"USD", "EUR", "GBP", "JPY", "CAD"}, request.Currency) {
		return fmt.Errorf("unsupported currency %q", request.Currency)
	}
	if len(request.Items) == 0 {
		request.Items = []itemInput{{ProductID: "sku-1", Quantity: 1}}
	}
	if len(request.Items) > 4 {
		return errors.New("at most four cart items are allowed")
	}
	for _, item := range request.Items {
		if _, ok := product(item.ProductID); !ok {
			return fmt.Errorf("unknown product %q", item.ProductID)
		}
		if item.Quantity < 1 || item.Quantity > 3 {
			return errors.New("item quantity must be between one and three")
		}
	}
	if !slices.Contains([]string{"", "payment-unavailable", "shipping-unavailable"}, request.Fault) {
		return fmt.Errorf("unsupported fault %q", request.Fault)
	}
	if request.CardCase == "" {
		request.CardCase = "valid"
	}
	if !slices.Contains([]string{"valid", "unsupported-card", "expired-card", "invalid-number"}, request.CardCase) {
		return fmt.Errorf("unsupported card case %q", request.CardCase)
	}
	if request.TimeoutMS == 0 {
		request.TimeoutMS = 30_000
	}
	if request.TimeoutMS < 100 || request.TimeoutMS > 60_000 {
		return errors.New("timeout_ms must be between 100 and 60000")
	}
	return nil
}

func cardForCase(cardCase string, now time.Time) *pb.CreditCardInfo {
	card := &pb.CreditCardInfo{
		CreditCardNumber:          "4111111111111111",
		CreditCardCvv:             123,
		CreditCardExpirationMonth: 12,
		CreditCardExpirationYear:  int32(now.Year() + 2),
	}
	switch cardCase {
	case "unsupported-card":
		card.CreditCardNumber = "378282246310005"
	case "expired-card":
		card.CreditCardExpirationMonth = 1
		card.CreditCardExpirationYear = int32(now.Year() - 1)
	case "invalid-number":
		card.CreditCardNumber = "1234567890"
	}
	return card
}

func (h *oracleHarness) exerciseHandler(response http.ResponseWriter, request *http.Request) {
	if request.Method != http.MethodPost {
		http.Error(response, "POST required", http.StatusMethodNotAllowed)
		return
	}
	request.Body = http.MaxBytesReader(response, request.Body, maximumBodySize)
	var input exerciseRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&input); err != nil {
		http.Error(response, "invalid JSON request: "+err.Error(), http.StatusBadRequest)
		return
	}
	if err := normalizeExercise(&input); err != nil {
		http.Error(response, err.Error(), http.StatusBadRequest)
		return
	}

	h.exerciseMu.Lock()
	defer h.exerciseMu.Unlock()
	h.reset(input)

	ctx, cancel := context.WithTimeout(request.Context(), time.Duration(input.TimeoutMS)*time.Millisecond)
	defer cancel()
	result, callErr := h.checkoutClient.PlaceOrder(ctx, &pb.PlaceOrderRequest{
		UserId:       input.UserID,
		UserCurrency: input.Currency,
		Address: &pb.Address{
			StreetAddress: "1 Oracle Street",
			City:          "Test City",
			State:         "SP",
			Country:       "BR",
			ZipCode:       10101,
		},
		Email:      "oracle@example.invalid",
		CreditCard: cardForCase(input.CardCase, time.Now().UTC()),
	})

	output := exerciseResult{
		SchemaVersion: "1.0.0",
		UserID:        input.UserID,
		ExpectedCase:  input.ExpectedCase,
		Input:         input,
		GRPCCode:      codes.OK.String(),
	}
	if callErr != nil {
		output.GRPCCode = status.Code(callErr).String()
		output.Error = callErr.Error()
	} else if encoded, err := protojson.Marshal(result); err != nil {
		output.GRPCCode = codes.Internal.String()
		output.Error = "could not encode checkout response: " + err.Error()
	} else {
		output.Response = encoded
	}
	output.Events, output.Charges, output.Conversions, output.CartCleared, output.RemainingCartItems = h.snapshot()
	h.mu.Lock()
	h.active.request.Fault = ""
	h.mu.Unlock()

	response.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(response).Encode(output); err != nil {
		log.Printf("encode exercise result: %v", err)
	}
}

func (h *oracleHarness) prepareLoadUser(request exerciseRequest) {
	items := make([]*pb.CartItem, 0, len(request.Items))
	for _, item := range request.Items {
		items = append(items, &pb.CartItem{ProductId: item.ProductID, Quantity: item.Quantity})
	}
	h.mu.Lock()
	defer h.mu.Unlock()
	h.carts[request.UserID] = items
	h.cartCleared[request.UserID] = false
}

func (h *oracleHarness) loadOrderHandler(response http.ResponseWriter, request *http.Request) {
	if request.Method != http.MethodPost {
		http.Error(response, "POST required", http.StatusMethodNotAllowed)
		return
	}
	request.Body = http.MaxBytesReader(response, request.Body, maximumBodySize)
	var input exerciseRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&input); err != nil {
		http.Error(response, "invalid JSON request: "+err.Error(), http.StatusBadRequest)
		return
	}
	input.Fault = ""
	input.CardCase = "valid"
	if err := normalizeExercise(&input); err != nil {
		http.Error(response, err.Error(), http.StatusBadRequest)
		return
	}
	h.prepareLoadUser(input)
	h.mu.Lock()
	h.counters.LoadOrders++
	h.mu.Unlock()

	ctx, cancel := context.WithTimeout(request.Context(), time.Duration(input.TimeoutMS)*time.Millisecond)
	defer cancel()
	started := time.Now()
	_, callErr := h.checkoutClient.PlaceOrder(ctx, &pb.PlaceOrderRequest{
		UserId:       input.UserID,
		UserCurrency: input.Currency,
		Address: &pb.Address{
			StreetAddress: "1 Oracle Load Street",
			City:          "Test City",
			State:         "SP",
			Country:       "BR",
			ZipCode:       10101,
		},
		Email:      "oracle-load@example.invalid",
		CreditCard: cardForCase("valid", time.Now().UTC()),
	})
	output := loadOrderResult{
		SchemaVersion: "1.0.0",
		UserID:        input.UserID,
		GRPCCode:      codes.OK.String(),
		LatencyMS:     float64(time.Since(started).Microseconds()) / 1000,
	}
	if callErr != nil {
		output.GRPCCode = status.Code(callErr).String()
		output.Error = callErr.Error()
	} else {
		h.mu.Lock()
		h.counters.LoadSuccesses++
		h.mu.Unlock()
	}
	response.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(response).Encode(output); err != nil {
		log.Printf("encode load-order result: %v", err)
	}
}

func (h *oracleHarness) loadConfigHandler(response http.ResponseWriter, request *http.Request) {
	if request.Method == http.MethodGet {
		h.mu.Lock()
		output := struct {
			Fault    string       `json:"fault"`
			DelayMS  int64        `json:"delay_ms"`
			Counters loadCounters `json:"counters"`
		}{
			Fault:    h.loadFault,
			DelayMS:  h.loadDelay.Milliseconds(),
			Counters: h.counters,
		}
		h.mu.Unlock()
		response.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(response).Encode(output)
		return
	}
	if request.Method != http.MethodPost {
		http.Error(response, "GET or POST required", http.StatusMethodNotAllowed)
		return
	}
	request.Body = http.MaxBytesReader(response, request.Body, maximumBodySize)
	var input loadConfigRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&input); err != nil {
		http.Error(response, "invalid JSON request: "+err.Error(), http.StatusBadRequest)
		return
	}
	if !slices.Contains([]string{"", "payment-tail-latency", "shipping-tail-latency"}, input.Fault) {
		http.Error(response, "unsupported load fault", http.StatusBadRequest)
		return
	}
	if input.DelayMS < 0 || input.DelayMS > 1_000 {
		http.Error(response, "delay_ms must be between zero and 1000", http.StatusBadRequest)
		return
	}
	h.mu.Lock()
	h.loadFault = input.Fault
	h.loadDelay = time.Duration(input.DelayMS) * time.Millisecond
	if input.ResetCounters {
		h.counters = loadCounters{}
		h.events = nil
		h.charges = nil
	}
	output := h.counters
	h.mu.Unlock()
	response.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(response).Encode(output)
}

func environment(name, fallback string) string {
	if value := os.Getenv(name); value != "" {
		return value
	}
	return fallback
}

func optionalConnection(address string) (*grpc.ClientConn, error) {
	if address == "" {
		return nil, nil
	}
	return grpc.NewClient(address, grpc.WithTransportCredentials(insecure.NewCredentials()))
}

func main() {
	checkoutAddress := environment("CHECKOUT_SERVICE_ADDR", "checkoutservice:5050")
	checkoutConnection, err := optionalConnection(checkoutAddress)
	if err != nil {
		log.Fatalf("connect to checkout candidate: %v", err)
	}
	defer checkoutConnection.Close()

	harness := &oracleHarness{
		checkoutClient: pb.NewCheckoutServiceClient(checkoutConnection),
		carts:          make(map[string][]*pb.CartItem),
		cartCleared:    make(map[string]bool),
	}
	currencyCandidateConnection, err := optionalConnection(os.Getenv("CURRENCY_CANDIDATE_ADDR"))
	if err != nil {
		log.Fatalf("connect to candidate currency service: %v", err)
	}
	if currencyCandidateConnection != nil {
		defer currencyCandidateConnection.Close()
		harness.currencyCandidateClient = pb.NewCurrencyServiceClient(currencyCandidateConnection)
	}
	currencyReferenceConnection, err := optionalConnection(os.Getenv("CURRENCY_REFERENCE_ADDR"))
	if err != nil {
		log.Fatalf("connect to reference currency service: %v", err)
	}
	if currencyReferenceConnection != nil {
		defer currencyReferenceConnection.Close()
		harness.currencyReferenceClient = pb.NewCurrencyServiceClient(currencyReferenceConnection)
	}
	paymentCandidateConnection, err := optionalConnection(os.Getenv("PAYMENT_CANDIDATE_ADDR"))
	if err != nil {
		log.Fatalf("connect to candidate payment service: %v", err)
	}
	if paymentCandidateConnection != nil {
		defer paymentCandidateConnection.Close()
		harness.paymentCandidateClient = pb.NewPaymentServiceClient(paymentCandidateConnection)
	}

	grpcListener, err := net.Listen("tcp", ":"+environment("GRPC_PORT", defaultGRPCPort))
	if err != nil {
		log.Fatalf("listen for oracle gRPC dependencies: %v", err)
	}
	grpcServer := grpc.NewServer()
	pb.RegisterCartServiceServer(grpcServer, harness)
	pb.RegisterProductCatalogServiceServer(grpcServer, harness)
	pb.RegisterCurrencyServiceServer(grpcServer, harness)
	pb.RegisterShippingServiceServer(grpcServer, harness)
	pb.RegisterPaymentServiceServer(grpcServer, harness)
	pb.RegisterEmailServiceServer(grpcServer, harness)
	healthServer := health.NewServer()
	healthServer.SetServingStatus("", healthpb.HealthCheckResponse_SERVING)
	healthpb.RegisterHealthServer(grpcServer, healthServer)
	go func() {
		if err := grpcServer.Serve(grpcListener); err != nil {
			log.Fatalf("serve oracle gRPC dependencies: %v", err)
		}
	}()

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(response http.ResponseWriter, _ *http.Request) {
		response.WriteHeader(http.StatusNoContent)
	})
	mux.HandleFunc("/exercise", harness.exerciseHandler)
	mux.HandleFunc("/load-order", harness.loadOrderHandler)
	mux.HandleFunc("/load-config", harness.loadConfigHandler)
	httpServer := &http.Server{
		Addr:              ":" + environment("HTTP_PORT", defaultHTTPPort),
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       65 * time.Second,
		WriteTimeout:      65 * time.Second,
		IdleTimeout:       30 * time.Second,
	}
	log.Printf("oracle harness listening on gRPC %s and HTTP %s", grpcListener.Addr(), httpServer.Addr)
	if err := httpServer.ListenAndServe(); !errors.Is(err, http.ErrServerClosed) {
		log.Fatalf("serve oracle HTTP API: %v", err)
	}
}
