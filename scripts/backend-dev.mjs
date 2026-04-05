import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

const backend = join(process.cwd(), "backend");
const win = join(backend, ".venv", "Scripts", "python.exe");
const unix = join(backend, ".venv", "bin", "python");
const python = existsSync(win) ? win : unix;

if (!existsSync(python)) {
  console.error(
    "No venv Python found. From the backend folder run: python -m venv .venv && .venv\\Scripts\\pip install -r requirements.txt (Windows)"
  );
  process.exit(1);
}

const result = spawnSync(python, ["main.py"], {
  cwd: backend,
  stdio: "inherit",
  env: process.env,
});
process.exit(result.status ?? 1);
