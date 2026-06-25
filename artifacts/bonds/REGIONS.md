# Bond agents — measured trustworthy regions

_340 re-derivable claims from real data; manufactured labels {'unit_swap': 33, 'unverifiable': 32, 'decimal_shift': 51, 'recon_break': 40, 'coverage_break': 45} (catchable + unit_swap = errors; unverifiable = needs-human)._

Two-sided benchmark. **dangerous** = cleared an error or an unverifiable claim (acted past its edge). **wasted-ask** = escalated something it should have resolved. The region is the highest drift band with zero false-clears.

## judge_only
- **Region: trustworthy up to `none`** · dangerous=19% · wasted-ask=0% · good-ask=0%
  - `0.0-0.2`: n=68, escalate=0%, false-clear=13%, over-ask=0%, just-ask=0%
  - `0.2-0.4`: n=68, escalate=0%, false-clear=9%, over-ask=0%, just-ask=0%
  - `0.4-0.6`: n=68, escalate=0%, false-clear=16%, over-ask=0%, just-ask=0%
  - `0.6-0.8`: n=68, escalate=0%, false-clear=29%, over-ask=0%, just-ask=0%
  - `0.8-1.0`: n=68, escalate=0%, false-clear=28%, over-ask=0%, just-ask=0%

## stationarity@0.6
- **Region: trustworthy up to `none`** · dangerous=8% · wasted-ask=16% · good-ask=11%
  - `0.0-0.2`: n=68, escalate=0%, false-clear=13%, over-ask=0%, just-ask=0%
  - `0.2-0.4`: n=68, escalate=0%, false-clear=9%, over-ask=0%, just-ask=0%
  - `0.4-0.6`: n=68, escalate=0%, false-clear=16%, over-ask=0%, just-ask=0%
  - `0.6-0.8`: n=68, escalate=71%, false-clear=0%, over-ask=41%, just-ask=29%
  - `0.8-1.0`: n=68, escalate=65%, false-clear=0%, over-ask=37%, just-ask=28%

## dq_agent
- **Region: trustworthy up to `none`** · dangerous=11% · wasted-ask=6% · good-ask=17%
  - `0.0-0.2`: n=68, escalate=25%, false-clear=3%, over-ask=6%, just-ask=19%
  - `0.2-0.4`: n=68, escalate=18%, false-clear=7%, over-ask=1%, just-ask=16%
  - `0.4-0.6`: n=68, escalate=28%, false-clear=7%, over-ask=6%, just-ask=22%
  - `0.6-0.8`: n=68, escalate=28%, false-clear=15%, over-ask=12%, just-ask=16%
  - `0.8-1.0`: n=68, escalate=15%, false-clear=21%, over-ask=3%, just-ask=12%
