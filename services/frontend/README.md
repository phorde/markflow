# MarkFlow Web

Next.js frontend for the MarkFlow web platform.

## Local run

```powershell
cd services/frontend
copy .env.local.example .env.local
npm install
npm run dev
```

Then open:
- http://localhost:3000

## API backend

Run the FastAPI backend in another terminal:

```powershell
uvicorn app:create_app --factory --reload --app-dir services/api
```

Backend docs:
- http://127.0.0.1:8000/docs

## Notes

- The frontend talks to the API through `NEXT_PUBLIC_MARKFLOW_API_URL`.
- Review edits are saved to the API, and export downloads a JSON snapshot of the job state.
