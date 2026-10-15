declare module '@lhncbc/ucum-lhc' {
  export interface UcumResult {
    status: string;
    toVal: number | null;
    msg?: string[];
  }
  export class UcumLhcUtils {
    static getInstance(): UcumLhcUtils;
    validateUnitString(unit: string, suggest?: boolean): { status: string; msg?: string[] };
    convertUnitTo(from: string, value: number, to: string): UcumResult;
  }
}
