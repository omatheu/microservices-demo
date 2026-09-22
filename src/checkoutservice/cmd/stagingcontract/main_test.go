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

package main

import (
	"context"
	"testing"
	"time"

	pb "github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice/genproto"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/proto"
)

type fakeCart struct {
	items map[string][]*pb.CartItem
}

func newFakeCart() *fakeCart {
	return &fakeCart{items: map[string][]*pb.CartItem{}}
}

func (cart *fakeCart) AddItem(_ context.Context, request *pb.AddItemRequest, _ ...grpc.CallOption) (*pb.Empty, error) {
	cart.items[request.GetUserId()] = append(
		cart.items[request.GetUserId()],
		proto.Clone(request.GetItem()).(*pb.CartItem),
	)
	return &pb.Empty{}, nil
}

func (cart *fakeCart) GetCart(_ context.Context, request *pb.GetCartRequest, _ ...grpc.CallOption) (*pb.Cart, error) {
	items := make([]*pb.CartItem, 0, len(cart.items[request.GetUserId()]))
	for _, item := range cart.items[request.GetUserId()] {
		items = append(items, proto.Clone(item).(*pb.CartItem))
	}
	return &pb.Cart{UserId: request.GetUserId(), Items: items}, nil
}

func (cart *fakeCart) EmptyCart(_ context.Context, request *pb.EmptyCartRequest, _ ...grpc.CallOption) (*pb.Empty, error) {
	delete(cart.items, request.GetUserId())
	return &pb.Empty{}, nil
}

type fakeCheckout struct {
	cart                  *fakeCart
	clearOnPaymentFailure bool
}

func (checkout *fakeCheckout) PlaceOrder(_ context.Context, request *pb.PlaceOrderRequest, _ ...grpc.CallOption) (*pb.PlaceOrderResponse, error) {
	if request.GetCreditCard().GetCreditCardExpirationYear() < 2026 {
		if checkout.clearOnPaymentFailure {
			delete(checkout.cart.items, request.GetUserId())
		}
		return nil, status.Error(codes.Internal, "controlled payment rejection")
	}
	items := checkout.cart.items[request.GetUserId()]
	delete(checkout.cart.items, request.GetUserId())
	return &pb.PlaceOrderResponse{Order: &pb.OrderResult{
		OrderId:            "order-1",
		ShippingTrackingId: "tracking-1",
		ShippingCost:       &pb.Money{CurrencyCode: "USD", Units: 1},
		ShippingAddress:    proto.Clone(request.GetAddress()).(*pb.Address),
		Items: []*pb.OrderItem{{
			Item: proto.Clone(items[0]).(*pb.CartItem),
			Cost: &pb.Money{CurrencyCode: "USD", Units: 19},
		}},
	}}, nil
}

func TestExecutePassesBothRequiredRealServiceContracts(t *testing.T) {
	cart := newFakeCart()
	checkout := &fakeCheckout{cart: cart}
	result := execute(
		context.Background(), cart, checkout, "cand-test", 1,
		time.Date(2026, time.September, 21, 0, 0, 0, 0, time.UTC),
	)

	if result.Decision != "PASS" || result.Passed != 2 || result.Failed != 0 {
		t.Fatalf("unexpected result: %+v", result)
	}
	if result.OperationalSnapshotAccess {
		t.Fatal("traditional staging contract probe must not access operational state")
	}
	if len(result.Cases) != 2 || result.Cases[0].ID != "happy-path-order" || result.Cases[1].ID != "payment-failure-preserves-cart" {
		t.Fatalf("unexpected contract cases: %+v", result.Cases)
	}
}

func TestExecuteFailsWhenPaymentErrorClearsCart(t *testing.T) {
	cart := newFakeCart()
	checkout := &fakeCheckout{cart: cart, clearOnPaymentFailure: true}
	result := execute(
		context.Background(), cart, checkout, "cand-test", 1,
		time.Date(2026, time.September, 21, 0, 0, 0, 0, time.UTC),
	)

	if result.Decision != "FAIL" || result.Failed != 1 {
		t.Fatalf("unexpected result: %+v", result)
	}
	if result.Cases[1].Failure != "verify-cart-retained" {
		t.Fatalf("unexpected failure: %+v", result.Cases[1])
	}
}
