import { ReactNode } from "react";

type DataTableProps = {
  title?: string;
  subtitle?: string;
  headers: string[];
  rows: ReactNode[][];
};

export function DataTable({ title, subtitle, headers, rows }: DataTableProps) {
  return (
    <section className="table-card">
      {(title || subtitle) ? (
        <header>
          {title ? <h2>{title}</h2> : null}
          {subtitle ? <p>{subtitle}</p> : null}
        </header>
      ) : null}
      <table>
        <thead>
          <tr>
            {headers.map((header) => (
              <th key={header}>{header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${title}-${index}`}>
              {row.map((cell, cellIndex) => (
                <td key={`${title}-${index}-${cellIndex}`}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
