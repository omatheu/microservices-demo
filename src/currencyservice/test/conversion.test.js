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

process.env.DISABLE_PROFILER = '1';

const assert = require('node:assert/strict');
const test = require('node:test');

const { _carry, convert, getSupportedCurrencies } = require('../server');

function convertAsync (from, toCode) {
  return new Promise((resolve, reject) => {
    convert({ request: { from, to_code: toCode } }, (error, result) => {
      if (error) {
        reject(error);
      } else {
        resolve(result);
      }
    });
  });
}

test('normalizes nanos that exceed one currency unit', () => {
  assert.deepEqual(
    _carry({ units: 1, nanos: 1500000000 }),
    { units: 2, nanos: 500000000 }
  );
});

test('identity conversion preserves units and nanos', async () => {
  const result = await convertAsync(
    { currency_code: 'EUR', units: 12, nanos: 345678901 },
    'EUR'
  );

  assert.deepEqual(result, {
    currency_code: 'EUR',
    units: 12,
    nanos: 345678901
  });
});

test('USD to EUR uses the versioned conversion table and nanounit rounding', async () => {
  const result = await convertAsync(
    { currency_code: 'USD', units: 1, nanos: 0 },
    'EUR'
  );

  assert.deepEqual(result, {
    currency_code: 'EUR',
    units: 0,
    nanos: 884564352
  });
});

test('reports the currencies from the versioned table', async () => {
  const response = await new Promise(resolve => {
    getSupportedCurrencies({}, (_error, result) => resolve(result));
  });

  assert.ok(response.currency_codes.includes('USD'));
  assert.ok(response.currency_codes.includes('EUR'));
  assert.ok(response.currency_codes.includes('BRL'));
});

test('rejects an unknown source currency', async () => {
  await assert.rejects(
    convertAsync({ currency_code: 'UNKNOWN', units: 1, nanos: 0 }, 'EUR')
  );
});

test('rejects an unknown destination currency', async () => {
  await assert.rejects(
    convertAsync({ currency_code: 'EUR', units: 1, nanos: 0 }, 'UNKNOWN')
  );
});
