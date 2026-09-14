function average(values) {
  if (values.length === 0) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function maxValue(record = {}) {
  return Math.max(0, ...Object.values(record).map((value) => Math.abs(value)));
}

export function summarizeSnapshots(snapshots, {
  adaptationPressureMax = 1.2,
  adaptationPressureSaturationRatio = 0.95,
  hSilenceThreshold = 0.01,
  reliabilityCollapseThreshold = 0.2,
} = {}) {
  if (!Array.isArray(snapshots) || snapshots.length === 0) {
    return {
      ticks: 0,
      leapRate: 0,
      adaptationPressureSaturationRate: 0,
      hSilenceRate: 0,
      reliabilityCollapseRate: 0,
      averageAdaptationPressure: 0,
      averageMaxH: 0,
      finalLeaps: 0,
    };
  }

  const finalSnapshot = snapshots.at(-1);
  const finalLeaps = finalSnapshot.leapCount ?? 0;
  const pressureSaturationLine = adaptationPressureMax * adaptationPressureSaturationRatio;

  const pressureSaturated = snapshots.filter((snapshot) => (
    (snapshot.adaptationPressure ?? 0) >= pressureSaturationLine
  )).length;
  const hSilent = snapshots.filter((snapshot) => maxValue(snapshot.H) <= hSilenceThreshold).length;
  const reliabilityCollapse = snapshots.filter((snapshot) => (
    Object.values(snapshot.reliability ?? {}).some((value) => value <= reliabilityCollapseThreshold)
  )).length;

  return {
    ticks: snapshots.length,
    leapRate: finalLeaps / snapshots.length,
    adaptationPressureSaturationRate: pressureSaturated / snapshots.length,
    hSilenceRate: hSilent / snapshots.length,
    reliabilityCollapseRate: reliabilityCollapse / snapshots.length,
    averageAdaptationPressure: average(
      snapshots.map((snapshot) => snapshot.adaptationPressure ?? 0),
    ),
    averageMaxH: average(snapshots.map((snapshot) => maxValue(snapshot.H))),
    finalLeaps,
  };
}

export function defaultDurabilityScore(metrics) {
  return 1
    - metrics.adaptationPressureSaturationRate * 0.35
    - metrics.hSilenceRate * 0.2
    - metrics.reliabilityCollapseRate * 0.25
    - Math.min(metrics.leapRate, 1) * 0.2;
}
