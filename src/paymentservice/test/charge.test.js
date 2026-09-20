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

'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');

const charge = require('../charge');

function request (number, month = 12, year = 2999) {
  return {
    amount: { currency_code: 'USD', units: 42, nanos: 250000000 },
    credit_card: {
      credit_card_number: number,
      credit_card_cvv: 123,
      credit_card_expiration_month: month,
      credit_card_expiration_year: year
    }
  };
}

test('accepts supported, valid, non-expired cards', () => {
  for (const number of ['4111111111111111', '5555555555554444']) {
    const response = charge(request(number));
    assert.match(response.transaction_id, /^[0-9a-f-]{36}$/i);
  }
});

test('rejects an invalid card number', () => {
  assert.throws(
    () => charge(request('1234567890')),
    error => error.code === 400 && /invalid/i.test(error.message)
  );
});

test('rejects a valid but unsupported card brand', () => {
  assert.throws(
    () => charge(request('378282246310005')),
    error => error.code === 400 && /only VISA or MasterCard/i.test(error.message)
  );
});

test('rejects an expired supported card', () => {
  assert.throws(
    () => charge(request('4111111111111111', 1, 2000)),
    error => error.code === 400 && /expired/i.test(error.message)
  );
});
