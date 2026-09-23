# Copyright 2026 Google LLC
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

import unittest

import demo_pb2
from grpc_health.v1 import health_pb2

import email_server


class EmailServiceContractTests(unittest.TestCase):
    def test_health_check_reports_serving(self):
        response = email_server.DummyEmailService().Check(None, None)

        self.assertEqual(response.status, health_pb2.HealthCheckResponse.SERVING)

    def test_dummy_confirmation_acknowledges_a_valid_request(self):
        request = demo_pb2.SendOrderConfirmationRequest(
            email="contract@example.invalid",
            order=demo_pb2.OrderResult(order_id="contract-order"),
        )

        response = email_server.DummyEmailService().SendOrderConfirmation(request, None)

        self.assertEqual(response, demo_pb2.Empty())

    def test_confirmation_template_escapes_order_content(self):
        order = demo_pb2.OrderResult(
            order_id="<script>unsafe()</script>",
            shipping_tracking_id="tracking-contract",
            shipping_cost=demo_pb2.Money(
                currency_code="USD",
                units=1,
                nanos=250_000_000,
            ),
            shipping_address=demo_pb2.Address(
                city="Test City",
                country="BR",
                zip_code=10101,
            ),
        )

        rendered = email_server.template.render(order=order)

        self.assertNotIn("<script>unsafe()</script>", rendered)
        self.assertIn("&lt;script&gt;unsafe()&lt;/script&gt;", rendered)


if __name__ == "__main__":
    unittest.main()
