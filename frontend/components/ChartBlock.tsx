"use client";

// Graphiques automatiques (Module 9) — rendu ECharts.
// Le type est suggéré par le backend selon la nature des données ;
// l'utilisateur peut forcer un autre type. Exports PNG / SVG / CSV.

import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";

// Palette catégorielle validée (validate_palette.js, surface #141b2e,
// tous checks PASS : bande de luminance, chroma, ΔE CVD, contraste ≥3:1).
const PALETTE = [
  "#3987e5",
  "#008300",
  "#d55181",
  "#c98500",
  "#199e70",
  "#d95926",
  "#9085e9",
  "#e66767",
];
const INK = "#9fb3d1"; // texte secondaire — les libellés ne portent jamais la couleur de série
const GRID = "rgba(255,255,255,0.08)";

export interface ChartSuggestion {
  type: string;
  x: string | null;
  y: string[];
  reason: string;
  alternatives: string[];
}

type ChartType = "line" | "bar" | "pie" | "scatter" | "histogram" | "table";

function histogramBins(values: number[], binCount = 12) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const width = (max - min) / binCount || 1;
  const bins = Array.from({ length: binCount }, (_, i) => ({
    label: `${(min + i * width).toFixed(1)}–${(min + (i + 1) * width).toFixed(1)}`,
    count: 0,
  }));
  values.forEach((v) => {
    const idx = Math.min(binCount - 1, Math.floor((v - min) / width));
    bins[idx].count += 1;
  });
  return bins;
}

function buildOption(
  type: ChartType,
  columns: string[],
  rows: any[][],
  suggestion: ChartSuggestion,
) {
  const xi = suggestion.x ? columns.indexOf(suggestion.x) : 0;
  const yCols = suggestion.y.filter((c) => columns.includes(c));
  const yIdx = yCols.map((c) => columns.indexOf(c));
  const multi = yIdx.length > 1;

  const base = {
    color: PALETTE,
    backgroundColor: "transparent",
    textStyle: { color: INK, fontSize: 12 },
    tooltip: {
      trigger: type === "line" ? "axis" : "item",
      axisPointer: type === "line" ? { type: "cross" } : undefined,
      backgroundColor: "#1c2437",
      borderColor: GRID,
      textStyle: { color: "#e2e8f0", fontSize: 12 },
    },
    // Légende seulement à partir de 2 séries (une série : le titre suffit).
    legend: multi ? { textStyle: { color: INK }, top: 0 } : undefined,
    grid: { left: 8, right: 16, top: multi ? 36 : 24, bottom: 8, containLabel: true },
  } as any;

  const axis = {
    axisLine: { lineStyle: { color: GRID } },
    axisTick: { show: false },
    axisLabel: { color: INK },
    splitLine: { lineStyle: { color: GRID } },
  };

  if (type === "pie") {
    return {
      ...base,
      series: [
        {
          type: "pie",
          radius: ["35%", "68%"],
          // Étiquettes directes (nom + valeur) : l'identité n'est jamais
          // portée par la couleur seule.
          label: { color: INK, formatter: "{b} : {c}" },
          itemStyle: { borderColor: "#141b2e", borderWidth: 2 },
          data: rows.map((r) => ({ name: String(r[xi]), value: Number(r[yIdx[0]]) })),
        },
      ],
    };
  }

  if (type === "scatter") {
    return {
      ...base,
      xAxis: { type: "value", name: suggestion.x ?? columns[0], ...axis },
      yAxis: { type: "value", name: yCols[0], ...axis },
      series: [
        {
          type: "scatter",
          symbolSize: 9,
          itemStyle: { borderColor: "#141b2e", borderWidth: 2 },
          data: rows.map((r) => [Number(r[xi]), Number(r[yIdx[0]])]),
        },
      ],
    };
  }

  if (type === "histogram") {
    const values = rows.map((r) => Number(r[yIdx[0] ?? 0])).filter((v) => !isNaN(v));
    const bins = histogramBins(values);
    return {
      ...base,
      xAxis: { type: "category", data: bins.map((b) => b.label), ...axis },
      yAxis: { type: "value", ...axis },
      series: [
        {
          type: "bar",
          barCategoryGap: "10%",
          itemStyle: { borderRadius: [4, 4, 0, 0], borderColor: "#141b2e", borderWidth: 1 },
          data: bins.map((b) => b.count),
        },
      ],
    };
  }

  // line / bar
  const categories = rows.map((r) => String(r[xi]));
  const series = yIdx.map((yi, s) => ({
    name: columns[yi],
    type: type === "line" ? "line" : "bar",
    lineStyle: { width: 2 },
    symbolSize: 8,
    barCategoryGap: "25%",
    itemStyle:
      type === "bar"
        ? { borderRadius: [4, 4, 0, 0], borderColor: "#141b2e", borderWidth: 1 }
        : undefined,
    data: rows.map((r) => Number(r[yi])),
  }));
  return {
    ...base,
    xAxis: { type: "category", data: categories, ...axis },
    yAxis: { type: "value", ...axis },
    series,
  };
}

export default function ChartBlock({
  columns,
  rows,
  suggestion,
}: {
  columns: string[];
  rows: any[][];
  suggestion: ChartSuggestion;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);
  const [type, setType] = useState<ChartType>(suggestion.type as ChartType);

  const choices: ChartType[] = useMemo(() => {
    const all = new Set<ChartType>([
      suggestion.type as ChartType,
      ...(suggestion.alternatives as ChartType[]),
      "table",
    ]);
    return Array.from(all);
  }, [suggestion]);

  useEffect(() => {
    setType(suggestion.type as ChartType);
  }, [suggestion]);

  useEffect(() => {
    if (type === "table" || !ref.current) return;
    let disposed = false;
    import("echarts").then((echarts) => {
      if (disposed || !ref.current) return;
      chartRef.current?.dispose();
      const chart = echarts.init(ref.current);
      chart.setOption(buildOption(type, columns, rows, suggestion));
      chartRef.current = chart;
      const onResize = () => chart.resize();
      window.addEventListener("resize", onResize);
      return () => window.removeEventListener("resize", onResize);
    });
    return () => {
      disposed = true;
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, [type, columns, rows, suggestion]);

  function exportPNG() {
    if (!chartRef.current) return;
    const url = chartRef.current.getDataURL({
      type: "png",
      pixelRatio: 2,
      backgroundColor: "#141b2e",
    });
    downloadURL(url, "noreon_graphique.png");
    api.recordUsage("chart_export", "png");
  }

  async function exportSVG() {
    // Rendu temporaire en SVG (le graphique affiché utilise le canvas).
    const echarts = await import("echarts");
    const tmp = document.createElement("div");
    tmp.style.cssText = "position:fixed;left:-10000px;width:900px;height:420px";
    document.body.appendChild(tmp);
    const chart = echarts.init(tmp, undefined, { renderer: "svg" });
    chart.setOption(buildOption(type, columns, rows, suggestion));
    const svg = tmp.querySelector("svg")?.outerHTML ?? "";
    chart.dispose();
    tmp.remove();
    const blob = new Blob([svg], { type: "image/svg+xml" });
    downloadURL(URL.createObjectURL(blob), "noreon_graphique.svg");
    api.recordUsage("chart_export", "svg");
  }

  function exportCSV() {
    const esc = (v: any) => {
      const s = v == null ? "" : String(v);
      return /[",;\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const csv = [columns.map(esc).join(";"), ...rows.map((r) => r.map(esc).join(";"))].join("\n");
    const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
    downloadURL(URL.createObjectURL(blob), "noreon_donnees.csv");
    api.recordUsage("chart_export", "csv");
  }

  if (rows.length < 2) return null;

  return (
    <div className="card p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm font-medium">Graphique</div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            className="input !w-auto !py-1 text-xs"
            value={type}
            onChange={(e) => setType(e.target.value as ChartType)}
            aria-label="Type de graphique"
          >
            {choices.map((c) => (
              <option key={c} value={c}>
                {{
                  line: "Courbe",
                  bar: "Barres",
                  pie: "Secteurs",
                  scatter: "Nuage",
                  histogram: "Histogramme",
                  table: "Tableau",
                }[c] ?? c}
              </option>
            ))}
          </select>
          {type !== "table" && (
            <>
              <button className="btn-ghost !py-1 text-xs" onClick={exportPNG}>
                PNG
              </button>
              <button className="btn-ghost !py-1 text-xs" onClick={exportSVG}>
                SVG
              </button>
            </>
          )}
          <button className="btn-ghost !py-1 text-xs" onClick={exportCSV}>
            CSV
          </button>
        </div>
      </div>
      <div className="text-xs text-noreon-soft">{suggestion.reason}</div>
      {type !== "table" && <div ref={ref} className="w-full" style={{ height: 340 }} />}
    </div>
  );
}

function downloadURL(url: string, filename: string) {
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  if (url.startsWith("blob:")) URL.revokeObjectURL(url);
}
