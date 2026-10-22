# Research roadmap

Two possible next experiments, as **ideas only**: neither is designed, approved or started (06B's step 5). Each grows out of a result that is already in, and each would need its own proposal, tuning pilots and pre-registration, like E007–E009.

## 1. Does the preference itself evolve? (brains that see two foods)

**Where it comes from.** In E009, specialists emerged in all 20 trade-off worlds and split into two coexisting groups in 9. But the *choice* of food was designed: the diet seeker always heads for the food its diet digests best. Only the diet gene evolved.

**The idea.** Give neural organisms two foods' worth of senses (nearest food of each kind) and the diet gene, and let both the brain and the diet evolve. Does behaviour line up with diet without anyone writing the rule: organisms that digest A learning, by selection, to seek A? A split world would then need two things to coevolve inside one population, a gene and a behaviour.

**Why it might not work, and what would still be learned.** In E008, these small brains evolved evasion weakly if at all within 20,000 ticks (no detectable effect on the Mac, 14% fewer captures in the Linux replication). If preference fails to evolve too, comparing the two experiments would say something about which behaviours this kind of evolution finds easy (moving toward food: E007, yes) and hard (choosing between targets, avoiding threats).

## 2. Evasion revisited: an "ahead" input and longer exposure

**Where it comes from.** In E008, prey evolved with predators were not detectably harder to catch (−5.2%, CI including zero), though a designed flee rule cut captures by 73%. An exploratory look found a hint: in the 12 worlds where predators lasted all of training, prey were caught 9.8% less (9 of 12 worlds); where predators died out, no difference.

**The idea.** A pre-registered test of the two candidate reasons E008 named: (a) the blind spot, by adding a `predator_ahead` input (86 parameters instead of 80), and (b) exposure, by keeping predators present for the whole of a longer training run (for example, predators that can't die out, as in E008's arena). A two-by-two design, blind spot by exposure, would say which mattered.

**Why it is worth doing.** E008's two samples disagree: no detectable effect on the Mac, 14% fewer captures (p = 0.007) when the Linux replication grew different histories from the same seeds. A design aimed at the likely causes, with more worlds, would settle whether the effect is real and how large it is.
