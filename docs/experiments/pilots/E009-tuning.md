# E009 tuning pilots (6.10)

**Tuning, not results.** These pilots chose E009's food energy before E009 was defined. They report only whether populations survive and how large they are, never anything about the diet, which is what E009 measures. Seeds 90100–90105, which no experiment uses.

Script: [`experiments/pilots/e009_tuning.py`](../../../experiments/pilots/e009_tuning.py). Each pilot is `configs/diets.yaml` in one of the three conditions (`tradeoff`: k = 2; `neutral`: the diet has no effect; `linear`: k = 1) with `food.energy_value` V = 60, 80 or 100, run for 20,000 ticks.

## What it showed

- **Every population survived** at every V and in every condition (54 of 54 runs), so survival doesn't constrain V. **V = 80** is kept: a generalist (d = 0.5) then keeps 20 EU per meal, the meal of every earlier world.
- **Neutral worlds settle at about half the population** of the other two (at V = 80, median 90 against 182). A smaller population drifts more, which would spread the diet more in the neutral control. This works *against* E009's hypothesis (more spread with a trade-off), not for it.

## Output

```text
20000 ticks, seeds 90100-90105 (survival only)

    V  condition  survived  died out on ticks     final population
   60  tradeoff       6/6  -                     77-161 (median 132)
   60  neutral        6/6  -                     61-79 (median 73)
   60  linear         6/6  -                     131-155 (median 136)
   80  tradeoff       6/6  -                     157-206 (median 182)
   80  neutral        6/6  -                     85-103 (median 90)
   80  linear         6/6  -                     162-205 (median 182)
  100  tradeoff       6/6  -                     191-246 (median 224)
  100  neutral        6/6  -                     106-125 (median 118)
  100  linear         6/6  -                     199-257 (median 228)
```
