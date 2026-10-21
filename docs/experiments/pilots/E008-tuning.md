# E008 tuning pilots (6.6)

**Tuning, not results.** These pilots chose the settings E008 will use, before E008 was defined. They answer only "which settings keep predators and prey both alive?", never E008's question (do prey evolve to escape predators?). They use seeds 90000 and up, which no experiment uses. Nothing here is evidence for or against any hypothesis.

Script: [`experiments/pilots/e008_tuning.py`](../../../experiments/pilots/e008_tuning.py) (`--round 1` to `--round 4`; each round reproduces exactly). Every pilot is `configs/predators.yaml` (neural prey) with the settings shown changed. "both" counts seeds that kept both species to the end; "prey out" and "pred out" are the median tick a species died out, over the seeds where it did; "prey" and "pred" are mean numbers over the last fifth of the runs that kept both; "caught" is mean captures per run.

## What each round showed

| Round | Question | Answer |
|---|---|---|
| 1 | Span from the placeholders (which overkill) to clearly weak predators: 64 settings, chasers and neural predators, 10,000 ticks | At best 2 of 6 seeds kept both. Prey often died out after few captures (26 in one setting). |
| (check) | Why do prey die out after so few captures? | Prey alone dip from 30 to 17-30 in their first ~400 ticks (random founder brains are weeded out) before settling near 100. Predators arriving in that dip finish them. |
| 2 | Does starting with 100 prey avoid the dip? | Yes: weak chasers (catch chance 0.1) never ended the prey. Failures became small predator populations dying out. Neural predators starved in every seed. |
| 3 | A cap on predators (limits booms) with 100 prey, 20,000 ticks (E007's training length) | Best: 4 chasers, catch chance 0.18, cap 10: 4 of 6. Neural predators starved within ~400-800 ticks in all 72 pilots. |
| 4 | Round 3's two best on 12 seeds | **4 chasers, catch chance 0.18, cap 10: prey never died out; both species to tick 20,000 in 7 of 12; where predators died out, they lasted until tick 15,780-19,926.** |

## The settings proposed for E008 (to be fixed in its definition)

Prey: `neural.yaml`'s prey with **100 founders** (initial energy, costs and genes unchanged). Predators: `nearest_prey_seeker`, **4 founders, cap 10**, speed 1.5 (as prey), capture probability **0.18**, capture efficiency **0.5**, reproduction threshold **240** (offspring 80, overhead 20), other predator settings as `predators.yaml`.

**Neural predators** were not viable at any setting tried: random predator brains can't catch enough to survive long enough for selection to improve them (they starved within ~800 ticks, after 8-24 captures, in every pilot of rounds 1-3).

## Round outputs

### Round 1

```text
round 1: 10000 ticks, seeds 90000-90005
fixed for this round: none

predators           setting                                       both  prey out  pred out   prey  pred  caught
nearest_prey_seeker n=3 p=0.1 speed=1.8 eff=0.8 thresh=160        2/6          -       503     58    16     955
                      per seed: pred 473, pred 689, both, pred 533, pred 455, both
nearest_prey_seeker n=6 p=0.1 speed=1.5 eff=0.8 thresh=160        2/6        567       622     74     9     830
                      per seed: both, pred 702, prey 2333, prey 567, both, prey 479
nearest_prey_seeker n=3 p=0.1 speed=1.5 eff=0.5 thresh=160        1/6          -       641     71     8     334
                      per seed: pred 641, pred 420, both, pred 1477, pred 761, pred 415
nearest_prey_seeker n=3 p=0.1 speed=1.5 eff=0.5 thresh=240        1/6          -       641     90     1     158
                      per seed: pred 641, pred 420, both, pred 1477, pred 761, pred 415
nearest_prey_seeker n=3 p=0.1 speed=1.5 eff=0.8 thresh=160        1/6       1843       489     50    23     579
                      per seed: pred 457, pred 384, both, pred 532, prey 1843, pred 489
nearest_prey_seeker n=3 p=0.1 speed=1.5 eff=0.8 thresh=240        1/6       3443      3303     68    14     667
                      per seed: both, pred 555, prey 2966, pred 966, prey 3502, prey 3443
nearest_prey_seeker n=3 p=0.1 speed=1.8 eff=0.5 thresh=160        1/6        467       387     72     8     238
                      per seed: pred 355, pred 543, both, pred 355, prey 467, pred 387
nearest_prey_seeker n=3 p=0.1 speed=1.8 eff=0.5 thresh=240        1/6        467       450     65     9     319
                      per seed: pred 355, pred 543, both, pred 455, prey 467, pred 387
nearest_prey_seeker n=3 p=0.25 speed=1.5 eff=0.5 thresh=240       1/6       2949      3159     58    13     834
                      per seed: both, pred 700, prey 3015, prey 2883, prey 771, prey 3505
nearest_prey_seeker n=3 p=0.25 speed=1.8 eff=0.5 thresh=240       1/6        242       852     58     7     527
                      per seed: prey 275, pred 852, pred 2247, pred 1053, prey 209, both
nearest_prey_seeker n=6 p=0.1 speed=1.5 eff=0.8 thresh=240        1/6        277       571     55    18     484
                      per seed: prey 245, pred 507, prey 2568, both, pred 665, prey 277
nearest_prey_seeker n=6 p=0.25 speed=1.5 eff=0.5 thresh=160       1/6        241       474     75     6     369
                      per seed: prey 241, prey 203, prey 247, both, prey 192, prey 364
nearest_prey_seeker n=6 p=0.25 speed=1.8 eff=0.5 thresh=160       1/6        186       418     67     7     424
                      per seed: prey 186, pred 406, pred 434, prey 344, both, prey 164
neural              n=6 p=0.25 speed=1.8 eff=0.8 thresh=240       1/6          -       442     74    11     453
                      per seed: both, pred 294, pred 442, pred 381, pred 543, pred 1009
nearest_prey_seeker n=3 p=0.1 speed=1.8 eff=0.8 thresh=240        0/6       3648      2139      -     -     678
                      per seed: pred 473, prey 3390, prey 3905, pred 520, prey 795, prey 7369
nearest_prey_seeker n=3 p=0.25 speed=1.5 eff=0.5 thresh=160       0/6       1868       566      -     -     158
                      per seed: pred 734, pred 700, prey 2877, pred 431, prey 859, pred 402
nearest_prey_seeker n=3 p=0.25 speed=1.5 eff=0.8 thresh=160       0/6        560       604      -     -      59
                      per seed: pred 1524, pred 409, pred 630, pred 772, prey 630, prey 491
nearest_prey_seeker n=3 p=0.25 speed=1.5 eff=0.8 thresh=240       0/6       1244      1240      -     -     228
                      per seed: prey 1366, prey 3001, prey 2501, prey 1123, prey 859, prey 517
nearest_prey_seeker n=3 p=0.25 speed=1.8 eff=0.5 thresh=160       0/6        378       488      -     -     504
                      per seed: pred 413, pred 852, prey 8787, prey 398, prey 357, prey 305
nearest_prey_seeker n=3 p=0.25 speed=1.8 eff=0.8 thresh=160       0/6        411       653      -     -     117
                      per seed: prey 266, pred 785, prey 342, prey 411, prey 633, prey 2331
nearest_prey_seeker n=3 p=0.25 speed=1.8 eff=0.8 thresh=240       0/6       1356      1026      -     -     210
                      per seed: pred 549, prey 1727, prey 3068, pred 708, prey 283, prey 984
nearest_prey_seeker n=6 p=0.1 speed=1.5 eff=0.5 thresh=160        0/6        261       435      -     -      26
                      per seed: prey 245, pred 398, pred 540, pred 411, pred 734, prey 277
nearest_prey_seeker n=6 p=0.1 speed=1.5 eff=0.5 thresh=240        0/6        261       432      -     -      21
                      per seed: prey 245, pred 398, pred 452, pred 411, pred 497, prey 277
nearest_prey_seeker n=6 p=0.1 speed=1.8 eff=0.5 thresh=160        0/6        836       409      -     -      22
                      per seed: pred 415, pred 374, pred 412, pred 406, pred 349, prey 836
nearest_prey_seeker n=6 p=0.1 speed=1.8 eff=0.5 thresh=240        0/6       4203       410      -     -      21
                      per seed: pred 415, pred 374, pred 462, pred 406, pred 349, prey 4203
nearest_prey_seeker n=6 p=0.1 speed=1.8 eff=0.8 thresh=160        0/6        328       471      -     -      24
                      per seed: prey 370, pred 396, pred 528, pred 403, pred 533, prey 285
nearest_prey_seeker n=6 p=0.1 speed=1.8 eff=0.8 thresh=240        0/6        490       660      -     -      26
                      per seed: pred 1087, pred 488, pred 578, pred 727, pred 678, prey 490
nearest_prey_seeker n=6 p=0.25 speed=1.5 eff=0.5 thresh=240       0/6        433       484      -     -      27
                      per seed: pred 564, prey 203, prey 705, pred 467, prey 467, prey 399
nearest_prey_seeker n=6 p=0.25 speed=1.5 eff=0.8 thresh=160       0/6        299       450      -     -      64
                      per seed: prey 299, prey 1829, prey 242, prey 310, pred 414, prey 171
nearest_prey_seeker n=6 p=0.25 speed=1.5 eff=0.8 thresh=240       0/6        345       588      -     -      28
                      per seed: prey 369, prey 204, prey 231, prey 457, prey 467, prey 321
nearest_prey_seeker n=6 p=0.25 speed=1.8 eff=0.5 thresh=240       0/6        294       454      -     -     176
                      per seed: prey 270, pred 438, prey 294, prey 344, prey 3623, prey 170
nearest_prey_seeker n=6 p=0.25 speed=1.8 eff=0.8 thresh=160       0/6        198       414      -     -      30
                      per seed: prey 177, pred 480, prey 193, pred 365, prey 207, prey 202
nearest_prey_seeker n=6 p=0.25 speed=1.8 eff=0.8 thresh=240       0/6        292       588      -     -      81
                      per seed: prey 230, prey 451, prey 241, prey 344, prey 1473, prey 161
neural              n=3 p=0.1 speed=1.5 eff=0.5 thresh=160        0/6          -       294      -     -       4
                      per seed: pred 298, pred 282, pred 337, pred 291, pred 955, pred 280
neural              n=3 p=0.1 speed=1.5 eff=0.5 thresh=240        0/6          -       288      -     -       2
                      per seed: pred 295, pred 278, pred 487, pred 269, pred 331, pred 280
neural              n=3 p=0.1 speed=1.5 eff=0.8 thresh=160        0/6          -       326      -     -       2
                      per seed: pred 326, pred 282, pred 343, pred 327, pred 688, pred 280
neural              n=3 p=0.1 speed=1.5 eff=0.8 thresh=240        0/6          -       298      -     -       2
                      per seed: pred 317, pred 278, pred 538, pred 271, pred 486, pred 280
neural              n=3 p=0.1 speed=1.8 eff=0.5 thresh=160        0/6          -       293      -     -       2
                      per seed: pred 291, pred 277, pred 295, pred 314, pred 542, pred 276
neural              n=3 p=0.1 speed=1.8 eff=0.5 thresh=240        0/6          -       284      -     -       1
                      per seed: pred 292, pred 274, pred 306, pred 264, pred 335, pred 276
neural              n=3 p=0.1 speed=1.8 eff=0.8 thresh=160        0/6          -       318      -     -       1
                      per seed: pred 313, pred 277, pred 322, pred 330, pred 460, pred 276
neural              n=3 p=0.1 speed=1.8 eff=0.8 thresh=240        0/6          -       301      -     -       1
                      per seed: pred 326, pred 274, pred 572, pred 264, pred 327, pred 276
neural              n=3 p=0.25 speed=1.5 eff=0.5 thresh=160       0/6       5266       344      -     -       3
                      per seed: pred 298, pred 311, pred 376, pred 291, pred 478, prey 5266
neural              n=3 p=0.25 speed=1.5 eff=0.5 thresh=240       0/6          -       318      -     -       2
                      per seed: pred 372, pred 278, pred 388, pred 269, pred 329, pred 307
neural              n=3 p=0.25 speed=1.5 eff=0.8 thresh=160       0/6          -       388      -     -       7
                      per seed: pred 326, pred 329, pred 1250, pred 327, pred 1042, pred 447
neural              n=3 p=0.25 speed=1.5 eff=0.8 thresh=240       0/6          -       397      -     -       2
                      per seed: pred 443, pred 278, pred 436, pred 271, pred 398, pred 396
neural              n=3 p=0.25 speed=1.8 eff=0.5 thresh=160       0/6          -       324      -     -       4
                      per seed: pred 302, pred 277, pred 581, pred 315, pred 439, pred 332
neural              n=3 p=0.25 speed=1.8 eff=0.5 thresh=240       0/6          -       308      -     -       3
                      per seed: pred 300, pred 274, pred 724, pred 264, pred 315, pred 335
neural              n=3 p=0.25 speed=1.8 eff=0.8 thresh=160       0/6          -       412      -     -       2
                      per seed: pred 458, pred 277, pred 468, pred 330, pred 474, pred 367
neural              n=3 p=0.25 speed=1.8 eff=0.8 thresh=240       0/6          -       347      -     -       2
                      per seed: pred 324, pred 274, pred 582, pred 264, pred 387, pred 370
neural              n=6 p=0.1 speed=1.5 eff=0.5 thresh=160        0/6          -       344      -     -       4
                      per seed: pred 388, pred 280, pred 341, pred 336, pred 419, pred 346
neural              n=6 p=0.1 speed=1.5 eff=0.5 thresh=240        0/6          -       314      -     -       4
                      per seed: pred 295, pred 280, pred 404, pred 289, pred 433, pred 333
neural              n=6 p=0.1 speed=1.5 eff=0.8 thresh=160        0/6          -       334      -     -       8
                      per seed: pred 1037, pred 280, pred 366, pred 269, pred 882, pred 301
neural              n=6 p=0.1 speed=1.5 eff=0.8 thresh=240        0/6          -       572      -     -      15
                      per seed: pred 2749, pred 280, pred 751, pred 316, pred 724, pred 420
neural              n=6 p=0.1 speed=1.8 eff=0.5 thresh=160        0/6          -       322      -     -       4
                      per seed: pred 267, pred 276, pred 472, pred 302, pred 568, pred 342
neural              n=6 p=0.1 speed=1.8 eff=0.5 thresh=240        0/6          -       314      -     -       2
                      per seed: pred 268, pred 274, pred 410, pred 302, pred 367, pred 325
neural              n=6 p=0.1 speed=1.8 eff=0.8 thresh=160        0/6          -       423      -     -       6
                      per seed: pred 267, pred 276, pred 820, pred 336, pred 788, pred 510
neural              n=6 p=0.1 speed=1.8 eff=0.8 thresh=240        0/6          -       361      -     -       3
                      per seed: pred 268, pred 274, pred 529, pred 359, pred 426, pred 363
neural              n=6 p=0.25 speed=1.5 eff=0.5 thresh=160       0/6          -       360      -     -       4
                      per seed: pred 343, pred 280, pred 367, pred 396, pred 353, pred 372
neural              n=6 p=0.25 speed=1.5 eff=0.5 thresh=240       0/6          -       354      -     -      29
                      per seed: pred 2594, pred 299, pred 1619, pred 289, pred 381, pred 327
neural              n=6 p=0.25 speed=1.5 eff=0.8 thresh=160       0/6          -       585      -     -      52
                      per seed: pred 5327, pred 280, pred 493, pred 277, pred 1423, pred 677
neural              n=6 p=0.25 speed=1.5 eff=0.8 thresh=240       0/6          -       508      -     -     106
                      per seed: pred 4551, pred 320, pred 1575, pred 316, pred 658, pred 358
neural              n=6 p=0.25 speed=1.8 eff=0.5 thresh=160       0/6          -       383      -     -       7
                      per seed: pred 475, pred 276, pred 406, pred 302, pred 419, pred 360
neural              n=6 p=0.25 speed=1.8 eff=0.5 thresh=240       0/6          -       387      -     -       6
                      per seed: pred 356, pred 277, pred 418, pred 302, pred 435, pred 494
neural              n=6 p=0.25 speed=1.8 eff=0.8 thresh=160       0/6          -       510      -     -      48
                      per seed: pred 4285, pred 286, pred 626, pred 336, pred 768, pred 394
```

### Round 2

```text
round 2: 10000 ticks, seeds 90000-90005
fixed for this round: organisms.initial_count 100, predators.genome.speed.initial 1.5, predators.capture_efficiency 0.5

predators           setting                                       both  prey out  pred out   prey  pred  caught
nearest_prey_seeker n=6 p=0.1 thresh=240                          4/6          -      6353     89     3    1134
                      per seed: pred 7620, both, both, both, pred 5086, both
nearest_prey_seeker n=3 p=0.1 thresh=240                          3/6          -      6088     82     4     991
                      per seed: both, pred 6088, pred 8893, both, pred 5071, both
nearest_prey_seeker n=3 p=0.25 thresh=240                         3/6       1116      1477     79     5    1118
                      per seed: both, prey 2218, both, prey 949, both, prey 1116
nearest_prey_seeker n=6 p=0.1 thresh=160                          3/6          -      2691     86     3     687
                      per seed: pred 4109, both, pred 2691, both, pred 1974, both
nearest_prey_seeker n=6 p=0.25 thresh=160                         3/6        335       614     71     8    1294
                      per seed: pred 614, both, both, pred 721, prey 335, both
nearest_prey_seeker n=3 p=0.25 thresh=160                         1/6       7115      7189     66    10    1461
                      per seed: pred 3234, both, prey 7115, pred 987, pred 8692, pred 9459
neural              n=6 p=0.25 thresh=240                         1/6          -       820     91     1      75
                      per seed: both, pred 767, pred 1003, pred 377, pred 995, pred 820
nearest_prey_seeker n=3 p=0.1 thresh=160                          0/6          -      4025      -     -     458
                      per seed: pred 3913, pred 8023, pred 7489, pred 1746, pred 1936, pred 4137
nearest_prey_seeker n=6 p=0.25 thresh=240                         0/6        720      1097      -     -     441
                      per seed: prey 3184, prey 3893, prey 634, prey 442, prey 552, prey 807
neural              n=3 p=0.1 thresh=160                          0/6          -       442      -     -      11
                      per seed: pred 663, pred 307, pred 573, pred 296, pred 597, pred 312
neural              n=3 p=0.1 thresh=240                          0/6          -       426      -     -       7
                      per seed: pred 457, pred 359, pred 443, pred 494, pred 409, pred 405
neural              n=3 p=0.25 thresh=160                         0/6          -       684      -     -      20
                      per seed: pred 732, pred 697, pred 1021, pred 299, pred 670, pred 321
neural              n=3 p=0.25 thresh=240                         0/6          -       558      -     -      17
                      per seed: pred 1339, pred 640, pred 802, pred 476, pred 437, pred 332
neural              n=6 p=0.1 thresh=160                          0/6          -       458      -     -      11
                      per seed: pred 566, pred 537, pred 441, pred 392, pred 476, pred 430
neural              n=6 p=0.1 thresh=240                          0/6          -       406      -     -      10
                      per seed: pred 565, pred 349, pred 355, pred 413, pred 511, pred 399
neural              n=6 p=0.25 thresh=160                         0/6          -       592      -     -      32
                      per seed: pred 2321, pred 392, pred 635, pred 336, pred 548, pred 956
```

### Round 3

```text
round 3: 20000 ticks, seeds 90000-90005
fixed for this round: organisms.initial_count 100, predators.genome.speed.initial 1.5, predators.capture_efficiency 0.5, predators.genome.reproduction_threshold.initial 240

predators           setting                                       both  prey out  pred out   prey  pred  caught
nearest_prey_seeker n=4 p=0.18 cap=10                             4/6          -     19777     77     5    3907
                      per seed: both, pred 19628, both, both, both, pred 19926
nearest_prey_seeker n=8 p=0.12 cap=10                             4/6          -     15392     80     4    2624
                      per seed: pred 13635, both, both, both, both, pred 17150
nearest_prey_seeker n=4 p=0.18 cap=20                             3/6       1256     10356     78     5    2952
                      per seed: both, pred 10356, both, prey 1256, both, pred 13282
nearest_prey_seeker n=8 p=0.18 cap=10                             3/6        599     15481     77     5    3608
                      per seed: both, pred 15481, both, pred 18740, prey 599, both
nearest_prey_seeker n=8 p=0.18 cap=20                             3/6        599     16537     70     7    3919
                      per seed: both, pred 16537, both, both, prey 599, pred 18446
nearest_prey_seeker n=8 p=0.12 cap=20                             2/6          -     15968     87     3    2316
                      per seed: pred 7439, pred 14464, pred 17471, pred 19875, both, both
nearest_prey_seeker n=4 p=0.12 cap=10                             1/6          -     14682     87     1    2171
                      per seed: pred 14682, both, pred 18840, pred 15900, pred 5233, pred 12025
nearest_prey_seeker n=4 p=0.12 cap=20                             1/6          -     12279     95     1    1915
                      per seed: pred 14682, pred 18718, pred 12279, pred 8735, pred 5233, both
nearest_prey_seeker n=4 p=0.08 cap=10                             0/6          -      7158      -     -     371
                      per seed: pred 8279, pred 4263, pred 7317, pred 7876, pred 2152, pred 6998
nearest_prey_seeker n=4 p=0.08 cap=20                             0/6          -      7158      -     -     371
                      per seed: pred 8279, pred 4263, pred 7317, pred 7876, pred 2152, pred 6998
nearest_prey_seeker n=8 p=0.08 cap=10                             0/6          -      6000      -     -     665
                      per seed: pred 6188, pred 2602, pred 7057, pred 5813, pred 4836, pred 14401
nearest_prey_seeker n=8 p=0.08 cap=20                             0/6          -      6000      -     -     665
                      per seed: pred 6188, pred 2602, pred 7057, pred 5813, pred 4836, pred 14401
neural              n=4 p=0.08 cap=10                             0/6          -       402      -     -       8
                      per seed: pred 508, pred 419, pred 738, pred 386, pred 384, pred 349
neural              n=4 p=0.08 cap=20                             0/6          -       402      -     -       8
                      per seed: pred 508, pred 419, pred 738, pred 386, pred 384, pred 349
neural              n=4 p=0.12 cap=10                             0/6          -       501      -     -      12
                      per seed: pred 533, pred 353, pred 672, pred 386, pred 514, pred 488
neural              n=4 p=0.12 cap=20                             0/6          -       501      -     -      12
                      per seed: pred 533, pred 353, pred 672, pred 386, pred 514, pred 488
neural              n=4 p=0.18 cap=10                             0/6          -       487      -     -      16
                      per seed: pred 874, pred 353, pred 808, pred 401, pred 573, pred 373
neural              n=4 p=0.18 cap=20                             0/6          -       487      -     -      16
                      per seed: pred 874, pred 353, pred 808, pred 401, pred 573, pred 373
neural              n=8 p=0.08 cap=10                             0/6          -       462      -     -      10
                      per seed: pred 502, pred 365, pred 481, pred 396, pred 467, pred 456
neural              n=8 p=0.08 cap=20                             0/6          -       462      -     -      10
                      per seed: pred 502, pred 365, pred 481, pred 396, pred 467, pred 456
neural              n=8 p=0.12 cap=10                             0/6          -       453      -     -      15
                      per seed: pred 688, pred 422, pred 583, pred 396, pred 391, pred 484
neural              n=8 p=0.12 cap=20                             0/6          -       453      -     -      15
                      per seed: pred 688, pred 422, pred 583, pred 396, pred 391, pred 484
neural              n=8 p=0.18 cap=10                             0/6          -       794      -     -      24
                      per seed: pred 800, pred 422, pred 787, pred 602, pred 1031, pred 905
neural              n=8 p=0.18 cap=20                             0/6          -       794      -     -      24
                      per seed: pred 800, pred 422, pred 787, pred 602, pred 1031, pred 905
```

### Round 4

```text
round 4: 20000 ticks, seeds 90000-90011
fixed for this round: organisms.initial_count 100, predators.genome.speed.initial 1.5, predators.capture_efficiency 0.5, predators.genome.reproduction_threshold.initial 240, predators.max_population 10

predators           setting                                       both  prey out  pred out   prey  pred  caught
nearest_prey_seeker n=4 p=0.18                                    7/12         -     17362     75     6    3596
                      per seed: both, pred 19628, both, both, both, pred 19926, pred 17362, pred 16006, both, pred 15780, both, both
nearest_prey_seeker n=8 p=0.18                                    5/12       599     10064     75     6    2970
                      per seed: both, pred 15481, both, pred 18740, prey 599, both, pred 738, pred 10064, both, pred 19951, pred 789, both
nearest_prey_seeker n=8 p=0.12                                    4/12       477      6736     80     4    1811
                      per seed: pred 13635, both, both, both, both, pred 17150, prey 477, pred 4084, pred 7009, pred 6462, pred 931, pred 17214
nearest_prey_seeker n=4 p=0.12                                    1/12         -     10980     87     1    1773
                      per seed: pred 14682, both, pred 18840, pred 15900, pred 5233, pred 12025, pred 5261, pred 10980, pred 9791, pred 16014, pred 8787, pred 10626
```
