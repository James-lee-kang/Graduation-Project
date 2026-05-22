import type { SiteSummaryItem } from "./types";

type SummaryStatCardsProps = {
  items: SiteSummaryItem[];
};

export function SummaryStatCards({ items }: SummaryStatCardsProps) {
  return (
    <div className="grid min-h-0 grid-cols-3 gap-3">
      {items.map((item) => (
        <div
          key={item.label}
          className="flex min-h-[112px] flex-col justify-between rounded-xl bg-white px-4 py-4"
        >
          <p className="text-xs font-semibold text-[#8a94a6]">{item.label}</p>
          <div className="flex items-end justify-end gap-1">
            <span className="text-3xl font-bold leading-none text-slate-950">{item.value}</span>
            {item.unit.length > 0 && <span className="text-base font-semibold text-slate-500">{item.unit}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}
