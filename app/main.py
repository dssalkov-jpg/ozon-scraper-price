from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from datetime import datetime
import os

from .db import Base, engine, SessionLocal
from .models import Target, RegionProfile, Run, PricePoint
from .scheduler import scheduler, schedule_daily, start_run

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Ozon Price Scraper")
templates = Jinja2Templates(directory="app/templates")

# Статические файлы
os.makedirs("./data/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="./data/static"), name="static")


@app.on_event("startup")
def on_startup():
    os.makedirs("./data/regions", exist_ok=True)
    schedule_daily()
    scheduler.start()


@app.get("/")
def root():
    return RedirectResponse("/targets")


# === TARGETS ===

@app.get("/targets")
def targets(request: Request):
    db: Session = SessionLocal()
    try:
        rows = db.query(Target).order_by(Target.id.desc()).all()
        return templates.TemplateResponse("targets.html", {"request": request, "targets": rows})
    finally:
        db.close()


@app.post("/targets/add")
def targets_add(url: str = Form(...), name: str = Form("")):
    db: Session = SessionLocal()
    try:
        # Нормализация URL
        url = url.strip()
        if not url.startswith("http"):
            url = "https://" + url
        
        if not db.query(Target).filter(Target.url == url).first():
            db.add(Target(url=url, name=name.strip()))
            db.commit()
        return RedirectResponse("/targets", status_code=303)
    finally:
        db.close()


@app.post("/targets/toggle")
def targets_toggle(target_id: int = Form(...)):
    db: Session = SessionLocal()
    try:
        t = db.query(Target).filter(Target.id == target_id).first()
        if t:
            t.enabled = not t.enabled
            db.commit()
        return RedirectResponse("/targets", status_code=303)
    finally:
        db.close()


@app.post("/targets/delete")
def targets_delete(target_id: int = Form(...)):
    db: Session = SessionLocal()
    try:
        t = db.query(Target).filter(Target.id == target_id).first()
        if t:
            db.delete(t)
            db.commit()
        return RedirectResponse("/targets", status_code=303)
    finally:
        db.close()


# === REGIONS ===

@app.get("/regions")
def regions(request: Request):
    db: Session = SessionLocal()
    try:
        rows = db.query(RegionProfile).order_by(RegionProfile.id.asc()).all()
        return templates.TemplateResponse("regions.html", {"request": request, "regions": rows})
    finally:
        db.close()


@app.post("/regions/add")
def regions_add(name: str = Form(...)):
    db: Session = SessionLocal()
    try:
        name = name.strip().replace(" ", "_").lower()
        storage_path = f"./data/regions/{name}"
        os.makedirs(storage_path, exist_ok=True)
        if not db.query(RegionProfile).filter(RegionProfile.name == name).first():
            db.add(RegionProfile(name=name, storage_path=storage_path, updated_at=datetime.utcnow()))
            db.commit()
        return RedirectResponse("/regions", status_code=303)
    finally:
        db.close()


# === RUNS ===

@app.get("/runs")
def runs(request: Request):
    db: Session = SessionLocal()
    try:
        runs = db.query(Run).order_by(Run.id.desc()).limit(50).all()
        regions = db.query(RegionProfile).order_by(RegionProfile.id.asc()).all()
        return templates.TemplateResponse("runs.html", {"request": request, "runs": runs, "regions": regions})
    finally:
        db.close()


@app.post("/runs/start")
def runs_start(region_profile_id: int = Form(...)):
    try:
        run_id = start_run(region_profile_id)
        return RedirectResponse(f"/runs?started={run_id}", status_code=303)
    except RuntimeError as e:
        return RedirectResponse(f"/runs?error={str(e)}", status_code=303)


@app.get("/runs/{run_id}")
def run_details(request: Request, run_id: int):
    db: Session = SessionLocal()
    try:
        run = db.query(Run).filter(Run.id == run_id).first()
        points = (
            db.query(PricePoint)
            .filter(PricePoint.run_id == run_id)
            .order_by(PricePoint.id.asc())
            .all()
        )
        return templates.TemplateResponse("run_details.html", {
            "request": request,
            "run": run,
            "points": points
        })
    finally:
        db.close()


@app.get("/runs/{run_id}/json")
def run_json(run_id: int):
    db: Session = SessionLocal()
    try:
        run = db.query(Run).filter(Run.id == run_id).first()
        points = (
            db.query(PricePoint)
            .filter(PricePoint.run_id == run_id)
            .order_by(PricePoint.id.asc())
            .all()
        )
        return JSONResponse({
            "run": {
                "id": run.id if run else None,
                "status": run.status if run else None,
                "error": run.error if run else None,
                "total": run.total_targets if run else 0,
                "success": run.success_count if run else 0,
                "fail": run.fail_count if run else 0,
            },
            "items": [
                {
                    "target_id": p.target_id,
                    "url": p.target.url,
                    "name": p.target.name,
                    "price": p.price / 100 if p.price else None,
                    "old_price": p.old_price / 100 if p.old_price else None,
                    "card_price": p.card_price / 100 if p.card_price else None,
                    "in_stock": p.in_stock,
                    "error": p.error,
                    "collected_at": p.collected_at.isoformat() if p.collected_at else None,
                }
                for p in points
            ],
        })
    finally:
        db.close()


# === API для интеграций ===

@app.get("/api/prices/latest")
def api_latest_prices():
    """Последние цены по каждому target"""
    db: Session = SessionLocal()
    try:
        # Находим последний успешный run
        last_run = db.query(Run).filter(Run.status == "done").order_by(Run.id.desc()).first()
        if not last_run:
            return JSONResponse({"error": "no_completed_runs", "items": []})
        
        points = (
            db.query(PricePoint)
            .filter(PricePoint.run_id == last_run.id)
            .all()
        )
        
        return JSONResponse({
            "run_id": last_run.id,
            "collected_at": last_run.finished_at.isoformat() if last_run.finished_at else None,
            "items": [
                {
                    "target_id": p.target_id,
                    "name": p.target.name,
                    "url": p.target.url,
                    "price": p.price / 100 if p.price else None,
                    "old_price": p.old_price / 100 if p.old_price else None,
                    "card_price": p.card_price / 100 if p.card_price else None,
                    "in_stock": p.in_stock,
                }
                for p in points
            ]
        })
    finally:
        db.close()
