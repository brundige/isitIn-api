import sharp from "sharp";
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const publicDir = resolve(__dirname, "../public");

const standardSvg = readFileSync(resolve(publicDir, "icon-source.svg"));
const maskableSvg = readFileSync(resolve(publicDir, "icon-source-maskable.svg"));

const targets = [
  { src: standardSvg, size: 192, out: "icon-192.png" },
  { src: standardSvg, size: 512, out: "icon-512.png" },
  { src: standardSvg, size: 180, out: "apple-touch-icon.png" },
  { src: maskableSvg, size: 512, out: "icon-maskable-512.png" },
];

for (const { src, size, out } of targets) {
  await sharp(src, { density: 384 })
    .resize(size, size)
    .png()
    .toFile(resolve(publicDir, out));
  console.log(`wrote public/${out}`);
}
