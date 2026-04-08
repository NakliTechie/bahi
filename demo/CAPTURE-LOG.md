# Capture run — 2026-04-08 09:58:08

**Summary**: 113/115 routes rendered ok · 0 total console errors

> The two "empty" rows are `#/stock-aging` on pharma and manufacturing. This is not a failure — the route renders correctly but shows its empty-state panel ("No aged batch stock.") because the sample data does not seed batch-tracked stock old enough to appear in any aging bucket. Screenshots are still captured and included in the demo.

## pharma.khata

| # | Route | Status | ms | Console errors |
|---|---|---|---|---|
| 01 | `#/dashboard` | ok | 816 | — |
| 02 | `#/file` | ok | 496 | — |
| 03 | `#/customers` | ok | 525 | — |
| 04 | `#/vendors` | ok | 519 | — |
| 05 | `#/items` | ok | 510 | — |
| 06 | `#/series` | ok | 486 | — |
| 07 | `#/invoices` | ok | 621 | — |
| 08 | `#/invoice/new` | ok | 585 | — |
| 09 | `#/credit-notes` | ok | 499 | — |
| 10 | `#/credit-note/new` | ok | 593 | — |
| 11 | `#/purchases` | ok | 633 | — |
| 12 | `#/purchase/new` | ok | 593 | — |
| 13 | `#/debit-notes` | ok | 481 | — |
| 14 | `#/debit-note/new` | ok | 591 | — |
| 15 | `#/payments` | ok | 634 | — |
| 16 | `#/payment/new` | ok | 597 | — |
| 17 | `#/vendor-payment/new` | ok | 591 | — |
| 18 | `#/tcs-collection/new` | ok | 592 | — |
| 19 | `#/advances` | ok | 486 | — |
| 20 | `#/advance/new` | ok | 595 | — |
| 21 | `#/inventory` | ok | 589 | — |
| 22 | `#/stock-on-hand` | ok | 578 | — |
| 23 | `#/stock-movements` | ok | 586 | — |
| 24 | `#/stock-register` | ok | 580 | — |
| 25 | `#/batches` | ok | 481 | — |
| 26 | `#/valuation-summary` | ok | 603 | — |
| 27 | `#/reorder-alerts` | ok | 479 | — |
| 28 | `#/stock-aging` | empty | 582 | — |
| 29 | `#/godowns` | ok | 486 | — |
| 30 | `#/delivery-challans` | ok | 482 | — |
| 31 | `#/delivery-challan/new` | ok | 593 | — |
| 32 | `#/eway-bills` | ok | 478 | — |
| 33 | `#/eway-bill/new` | ok | 588 | — |
| 34 | `#/stock-transfers` | ok | 488 | — |
| 35 | `#/stock-transfer/out/new` | ok | 595 | — |
| 36 | `#/stock-transfer/in/import` | ok | 586 | — |
| 37 | `#/journal/new` | ok | 588 | — |
| 38 | `#/bank-reconcile` | ok | 681 | — |
| 39 | `#/day-book` | ok | 586 | — |
| 40 | `#/account-ledger` | ok | 584 | — |
| 41 | `#/trial-balance` | ok | 684 | — |
| 42 | `#/balance-sheet` | ok | 682 | — |
| 43 | `#/pnl` | ok | 691 | — |
| 44 | `#/sales-register` | ok | 582 | — |
| 45 | `#/purchase-register` | ok | 594 | — |
| 46 | `#/gstr1` | ok | 799 | — |
| 47 | `#/gstr3b` | ok | 790 | — |
| 48 | `#/cmp08` | ok | 586 | — |
| 49 | `#/form-26q` | ok | 786 | — |
| 50 | `#/form-27eq` | ok | 589 | — |
| 51 | `#/form-27d` | ok | 580 | — |
| 52 | `#/tax-challans` | ok | 616 | — |
| 53 | `#/period-locks` | ok | 488 | — |
| 54 | `#/fy-rollover` | ok | 587 | — |
| 55 | `#/annotations` | ok | 485 | — |
| 56 | `#/settings` | ok | 520 | — |
| 57 | `#/debug` | ok | 511 | — |
| 58 | `#/workspace` | ok | 481 | — |

## manufacturing.khata

| # | Route | Status | ms | Console errors |
|---|---|---|---|---|
| 01 | `#/dashboard` | ok | 821 | — |
| 02 | `#/file` | ok | 512 | — |
| 03 | `#/invoices` | ok | 632 | — |
| 04 | `#/customers` | ok | 520 | — |
| 05 | `#/vendors` | ok | 503 | — |
| 06 | `#/items` | ok | 510 | — |
| 07 | `#/purchases` | ok | 638 | — |
| 08 | `#/inventory` | ok | 589 | — |
| 09 | `#/stock-on-hand` | ok | 574 | — |
| 10 | `#/stock-movements` | ok | 590 | — |
| 11 | `#/valuation-summary` | ok | 605 | — |
| 12 | `#/stock-aging` | empty | 585 | — |
| 13 | `#/stock-register` | ok | 591 | — |
| 14 | `#/delivery-challans` | ok | 486 | — |
| 15 | `#/eway-bills` | ok | 482 | — |
| 16 | `#/stock-transfers` | ok | 487 | — |
| 17 | `#/godowns` | ok | 493 | — |
| 18 | `#/trial-balance` | ok | 687 | — |
| 19 | `#/balance-sheet` | ok | 694 | — |
| 20 | `#/pnl` | ok | 702 | — |
| 21 | `#/gstr1` | ok | 804 | — |
| 22 | `#/gstr3b` | ok | 801 | — |

## consulting.khata

| # | Route | Status | ms | Console errors |
|---|---|---|---|---|
| 01 | `#/dashboard` | ok | 814 | — |
| 02 | `#/file` | ok | 514 | — |
| 03 | `#/invoices` | ok | 643 | — |
| 04 | `#/customers` | ok | 500 | — |
| 05 | `#/items` | ok | 517 | — |
| 06 | `#/credit-notes` | ok | 488 | — |
| 07 | `#/payments` | ok | 651 | — |
| 08 | `#/advances` | ok | 501 | — |
| 09 | `#/journal/new` | ok | 611 | — |
| 10 | `#/day-book` | ok | 595 | — |
| 11 | `#/trial-balance` | ok | 699 | — |
| 12 | `#/balance-sheet` | ok | 700 | — |
| 13 | `#/pnl` | ok | 714 | — |
| 14 | `#/sales-register` | ok | 584 | — |
| 15 | `#/gstr1` | ok | 801 | — |
| 16 | `#/gstr3b` | ok | 816 | — |
| 17 | `#/form-26q` | ok | 807 | — |

## ca-audit (across 3 files)

| # | Route | Status | ms | Console errors |
|---|---|---|---|---|
| 01 | `#/dashboard` | ok | 830 | — |
| 02 | `#/trial-balance` | ok | 816 | — |
| 03 | `#/balance-sheet` | ok | 807 | — |
| 04 | `#/pnl` | ok | 813 | — |
| 05 | `#/day-book` | ok | 687 | — |
| 06 | `#/ca/review` | ok | 733 | — |
| 07 | `#/annotations` | ok | 595 | — |
| 08 | `#/ca/report` | ok | 692 | — |
| 09 | `#/dashboard` | ok | 818 | — |
| 10 | `#/trial-balance` | ok | 802 | — |
| 11 | `#/balance-sheet` | ok | 789 | — |
| 12 | `#/pnl` | ok | 801 | — |
| 13 | `#/ca/review` | ok | 749 | — |
| 14 | `#/dashboard` | ok | 820 | — |
| 15 | `#/trial-balance` | ok | 794 | — |
| 16 | `#/balance-sheet` | ok | 810 | — |
| 17 | `#/pnl` | ok | 798 | — |
| 18 | `#/ca/adjustment/new` | ok | 702 | — |
