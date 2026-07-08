/**
 * K-line completeness calendar (P2-06).
 *
 * A hand-drawn CSS-grid month calendar: header row is 一~日 (Mon..Sun),
 * cells flow week-by-week (one row per week). Each cell is colored by its
 * daily status (green/yellow/red/gray). Future days are forced gray.
 * Clicking a past/present trading-day cell fires `onSelectDay`.
 */
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, DatePicker, Skeleton, Space, Tooltip } from "antd";
import { LeftOutlined, RightOutlined } from "@ant-design/icons";
import dayjs, { Dayjs } from "dayjs";

import { CalendarMonth, DayStatus, getCalendar } from "@/api/health";

interface Props {
  onSelectDay: (date: string) => void;
}

const STATUS_COLOR: Record<DayStatus["status"], string> = {
  green: "#16a34a",
  yellow: "#f59e0b",
  red: "#dc2626",
  gray: "#eef1f6",
};

const STATUS_LABEL: Record<DayStatus["status"], string> = {
  green: "完整",
  yellow: "部分缺失",
  red: "全部缺失",
  gray: "非交易日",
};

const WEEK_HEADERS = ["一", "二", "三", "四", "五", "六", "日"];

interface Cell {
  key: string;
  day: DayStatus | null; // null = leading blank placeholder
  isFuture: boolean;
}

/** Build a flat cell list with leading blanks so week 1 aligns under Mon..Sun. */
function buildCells(cal: CalendarMonth): Cell[] {
  const today = dayjs().format("YYYY-MM-DD");
  const first = dayjs(`${cal.year}-${String(cal.month).padStart(2, "0")}-01`);
  // dayjs: Sun=0..Sat=6; convert so Mon=0..Sun=6
  const lead = (first.day() + 6) % 7;

  const cells: Cell[] = [];
  for (let i = 0; i < lead; i += 1) {
    cells.push({ key: `blank-${i}`, day: null, isFuture: false });
  }
  cal.days.forEach((d) => {
    cells.push({ key: d.date, day: d, isFuture: d.date > today });
  });
  return cells;
}

function CellTooltip({ day, isFuture }: { day: DayStatus; isFuture: boolean }) {
  if (isFuture) {
    return (
      <div>
        <div style={{ fontWeight: 700, marginBottom: 4 }}>{day.date}</div>
        <div style={{ color: "#cbd5e1" }}>尚未到来</div>
      </div>
    );
  }
  return (
    <div>
      <div style={{ fontWeight: 700, marginBottom: 4 }}>{day.date}</div>
      <div>
        <span
          style={{
            display: "inline-block",
            width: 8,
            height: 8,
            borderRadius: "50%",
            marginRight: 6,
            background: STATUS_COLOR[day.status],
          }}
        />
        {STATUS_LABEL[day.status]}
      </div>
      {day.is_open && (
        <div style={{ marginTop: 4, color: "#cbd5e1" }}>
          应更新 <b style={{ color: "#fff" }}>{day.expected}</b> · 已更新{" "}
          <b style={{ color: "#fff" }}>{day.actual}</b>
        </div>
      )}
      {day.has_anomaly && (
        <div style={{ marginTop: 4, color: "#fbbf24" }}>⚠ 存在异常行</div>
      )}
    </div>
  );
}

export default function KlineCalendar({ onSelectDay }: Props) {
  const [cursor, setCursor] = useState<Dayjs>(dayjs().startOf("month"));
  const year = cursor.year();
  const month = cursor.month() + 1;
  const today = dayjs().format("YYYY-MM-DD");

  const { data, error, isLoading } = useQuery({
    queryKey: ["health", "kline", "calendar", year, month],
    queryFn: () => getCalendar(year, month),
  });

  const cells = useMemo(() => (data ? buildCells(data) : []), [data]);

  const handleClick = (cell: Cell) => {
    if (!cell.day || cell.isFuture) return;
    if (!cell.day.is_open) return;
    onSelectDay(cell.day.date);
  };

  return (
    <Card
      title={<span className="section-title"><span className="bar" />K 线月历</span>}
      extra={
        <Space>
          <Button shape="circle" icon={<LeftOutlined />} onClick={() => setCursor(cursor.subtract(1, "month"))} />
          <DatePicker
            picker="month"
            allowClear={false}
            value={cursor}
            onChange={(v) => v && setCursor(v.startOf("month"))}
          />
          <Button shape="circle" icon={<RightOutlined />} onClick={() => setCursor(cursor.add(1, "month"))} />
        </Space>
      }
    >
      <div className="legend-row">
        <span className="legend-item"><span className="legend-dot" style={{ background: "#16a34a" }} />完整</span>
        <span className="legend-item"><span className="legend-dot" style={{ background: "#f59e0b" }} />部分缺失</span>
        <span className="legend-item"><span className="legend-dot" style={{ background: "#dc2626" }} />全部缺失</span>
        <span className="legend-item"><span className="legend-dot" style={{ background: "#cbd5e1" }} />非交易日</span>
        <span className="legend-item" style={{ background: "rgba(245,158,11,0.12)", color: "#b45309" }}>⚠ 当日存在异常行</span>
      </div>

      {isLoading && <Skeleton active />}
      {error && <Alert type="error" showIcon message="加载月历失败" description={String(error)} />}

      {data && (
        <div className="cal">
          <div className="cal-head">
            {WEEK_HEADERS.map((w) => (
              <div key={w} className="cal-head-cell">{w}</div>
            ))}
          </div>
          <div className="cal-grid">
            {cells.map((cell) => {
              if (!cell.day) {
                return <div key={cell.key} className="cal-cell cal-cell--blank" />;
              }
              const { day, isFuture } = cell;
              const color = isFuture ? STATUS_COLOR.gray : STATUS_COLOR[day.status];
              const clickable = !isFuture && day.is_open;
              const isToday = day.date === today;
              return (
                <Tooltip
                  key={cell.key}
                  title={<CellTooltip day={day} isFuture={isFuture} />}
                  color="rgba(15, 23, 42, 0.92)"
                >
                  <div
                    className={[
                      "cal-cell",
                      clickable ? "cal-cell--clickable" : "",
                      isFuture ? "cal-cell--future" : "",
                      isToday ? "cal-cell--today" : "",
                    ].filter(Boolean).join(" ")}
                    style={{ background: color }}
                    onClick={() => handleClick(cell)}
                  >
                    <span className="cal-cell-num">{Number(day.date.slice(-2))}</span>
                    {day.has_anomaly && !isFuture && <span className="cal-cell-warn">⚠</span>}
                  </div>
                </Tooltip>
              );
            })}
          </div>
        </div>
      )}
    </Card>
  );
}
