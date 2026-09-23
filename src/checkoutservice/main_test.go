// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package main

import (
	"context"
	"fmt"
	"net"
	"reflect"
	"sync"
	"testing"

	pb "github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice/genproto"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
	"google.golang.org/grpc/test/bufconn"
	"google.golang.org/protobuf/proto"
)

const contractBufferSize = 1024 * 1024

type contractDependencies struct {
	pb.UnimplementedCartServiceServer
	pb.UnimplementedProductCatalogServiceServer
	pb.UnimplementedCurrencyServiceServer
	pb.UnimplementedShippingServiceServer
	pb.UnimplementedPaymentServiceServer
	pb.UnimplementedEmailServiceServer

	mu sync.Mutex

	events         []string
	chargeRequests []*pb.ChargeRequest
	shipRequests   []*pb.ShipOrderRequest
	emailRequests  []*pb.SendOrderConfirmationRequest

	cartItems    []*pb.CartItem
	products     map[string]*pb.Product
	shippingCost *pb.Money

	getCartErr   error
	productErr   error
	currencyErr  error
	quoteErr     error
	paymentErr   error
	shippingErr  error
	emptyCartErr error
	emailErr     error
}

func newContractDependencies() *contractDependencies {
	return &contractDependencies{
		cartItems: []*pb.CartItem{
			{ProductId: "sku-1", Quantity: 2},
			{ProductId: "sku-2", Quantity: 1},
		},
		products: map[string]*pb.Product{
			"sku-1": {Id: "sku-1", PriceUsd: contractMoney("USD", 3, 250_000_000)},
			"sku-2": {Id: "sku-2", PriceUsd: contractMoney("USD", 2, 500_000_000)},
		},
		shippingCost: contractMoney("USD", 1, 750_000_000),
	}
}

func (d *contractDependencies) record(event string) {
	d.mu.Lock()
	defer d.mu.Unlock()
	d.events = append(d.events, event)
}

func (d *contractDependencies) observedEvents() []string {
	d.mu.Lock()
	defer d.mu.Unlock()
	return append([]string(nil), d.events...)
}

func (d *contractDependencies) GetCart(_ context.Context, req *pb.GetCartRequest) (*pb.Cart, error) {
	d.record("get-cart")
	if d.getCartErr != nil {
		return nil, d.getCartErr
	}
	return &pb.Cart{UserId: req.GetUserId(), Items: d.cartItems}, nil
}

func (d *contractDependencies) EmptyCart(_ context.Context, _ *pb.EmptyCartRequest) (*pb.Empty, error) {
	d.record("empty-cart")
	if d.emptyCartErr != nil {
		return nil, d.emptyCartErr
	}
	return &pb.Empty{}, nil
}

func (d *contractDependencies) GetProduct(_ context.Context, req *pb.GetProductRequest) (*pb.Product, error) {
	d.record("get-product:" + req.GetId())
	if d.productErr != nil {
		return nil, d.productErr
	}
	product, ok := d.products[req.GetId()]
	if !ok {
		return nil, status.Errorf(codes.NotFound, "unknown product %q", req.GetId())
	}
	return proto.Clone(product).(*pb.Product), nil
}

func (d *contractDependencies) Convert(_ context.Context, req *pb.CurrencyConversionRequest) (*pb.Money, error) {
	d.record(fmt.Sprintf("convert:%s->%s", req.GetFrom().GetCurrencyCode(), req.GetToCode()))
	if d.currencyErr != nil {
		return nil, d.currencyErr
	}
	return contractMoney(req.GetToCode(), req.GetFrom().GetUnits(), req.GetFrom().GetNanos()), nil
}

func (d *contractDependencies) GetQuote(_ context.Context, _ *pb.GetQuoteRequest) (*pb.GetQuoteResponse, error) {
	d.record("get-shipping-quote")
	if d.quoteErr != nil {
		return nil, d.quoteErr
	}
	return &pb.GetQuoteResponse{CostUsd: proto.Clone(d.shippingCost).(*pb.Money)}, nil
}

func (d *contractDependencies) ShipOrder(_ context.Context, req *pb.ShipOrderRequest) (*pb.ShipOrderResponse, error) {
	d.record("ship")
	d.mu.Lock()
	d.shipRequests = append(d.shipRequests, proto.Clone(req).(*pb.ShipOrderRequest))
	d.mu.Unlock()
	if d.shippingErr != nil {
		return nil, d.shippingErr
	}
	return &pb.ShipOrderResponse{TrackingId: "tracking-contract-1"}, nil
}

func (d *contractDependencies) Charge(_ context.Context, req *pb.ChargeRequest) (*pb.ChargeResponse, error) {
	d.record("charge")
	d.mu.Lock()
	d.chargeRequests = append(d.chargeRequests, proto.Clone(req).(*pb.ChargeRequest))
	d.mu.Unlock()
	if d.paymentErr != nil {
		return nil, d.paymentErr
	}
	return &pb.ChargeResponse{TransactionId: "transaction-contract-1"}, nil
}

func (d *contractDependencies) SendOrderConfirmation(_ context.Context, req *pb.SendOrderConfirmationRequest) (*pb.Empty, error) {
	d.record("email")
	d.mu.Lock()
	d.emailRequests = append(d.emailRequests, proto.Clone(req).(*pb.SendOrderConfirmationRequest))
	d.mu.Unlock()
	if d.emailErr != nil {
		return nil, d.emailErr
	}
	return &pb.Empty{}, nil
}

func newContractHarness(t *testing.T) (*checkoutService, *contractDependencies) {
	t.Helper()

	dependencies := newContractDependencies()
	listener := bufconn.Listen(contractBufferSize)
	server := grpc.NewServer()
	pb.RegisterCartServiceServer(server, dependencies)
	pb.RegisterProductCatalogServiceServer(server, dependencies)
	pb.RegisterCurrencyServiceServer(server, dependencies)
	pb.RegisterShippingServiceServer(server, dependencies)
	pb.RegisterPaymentServiceServer(server, dependencies)
	pb.RegisterEmailServiceServer(server, dependencies)

	go func() {
		if err := server.Serve(listener); err != nil {
			return
		}
	}()

	connection, err := grpc.NewClient(
		"passthrough:///checkout-contract",
		grpc.WithContextDialer(func(ctx context.Context, _ string) (net.Conn, error) {
			return listener.DialContext(ctx)
		}),
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		t.Fatalf("create in-memory gRPC client: %v", err)
	}

	t.Cleanup(func() {
		_ = connection.Close()
		server.Stop()
		_ = listener.Close()
	})

	service := &checkoutService{
		productCatalogSvcConn: connection,
		cartSvcConn:           connection,
		currencySvcConn:       connection,
		shippingSvcConn:       connection,
		emailSvcConn:          connection,
		paymentSvcConn:        connection,
	}
	return service, dependencies
}

func contractRequest() *pb.PlaceOrderRequest {
	return &pb.PlaceOrderRequest{
		UserId:       "contract-user",
		UserCurrency: "EUR",
		Address: &pb.Address{
			StreetAddress: "1 Contract Street",
			City:          "Test City",
			State:         "SP",
			Country:       "BR",
			ZipCode:       10101,
		},
		Email: "contract@example.invalid",
		CreditCard: &pb.CreditCardInfo{
			CreditCardNumber:          "4111111111111111",
			CreditCardCvv:             123,
			CreditCardExpirationYear:  2030,
			CreditCardExpirationMonth: 12,
		},
	}
}

func contractMoney(currency string, units int64, nanos int32) *pb.Money {
	return &pb.Money{CurrencyCode: currency, Units: units, Nanos: nanos}
}

func contractPreparationEvents() []string {
	return []string{
		"get-cart",
		"get-product:sku-1",
		"convert:USD->EUR",
		"get-product:sku-2",
		"convert:USD->EUR",
		"get-shipping-quote",
		"convert:USD->EUR",
	}
}

func assertContractEvents(t *testing.T, got, want []string) {
	t.Helper()
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("unexpected dependency calls\n got: %v\nwant: %v", got, want)
	}
}

func TestPlaceOrderContract_ChargesExactTotalAndOrdersEffects(t *testing.T) {
	service, dependencies := newContractHarness(t)
	request := contractRequest()

	response, err := service.PlaceOrder(context.Background(), request)
	if err != nil {
		t.Fatalf("PlaceOrder returned an error: %v", err)
	}

	wantEvents := append(contractPreparationEvents(), "charge", "ship", "empty-cart", "email")
	assertContractEvents(t, dependencies.observedEvents(), wantEvents)

	if len(dependencies.chargeRequests) != 1 {
		t.Fatalf("charge calls = %d, want 1", len(dependencies.chargeRequests))
	}
	wantTotal := contractMoney("EUR", 10, 750_000_000)
	if !proto.Equal(dependencies.chargeRequests[0].GetAmount(), wantTotal) {
		t.Fatalf("charged amount = %v, want %v", dependencies.chargeRequests[0].GetAmount(), wantTotal)
	}
	if !proto.Equal(dependencies.chargeRequests[0].GetCreditCard(), request.GetCreditCard()) {
		t.Fatal("payment did not receive the submitted credit card")
	}

	order := response.GetOrder()
	if order.GetOrderId() == "" {
		t.Fatal("response has an empty order ID")
	}
	if order.GetShippingTrackingId() != "tracking-contract-1" {
		t.Fatalf("tracking ID = %q, want tracking-contract-1", order.GetShippingTrackingId())
	}
	if !proto.Equal(order.GetShippingCost(), contractMoney("EUR", 1, 750_000_000)) {
		t.Fatalf("shipping cost = %v, want EUR 1.75", order.GetShippingCost())
	}
	if len(order.GetItems()) != 2 {
		t.Fatalf("order items = %d, want 2", len(order.GetItems()))
	}
	if len(dependencies.shipRequests) != 1 || len(dependencies.emailRequests) != 1 {
		t.Fatalf("ship calls = %d and email calls = %d, want one of each", len(dependencies.shipRequests), len(dependencies.emailRequests))
	}
}

func TestPlaceOrderContract_PaymentFailureStopsDownstreamEffects(t *testing.T) {
	service, dependencies := newContractHarness(t)
	dependencies.paymentErr = status.Error(codes.Unavailable, "controlled payment failure")

	response, err := service.PlaceOrder(context.Background(), contractRequest())
	if response != nil {
		t.Fatalf("response = %v, want nil", response)
	}
	if status.Code(err) != codes.Internal {
		t.Fatalf("error code = %s, want %s", status.Code(err), codes.Internal)
	}

	wantEvents := append(contractPreparationEvents(), "charge")
	assertContractEvents(t, dependencies.observedEvents(), wantEvents)
	if len(dependencies.shipRequests) != 0 || len(dependencies.emailRequests) != 0 {
		t.Fatal("shipping or email occurred after payment failure")
	}
}

func TestPlaceOrderContract_PreparationFailureNeverCharges(t *testing.T) {
	tests := []struct {
		name      string
		configure func(*contractDependencies)
		want      []string
	}{
		{
			name: "cart",
			configure: func(dependencies *contractDependencies) {
				dependencies.getCartErr = status.Error(codes.Unavailable, "controlled cart failure")
			},
			want: []string{"get-cart"},
		},
		{
			name: "product catalog",
			configure: func(dependencies *contractDependencies) {
				dependencies.productErr = status.Error(codes.Unavailable, "controlled catalog failure")
			},
			want: []string{"get-cart", "get-product:sku-1"},
		},
		{
			name: "currency",
			configure: func(dependencies *contractDependencies) {
				dependencies.currencyErr = status.Error(codes.Unavailable, "controlled currency failure")
			},
			want: []string{"get-cart", "get-product:sku-1", "convert:USD->EUR"},
		},
		{
			name: "shipping quote",
			configure: func(dependencies *contractDependencies) {
				dependencies.quoteErr = status.Error(codes.Unavailable, "controlled quote failure")
			},
			want: []string{
				"get-cart",
				"get-product:sku-1",
				"convert:USD->EUR",
				"get-product:sku-2",
				"convert:USD->EUR",
				"get-shipping-quote",
			},
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			service, dependencies := newContractHarness(t)
			test.configure(dependencies)

			response, err := service.PlaceOrder(context.Background(), contractRequest())
			if response != nil {
				t.Fatalf("response = %v, want nil", response)
			}
			if status.Code(err) != codes.Internal {
				t.Fatalf("error code = %s, want %s", status.Code(err), codes.Internal)
			}
			assertContractEvents(t, dependencies.observedEvents(), test.want)
			if len(dependencies.chargeRequests) != 0 || len(dependencies.shipRequests) != 0 || len(dependencies.emailRequests) != 0 {
				t.Fatal("an irreversible downstream effect occurred after preparation failure")
			}
		})
	}
}

func TestPlaceOrderContract_ShippingFailureDoesNotClearCartOrEmail(t *testing.T) {
	service, dependencies := newContractHarness(t)
	dependencies.shippingErr = status.Error(codes.Unavailable, "controlled shipping failure")

	response, err := service.PlaceOrder(context.Background(), contractRequest())
	if response != nil {
		t.Fatalf("response = %v, want nil", response)
	}
	if status.Code(err) != codes.Unavailable {
		t.Fatalf("error code = %s, want %s", status.Code(err), codes.Unavailable)
	}

	wantEvents := append(contractPreparationEvents(), "charge", "ship")
	assertContractEvents(t, dependencies.observedEvents(), wantEvents)
	if len(dependencies.chargeRequests) != 1 {
		t.Fatalf("charge calls = %d, want 1", len(dependencies.chargeRequests))
	}
	if len(dependencies.emailRequests) != 0 {
		t.Fatal("email occurred after shipping failure")
	}
}

func TestPlaceOrderContract_EmailFailureDoesNotInvalidateCompletedOrder(t *testing.T) {
	service, dependencies := newContractHarness(t)
	dependencies.emailErr = status.Error(codes.Unavailable, "controlled email failure")

	response, err := service.PlaceOrder(context.Background(), contractRequest())
	if err != nil {
		t.Fatalf("PlaceOrder returned an error for a non-critical email failure: %v", err)
	}
	if response.GetOrder().GetShippingTrackingId() != "tracking-contract-1" {
		t.Fatal("completed order was not returned after email failure")
	}

	wantEvents := append(contractPreparationEvents(), "charge", "ship", "empty-cart", "email")
	assertContractEvents(t, dependencies.observedEvents(), wantEvents)
}
