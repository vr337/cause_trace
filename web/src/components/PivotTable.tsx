import {
  flexRender,
  getCoreRowModel,
  getExpandedRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type ExpandedState,
  type SortingState,
} from "@tanstack/react-table";
import { useMemo, useState } from "react";

export interface PivotRow {
  id: string;
  dimension: string;
  contribution: number;
  contributionRate: number;
  delta: number;
  children?: PivotRow[];
}

interface Props {
  rows: PivotRow[];
}

/** 多维下钻透视表：支持层级折叠、列头排序与差额高亮（FR-15）。 */
export function PivotTable({ rows }: Props) {
  const [expanded, setExpanded] = useState<ExpandedState>({});
  const [sorting, setSorting] = useState<SortingState>([{ id: "contribution", desc: true }]);

  const columns = useMemo<ColumnDef<PivotRow>[]>(
    () => [
      {
        accessorKey: "dimension",
        header: "维度",
        cell: ({ row }) => (
          <span
            className={row.getCanExpand() ? "cursor-pointer font-medium" : "pl-4 text-ink-600"}
            onClick={row.getToggleExpandedHandler()}
          >
            {row.getCanExpand() ? (row.getIsExpanded() ? "▾ " : "▸ ") : ""}
            {row.getValue<string>("dimension")}
          </span>
        ),
      },
      {
        accessorKey: "contribution",
        header: "贡献量",
        cell: ({ getValue }) => {
          const value = getValue<number>();
          return (
            <span className={value < 0 ? "text-fall" : "text-rise"}>
              {value.toLocaleString(undefined, { maximumFractionDigits: 2 })}
            </span>
          );
        },
      },
      {
        accessorKey: "contributionRate",
        header: "贡献率",
        cell: ({ getValue }) => `${(getValue<number>() * 100).toFixed(1)}%`,
      },
      {
        accessorKey: "delta",
        header: "变动量",
        cell: ({ getValue }) => {
          const value = getValue<number>();
          return (
            <span className={value < 0 ? "text-fall" : "text-rise"}>
              {value.toLocaleString(undefined, { maximumFractionDigits: 2 })}
            </span>
          );
        },
      },
    ],
    [],
  );

  const table = useReactTable({
    data: rows,
    columns,
    state: { expanded, sorting },
    onExpandedChange: setExpanded,
    onSortingChange: setSorting,
    getSubRows: (row) => row.children,
    getCoreRowModel: getCoreRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="border-b border-ink-200 text-left text-ink-500">
          {table.getHeaderGroups()[0].headers.map((header) => (
            <th
              key={header.id}
              className="cursor-pointer select-none py-1.5 pr-3 font-medium"
              onClick={header.column.getToggleSortingHandler()}
            >
              {flexRender(header.column.columnDef.header, header.getContext())}
              {header.column.getIsSorted() === "asc" ? " ↑" : ""}
              {header.column.getIsSorted() === "desc" ? " ↓" : ""}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {table.getRowModel().rows.map((row) => (
          <tr key={row.id} className="border-b border-ink-100 last:border-0">
            {row.getVisibleCells().map((cell) => (
              <td key={cell.id} className="py-1.5 pr-3">
                {flexRender(cell.column.columnDef.cell, cell.getContext())}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
