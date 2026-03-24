# Reconciliation Truth Model

**Last updated:** 2026-03-23

This document describes current reconciliation ownership and classification behavior.

## Inputs

- `fills`: accepted fills (paper mode)
- `internal_exposure`: local exposure mirror
- `exchange_exposure`: exchange-derived exposure (live mode)
- `open_orders_state_ok`: open-order consistency flag
- `cash_ok`: balance consistency flag
- `local_realized_pnl` / `exchange_realized_pnl`: realized-PnL sanity inputs when baseline balance is known
- `local_unrealized_pnl` / `exchange_unrealized_pnl`: unrealized-PnL sanity inputs from local mirror vs exchange positions
- `truth_confidence`: per-domain confidence snapshot for fills, fees, realized PnL, balances, exposure, and market data

## Classification

| Code | Severity | Action | Meaning |
|---|---|---|---|
| `ok` | `info` | `continue` | Reconciliation passed. |
| `position_mismatch` | `critical` | `halt_and_flatten` | Local paper exposure diverged from fill-implied exposure beyond tolerance. |
| `live_position_mismatch` | `critical` | `halt_and_flatten` | Live internal exposure diverged from exchange exposure beyond tolerance. |
| `open_order_state_mismatch` | `critical` | `halt` | Paper open-order state is inconsistent. |
| `live_open_order_state_mismatch` | `critical` | `halt` | Live open-order state is inconsistent. |
| `cash_mismatch` | `critical` | `halt` | Paper cash consistency check failed. |
| `live_cash_mismatch` | `critical` | `halt` | Live balance consistency check failed. |
| `realized_pnl_mismatch` | `critical` | `halt` | Paper realized-PnL ledger diverged from comparison truth. |
| `live_realized_pnl_mismatch` | `critical` | `halt` | Live realized PnL diverged from exchange-native income/account-history truth. |
| `unrealized_pnl_mismatch` | `warning` | `alert` | Paper unrealized-PnL sanity check failed. |
| `live_unrealized_pnl_mismatch` | `warning` | `alert` | Live unrealized-PnL diverged from exchange position marks. |
| `live_fill_truth_proxy` | `warning` | `degrade` | Fill truth is only partially recovered or backfilled. |
| `live_fee_truth_unavailable` | `critical` | `flatten_only` | Fee truth owner exists but current evidence is unavailable. |
| `live_realized_pnl_truth_unavailable` | `critical` | `flatten_only` | Realized-PnL truth owner exists but current evidence is unavailable. |
| `stale_snapshots` | `warning/critical` | `degrade/flatten_only` | Account or market snapshots are stale enough that reconciliation cannot be trusted. |

## Tolerances

- Paper exposure tolerance: `max(1.0, abs(expected_exposure) * 0.3)`
- Live exposure tolerance: `max(2.0, abs(exchange_exposure) * 0.1)`
- Realized PnL tolerance: `max(2.0, abs(exchange_realized_pnl) * 0.2)`
- Unrealized PnL tolerance: `max(2.0, abs(exchange_unrealized_pnl) * 0.25)`

## Runtime behavior

- Paper path emits reconciliation mismatch risk events with `severity`, `action`, and `details`.
- Live path emits a full accounting judgment first, then adapts it into the legacy reconciliation outcome.
- Live path fail-closes into `degrade`, `flatten_only`, `halt`, or `halt_and_flatten` based on both mismatch severity and domain truth confidence.
- Live reconciliation now includes a balance-state check when connector supports `balances()`.
- Live reconciliation now also compares local unrealized PnL to exchange-reported unrealized PnL.
- Live reconciliation now prefers exchange-native realized-PnL history (`income_history` on Binance, `account_log` on Kraken) over balance-derived proxies.
- Restart rehydration can backfill missing local fill history from exchange-native history before reconciliation confidence is classified.

## Confidence-aware actions

- authoritative fill/fee/realized-PnL mismatches can halt or halt-and-flatten
- proxy fill/fee/realized-PnL truth degrades the run rather than passing silently
- unavailable fill/fee/realized-PnL truth forces `flatten_only`
- stale market/account snapshots degrade or flatten depending on age and combined exposure/accounting risk

## Known limits

- Paper `cash_ok` currently remains a synthetic check (no real cash ledger).
- Live cash check is currently coarse (`balance_non_positive`, `balance_empty`, fetch error classes).
- Live unrealized-PnL sanity is still based on exchange position marks, not a dedicated exchange-native unrealized-PnL history feed.
