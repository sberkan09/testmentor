import { describe, expect, it } from "vitest";
import { guessMapping, parseCsv, toTable } from "./tabular";

describe("parseCsv", () => {
  it("tırnaklı alanları, virgülü ve satır sonlarını işler", () => {
    const rows = parseCsv('id,text\r\nR1,"Sistem, giriş yapar"\nR2,"Tırnak ""içinde"""\n');
    expect(rows).toEqual([
      ["id", "text"],
      ["R1", "Sistem, giriş yapar"],
      ["R2", 'Tırnak "içinde"'],
    ]);
  });

  it("noktalı virgül ayracını ve BOM'u tanır", () => {
    expect(parseCsv("﻿id;metin\nR1;merhaba")).toEqual([
      ["id", "metin"],
      ["R1", "merhaba"],
    ]);
  });

  it("tırnak içinde satır sonunu korur, boş satırları atar", () => {
    expect(parseCsv('a,b\n"x\ny",z\n\n')).toEqual([
      ["a", "b"],
      ["x\ny", "z"],
    ]);
  });
});

describe("kolon tahmini", () => {
  it("başlıklardan eşleme önerir", () => {
    const t = toTable(parseCsv("id,language,text\nR1,tr,metin"));
    expect(guessMapping(t.headers)).toMatchObject({ id: "id", language: "language", text: "text" });
    expect(guessMapping(["Gereksinim No", "Gereksinim Metni", "Dil"])).toMatchObject({ id: "Gereksinim No", text: "Gereksinim Metni", language: "Dil" });
  });
});
