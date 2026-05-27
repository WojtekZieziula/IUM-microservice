from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import random
import datetime
import json
import joblib

MODELS = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Loading ML models...")
    try:
        # Dopóki nie ma działających modeli jest podstawiony placeholder
        # MODELS["A_Baseline"] = joblib.load("models/baseline.pkl")
        # MODELS["B_Target"] = joblib.load("models/target.pkl")

        MODELS["A_Baseline"] = "dummy_model_a"
        MODELS["B_Target"] = "dummy_model_b"
        print("Models loaded successfully!")
    except FileNotFoundError as e:
        print(f"ERROR: Could not find model file. {e}")

    yield

    print("Shutting down, cleaning up resources...")
    MODELS.clear()


app = FastAPI(
    title="Nocarz ML API",
    description="Microservice for property valuation with A/B testing mechanism",
    version="1.0",
    lifespan=lifespan
)

# Te dane będzie trzeba pozmieniać w zależności od tego czego będziemy używać
# Ta klasa jest o tyle spoko, że automatycznie waliduje typy danych
class ListingData(BaseModel):
    accommodates: int
    bedrooms: float
    bathrooms: float

@app.post("/predict")
def predict_price(listing: ListingData):
    """
    Main endpoint. Accepts listing data and returns a prediction.
    """

    if not MODELS:
        raise HTTPException(status_code=500, detail="ML models have not been loaded on the server.")

    # na razie w teście A/B szanse to 50/50
    selected_model = random.choice(["A_Baseline", "B_Target"])
    model_instance = MODELS[selected_model]

    # placeholder na generowanie odpowiedzi przez model
    if selected_model == "A_Baseline":
        result = "too_high"
    else:
        result = "just_right"

    log_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "model_used": selected_model,
        "input_features": listing.model_dump(),
        "prediction_result": result
    }

    with open("logs.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")

    return {
        "prediction": result
    }
