Repo for UCSD Diamondhacks 2026 submission.

# To install/run

**Important**: make sure you are in the **_root directory_** of the repo.
Install JS dependencies:
```bash
pnpm i
```

Source the backend via the virtual environment (if VS Code/Cursor/etc doesn't do this for you):
```bash
source backend/.venv/bin/activate
```

Install Python dependencies:
```bash
cd backend
uv sync
```

Run the frontend and backend:
```bash
pnpm dev
```
