export function fmt(x: number, digits = 4): string {
  if (!Number.isFinite(x)) return String(x);
  if (x === 0) return '0';
  const abs = Math.abs(x);
  if (abs >= 1e6 || abs < 1e-3) return x.toExponential(digits - 1);
  return String(Number(x.toPrecision(digits)));
}
