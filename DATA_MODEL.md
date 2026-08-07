# Data model

## participant_submissions
One row per individual submission. A UUID-based submission ID prevents collisions.

## breakout_consensus
One row per breakout code. Saving a breakout consensus replaces the prior consensus for that breakout.

## Agreement indicator
Calculated from the population standard deviation of allocations:
- High: <= 8 units
- Medium: > 8 and <= 15 units
- Low: > 15 units

These thresholds are workshop heuristics and can be changed in `agreement_label()` in `app.py`.
