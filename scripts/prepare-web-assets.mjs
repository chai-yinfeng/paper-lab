import { cpSync, mkdirSync } from "node:fs";
for (const name of ["cmaps", "standard_fonts", "wasm"]) {
  const target = `web/public/pdf-assets/${name}`;
  mkdirSync(target, { recursive: true });
  cpSync(`node_modules/pdfjs-dist/${name}`, target, { recursive: true });
}
