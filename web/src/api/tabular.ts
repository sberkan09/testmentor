export interface Table {
  headers: string[];
  rows: string[][];
}

/** RFC 4180 style CSV parser; the delimiter (comma or semicolon) is sniffed from the first line. */
export function parseCsv(input: string): string[][] {
  const text = input.replace(/^\u{FEFF}/u, "");
  const firstLine = text.split(/\r?\n/, 1)[0] ?? "";
  const delim = (firstLine.match(/;/g)?.length ?? 0) > (firstLine.match(/,/g)?.length ?? 0) ? ";" : ",";
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i] as string;
    if (quoted) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          cell += '"';
          i++;
        } else quoted = false;
      } else cell += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === delim) {
      row.push(cell);
      cell = "";
    } else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(cell);
      cell = "";
      rows.push(row);
      row = [];
    } else cell += ch;
  }
  if (cell !== "" || row.length > 0) {
    row.push(cell);
    rows.push(row);
  }
  return rows.filter((r) => r.some((c) => c.trim() !== ""));
}

export function toTable(data: unknown[][]): Table {
  const [head = [], ...rest] = data;
  const headers = head.map((h, i) => (String(h ?? "").trim() || `Kolon ${i + 1}`));
  return { headers, rows: rest.map((r) => headers.map((_, i) => String(r[i] ?? ""))) };
}

export interface SheetTables {
  sheets: { name: string; table: Table }[];
}

/** Reads a csv or xlsx file for the column mapping preview. xlsx is parsed in the browser. */
export async function readTables(file: File): Promise<SheetTables> {
  if (/\.xlsx$/i.test(file.name)) {
    const { default: readXlsxFile } = await import("read-excel-file/browser");
    const sheets = await readXlsxFile(file);
    return { sheets: sheets.map((s) => ({ name: s.sheet, table: toTable(s.data as unknown[][]) })) };
  }
  const text = await file.text();
  return { sheets: [{ name: "", table: toTable(parseCsv(text)) }] };
}

/** Guess the column mapping from header names. */
export function guessMapping(headers: string[]): { text: string; id: string; language: string; source: string } {
  const find = (re: RegExp) => headers.find((h) => re.test(h.toLowerCase())) ?? "";
  return {
    id: find(/^(id|kimlik|no|req.?id|gereksinim.?(id|no|kimli))/),
    text:
      find(/^(text|metin|gereksinim.?metn|requirement.?text)/) ||
      find(/(text|metin|requirement|açıklama|aciklama|description)/) ||
      (headers[1] ?? headers[0] ?? ""),
    language: find(/^(lang|language|dil)/),
    source: find(/(source|kaynak|belge|document)/),
  };
}
