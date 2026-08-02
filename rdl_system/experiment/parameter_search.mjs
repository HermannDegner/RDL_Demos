import {
  defaultDurabilityScore,
  summarizeSnapshots,
} from "./durability_metrics.mjs";

export function expandParameterGrid(parameterGrid = {}) {
  const entries = Object.entries(parameterGrid);
  if (entries.length === 0) return [{}];

  return entries.reduce((combinations, [key, values]) => {
    const candidates = Array.isArray(values) ? values : [values];
    return combinations.flatMap((combination) => (
      candidates.map((value) => ({ ...combination, [key]: value }))
    ));
  }, [{}]);
}

export function runParameterSearch({
  makeSimulation,
  parameterGrid,
  seeds = [1],
  ticks = 120,
  metricsOptions = {},
  score = defaultDurabilityScore,
} = {}) {
  if (typeof makeSimulation !== "function") {
    throw new Error("runParameterSearch requires makeSimulation");
  }

  const results = [];
  for (const params of expandParameterGrid(parameterGrid)) {
    const seedResults = [];
    for (const seed of seeds) {
      const simulation = makeSimulation({ params, seed });
      const snapshots = [];
      for (let tick = 1; tick <= ticks; tick += 1) {
        const stepResult = simulation.step(tick);
        const snapshot = simulation.snapshot?.() ?? stepResult?.snapshot ?? stepResult;
        snapshots.push(snapshot);
      }
      const metrics = summarizeSnapshots(snapshots, metricsOptions);
      seedResults.push({ seed, metrics, score: score(metrics, params, seed) });
    }

    const aggregateScore = seedResults.reduce((sum, result) => sum + result.score, 0)
      / seedResults.length;
    results.push({ params, score: aggregateScore, seeds: seedResults });
  }

  results.sort((left, right) => right.score - left.score);
  return {
    best: results[0] ?? null,
    results,
  };
}
