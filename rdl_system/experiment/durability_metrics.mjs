function average(values) {
  if (values.length === 0) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function l2Norm(record = {}) {
  return Math.sqrt(
    Object.values(record ?? {}).reduce((sum, value) => {
      const numeric = Number(value) || 0;
      return sum + numeric * numeric;
    }, 0),
  );
}

function scalarH(snapshot = {}) {
  if (typeof snapshot.H === "number") return Math.abs(snapshot.H);
  if (snapshot.HVector && typeof snapshot.HVector === "object") return l2Norm(snapshot.HVector);
  // Compatibility for snapshots produced before the Core v2.3 H-scalar cutover.
  if (snapshot.H && typeof snapshot.H === "object") return l2Norm(snapshot.H);
  return 0;
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
      averageH: 0,
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
  const hSilent = snapshots.filter((snapshot) => scalarH(snapshot) <= hSilenceThreshold).length;
  const reliabilityCollapse = snapshots.filter((snapshot) => (
    Object.values(snapshot.reliability ?? {}).some((value) => value <= reliabilityCollapseThreshold)
  )).length;
  const averageScalarH = average(snapshots.map((snapshot) => scalarH(snapshot)));

  return {
    ticks: snapshots.length,
    leapRate: finalLeaps / snapshots.length,
    adaptationPressureSaturationRate: pressureSaturated / snapshots.length,
    hSilenceRate: hSilent / snapshots.length,
    reliabilityCollapseRate: reliabilityCollapse / snapshots.length,
    averageAdaptationPressure: average(
      snapshots.map((snapshot) => snapshot.adaptationPressure ?? 0),
    ),
    averageH: averageScalarH,
    // Compatibility alias for callers of the pre-scalar metric name.
    averageMaxH: averageScalarH,
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
