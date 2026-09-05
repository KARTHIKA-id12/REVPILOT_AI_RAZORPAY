# database/seeds

`technest_demo.dump` is a `pg_dump -Fc` snapshot of a freshly seeded
TechNest merchant (1,050 customers, 4,799 orders, 12 products) — a
convenience checkpoint so you don't have to regenerate from scratch.

**Restore it:**
```bash
pg_restore --clean --if-exists -d "$DATABASE_URL" database/seeds/technest_demo.dump
```

**Or regenerate it from code** (the actual source of truth — deterministic,
seeded with `RNG_SEED = 42` in `scripts/seed_demo.py`):
```bash
python scripts/seed_demo.py
```

Demo login: `owner@technest.demo` / `RevPilotDemo123!`
