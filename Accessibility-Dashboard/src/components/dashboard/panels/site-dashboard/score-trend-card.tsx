import { ChartContainer, ChartTooltip } from "@/components/ui/line-charts-6";
import { Bar, CartesianGrid, ComposedChart, Line, XAxis, YAxis } from "recharts";

import { chartConfig, chartLineVisibility, scoreGridLines } from "./constants";
import { SummaryStatCards } from "./summary-stat-cards";
import type { ChartSeriesKey, ScoreChartItem, SiteSummaryItem } from "./types";
import { formatDateLabel, getChartLabel, getChartValueSuffix } from "./utils";

type ScoreTrendCardProps = {
  chartData: ScoreChartItem[];
  summaryItems: SiteSummaryItem[];
};

type IssueBarShapeProps = {
  fill?: string;
  height?: number | string;
  width?: number | string;
  x?: number | string;
  y?: number | string;
};

function toChartNumber(value: number | string | undefined): number {
  if (typeof value === "number") {
    return value;
  }

  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  return 0;
}

function IssueBarShape({ fill, height, width, x, y }: IssueBarShapeProps) {
  const xValue = toChartNumber(x);
  const yValue = toChartNumber(y);
  const widthValue = toChartNumber(width);
  const heightValue = toChartNumber(height);

  if (widthValue <= 0 || heightValue <= 0) {
    return null;
  }

  const radius = Math.min(3, widthValue / 2, heightValue);
  const right = xValue + widthValue;
  const bottom = yValue + heightValue;
  const barPath = [
    `M ${xValue} ${bottom}`,
    `V ${yValue + radius}`,
    `Q ${xValue} ${yValue} ${xValue + radius} ${yValue}`,
    `H ${right - radius}`,
    `Q ${right} ${yValue} ${right} ${yValue + radius}`,
    `V ${bottom}`,
    "Z"
  ].join(" ");

  return (
    <g>
      <rect
        x={xValue - 1}
        y={yValue - 1}
        width={widthValue + 2}
        height={heightValue + 2}
        fill="var(--dashboard-card-bg)"
      />
      <path d={barPath} fill={fill ?? chartConfig.issueCount.color} />
    </g>
  );
}

export function ScoreTrendCard({ chartData, summaryItems }: ScoreTrendCardProps) {
  return (
    <article className="dashboard-card flex h-full min-h-0 w-full flex-col rounded-xl border border-slate-200 bg-white p-1">
      <div className="relative flex items-center justify-between px-3 pt-3">
        <h2 className="text-sm font-semibold text-slate-900">접근성 점수 추이</h2>
      </div>
      <div className="mt-2 px-2.5 py-4">
        <ChartContainer
          config={chartConfig}
          className="h-[360px] w-full overflow-visible [&_.recharts-curve.recharts-tooltip-cursor]:stroke-initial"
        >
          <ComposedChart
            data={chartData}
            margin={{
              top: 20,
              right: 20,
              left: 5,
              bottom: 20
            }}
            style={{ overflow: "visible" }}
          >
            <XAxis
              dataKey="label"
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
              tickMargin={10}
              padding={{ left: 2, right: 2 }}
            />

            <YAxis
              yAxisId="score"
              axisLine={false}
              tickLine={false}
              domain={[0, 100]}
              ticks={[0, 20, 40, 60, 80, 100]}
              tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
              tickFormatter={(value: number) => `${value}점`}
              tickMargin={10}
            />

            <YAxis
              yAxisId="issues"
              orientation="right"
              axisLine={false}
              tickLine={false}
              domain={[0, (dataMax: number) => Math.max(dataMax * 4, 1)]}
              width={0}
              tick={false}
              tickFormatter={() => ""}
            />

            <CartesianGrid
              yAxisId="score"
              vertical={false}
              horizontalValues={scoreGridLines}
              stroke="var(--site-score-grid-color)"
              strokeWidth={1}
              strokeOpacity={0.9}
            />

            <Bar
              yAxisId="issues"
              dataKey="issueCount"
              fill={chartConfig.issueCount.color}
              fillOpacity={1}
              barSize={14}
              radius={[3, 3, 0, 0]}
              shape={<IssueBarShape />}
              isAnimationActive={false}
            />

            <ChartTooltip
              content={<ScoreTooltip visibleSeries={chartLineVisibility} />}
              cursor={{ strokeDasharray: "3 3", stroke: "#9ca3af" }}
            />

            <Line
              yAxisId="score"
              type="monotone"
              dataKey="score"
              stroke={chartConfig.score.color}
              strokeWidth={2.25}
              dot={false}
              activeDot={{
                r: 4,
                fill: chartConfig.score.color,
                stroke: chartConfig.score.color,
                strokeWidth: 0
              }}
            />
          </ComposedChart>
        </ChartContainer>
      </div>
      <div className="px-3 pb-3">
        <SummaryStatCards items={summaryItems} />
      </div>
    </article>
  );
}

function ScoreTooltip({
  active,
  payload,
  visibleSeries
}: {
  active?: boolean;
  payload?: Array<{
    dataKey?: string | number;
    value?: number;
    color?: string;
    payload?: ScoreChartItem;
  }>;
  visibleSeries: Record<ChartSeriesKey, boolean>;
}) {
  const rows = (payload ?? [])
    .filter(
      (entry): entry is { dataKey: string | number; value: number; color?: string; payload?: ScoreChartItem } =>
        typeof entry.value === "number" &&
        entry.dataKey !== undefined &&
        visibleSeries[String(entry.dataKey) as ChartSeriesKey] === true
    )
    .sort((left, right) => {
      const order: Record<ChartSeriesKey, number> = {
        score: 0,
        issueCount: 1
      };
      return order[String(left.dataKey) as ChartSeriesKey] - order[String(right.dataKey) as ChartSeriesKey];
    });

  if (!active || rows.length === 0) {
    return null;
  }

  const label = rows[0]?.payload?.date ? formatDateLabel(rows[0].payload.date) : "";

  return (
    <div
      role="tooltip"
      className="min-w-[170px] rounded-lg px-3 py-2 text-left shadow-[0_14px_32px_rgba(2,6,23,0.32)]"
      style={{
        backgroundColor: "rgba(8, 8, 10, 0.96)",
        border: "1px solid rgba(255, 255, 255, 0.08)"
      }}
    >
      {label && <p className="text-[11px] font-semibold text-white">{label}</p>}
      <div className="mt-1 grid gap-1.5 text-sm">
        {rows.map((entry) => {
          const key = String(entry.dataKey) as keyof typeof chartConfig;
          const color = entry.color ?? chartConfig[key]?.color ?? chartConfig.score.color;
          return (
            <div key={String(entry.dataKey)} className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                {key !== "score" && (
                  <span className="size-1.5 rounded-full" style={{ backgroundColor: color }} aria-hidden="true" />
                )}
                <span className="text-[11px] font-semibold text-white">{getChartLabel(key)}</span>
              </div>
              <span className="font-bold text-white">
                {entry.value}
                {getChartValueSuffix(key)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
